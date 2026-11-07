"""The agent loop: model turn → tool calls → results → … → verified final answer."""

from __future__ import annotations

import json
import time
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from aiagent.config import AgentConfig
from aiagent.llm import LLMClient, LLMError, Message, ModelTurn, ToolCall, Usage
from aiagent.sandbox import Workspace
from aiagent.tools import ToolContext, ToolRegistry, ToolResult, default_registry
from aiagent.verify import Verification, run_verification

SYSTEM_PROMPT = """\
You are an autonomous coding agent working inside a sandboxed project directory.
You act only through the tools provided.

Workflow:
1. Explore: use list_files and search_code to find the relevant code, and read_file before
   editing anything.
2. Reproduce: when fixing a bug, reproduce it first with run_python or run_tests if practical.
3. Edit: make focused changes with apply_patch. Use write_file only to create new files.
   Match the existing code style.
4. Check: after editing, run run_tests (and run_python where useful). If something fails,
   read the error, fix the cause and run it again.
5. Finish: reply with a short summary of what you changed and how you checked it, without
   calling a tool.

Be efficient; every turn costs time and money:
- Make independent tool calls in the same turn. For example, read all the files you need at
  once, or patch several files together.
- Don't re-read a file you have already read unless it has changed since.
- Once the tests pass, finish straight away.

Rules:
- Paths are relative to the project root; nothing outside it is accessible.
- read_file prefixes each line with its number ("   12 | "). Never copy those prefixes into
  patches or file contents.
- If a patch is rejected, the error shows where the closest match is. Re-read that region
  and send a corrected patch; never resend the same patch.
- Change only what the task needs. Add or update tests when you add behaviour.
- Your final answer triggers an automatic run of the project's tests. If they fail, you will
  be asked to continue.
"""

MAX_IDENTICAL_CALLS = 2
# Verification runs the project's tests, so it goes through approval like run_tests.
VERIFY_CALL = ToolCall("run_tests", {})

# Called before each side-effecting action with the call and, for edits, a dry-run preview.
Approver = Callable[[ToolCall, ToolResult | None], bool]


class AgentObserver:
    """Hooks for UI and tracing. Every method is a no-op by default."""

    def on_start(self, task: str, config: AgentConfig) -> None: ...
    def on_model_turn(self, step: int, turn: ModelTurn) -> None: ...
    def on_tool_call(self, call: ToolCall) -> None: ...
    def on_tool_result(self, call: ToolCall, result: ToolResult) -> None: ...
    def on_verification(self, verification: Verification) -> None: ...
    def on_finish(self, result: RunResult) -> None: ...


@dataclass(frozen=True)
class RunResult:
    status: str  # completed | verification_failed | step_limit | error
    message: str
    steps: int
    tool_calls: int
    changed_files: list[str]
    verification: Verification | None
    usage: Usage
    duration_s: float

    @property
    def succeeded(self) -> bool:
        return self.status == "completed"


class Agent:
    def __init__(
        self,
        client: LLMClient,
        config: AgentConfig,
        *,
        registry: ToolRegistry | None = None,
        approve: Approver | None = None,
        observers: Iterable[AgentObserver] = (),
    ) -> None:
        self.client = client
        self.config = config
        self.registry = registry or default_registry()
        self.approve = approve
        self.observers = list(observers)

    def run(self, task: str) -> RunResult:
        started = time.monotonic()
        ctx = ToolContext(Workspace(self.config.workdir), self.config)
        self._notify("on_start", task, self.config)

        usage = Usage()
        tool_calls = 0
        verify_attempts = 0
        verification: Verification | None = None
        seen: Counter[tuple[str, str, int]] = Counter()

        def finish(status: str, message: str, steps: int) -> RunResult:
            result = RunResult(
                status=status,
                message=message,
                steps=steps,
                tool_calls=tool_calls,
                changed_files=sorted(ctx.changed_files),
                verification=verification,
                usage=usage,
                duration_s=time.monotonic() - started,
            )
            self._notify("on_finish", result)
            return result

        session = self.client.start(SYSTEM_PROMPT, self.registry.tools)
        message: Message = task
        for step in range(1, self.config.max_steps + 1):
            try:
                turn = session.send(message)
            except LLMError as exc:
                return finish("error", str(exc), step)
            usage += turn.usage
            self._notify("on_model_turn", step, turn)

            if turn.tool_calls:
                message = [(call, self._execute(call, ctx, seen)) for call in turn.tool_calls]
                tool_calls += len(turn.tool_calls)
                continue

            if not turn.text:
                message = (
                    f"Your last response was empty (finish reason: {turn.finish_reason}). "
                    "Continue the task: call a tool, or reply with your final summary."
                )
                continue

            # The model believes it is done; check its work before accepting that.
            if self.config.verify and ctx.changed_files:
                if self._approved(VERIFY_CALL, ctx):
                    verification = run_verification(ctx)
                else:
                    verification = Verification(passed=None, command=None, declined=True)
                self._notify("on_verification", verification)
                if verification.passed is False:
                    if verify_attempts >= self.config.max_verify_attempts:
                        return finish("verification_failed", turn.text, step)
                    verify_attempts += 1
                    message = (
                        "Automatic verification failed, so the task is not finished:\n"
                        f"{verification.summary(self.config.max_output_chars)}\n"
                        "Fix the cause, then reply with your final summary."
                    )
                    continue
            return finish("completed", turn.text, step)

        return finish("step_limit", "Stopped: reached the step limit.", self.config.max_steps)

    def _execute(
        self, call: ToolCall, ctx: ToolContext, seen: Counter[tuple[str, str, int]]
    ) -> ToolResult:
        self._notify("on_tool_call", call)
        key = (call.name, json.dumps(call.args, sort_keys=True, default=str), ctx.edit_count)
        seen[key] += 1
        tool = self.registry.get(call.name)

        if seen[key] > MAX_IDENTICAL_CALLS:
            result = ToolResult(
                False,
                f"You have made this exact {call.name} call {seen[key]} times and no file has "
                "changed since, so the result will be the same. Try a different approach.",
            )
        elif tool and tool.side_effects and not self._approved(call, ctx):
            result = ToolResult(False, "The user declined this action. Try another approach.")
        else:
            result = self.registry.call(call.name, call.args, ctx)

        self._notify("on_tool_result", call, result)
        return result

    def _approved(self, call: ToolCall, ctx: ToolContext) -> bool:
        if self.approve is None:
            return True
        return self.approve(call, self.registry.preview(call.name, call.args, ctx))

    def _notify(self, event: str, *args: object) -> None:
        for observer in self.observers:
            getattr(observer, event)(*args)
