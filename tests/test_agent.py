from typing import Any

import pytest
from conftest import make_ctx, write

from aiagent import agent as agent_module
from aiagent.agent import Agent, AgentObserver
from aiagent.config import AgentConfig
from aiagent.llm import LLMError, Message, ModelTurn, ScriptedClient, ToolCall, Usage
from aiagent.tools import ToolContext, ToolResult
from aiagent.tools.edit import Edit

BUGGY = "def add(a, b):\n    return a - b\n"
TEST = "from calc import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n"
FIX = "@@ -1,2 +1,2 @@\n def add(a, b):\n-    return a - b\n+    return a + b\n"


def calls(*specs: tuple[str, dict[str, Any]]) -> ModelTurn:
    return ModelTurn(tool_calls=[ToolCall(name, args) for name, args in specs], usage=Usage(10, 5))


def final(text: str = "Done.") -> ModelTurn:
    return ModelTurn(text=text, usage=Usage(10, 5))


def patch(text: str) -> ModelTurn:
    return calls(("apply_patch", {"path": "calc.py", "patch": text}))


def project(tmp_path) -> ToolContext:  # type: ignore[no-untyped-def]
    ctx = make_ctx(tmp_path)
    write(ctx, "calc.py", BUGGY)
    write(ctx, "test_calc.py", TEST)
    return ctx


def tool_results(message: Message) -> list[Any]:
    assert not isinstance(message, str)
    return [result for _, result in message]


class Recorder(AgentObserver):
    def __init__(self) -> None:
        self.events: list[str] = []

    def on_tool_call(self, call: ToolCall) -> None:
        self.events.append(f"call:{call.name}")

    def on_verification(self, verification: Any) -> None:
        self.events.append(f"verify:{verification.status}")


def test_end_to_end_bug_fix(tmp_path) -> None:  # type: ignore[no-untyped-def]
    ctx = project(tmp_path)
    client = ScriptedClient(
        [
            calls(("list_files", {})),
            calls(("read_file", {"path": "calc.py"})),
            patch(FIX),
            calls(("run_tests", {})),
            final("Fixed add() to use +."),
        ]
    )
    recorder = Recorder()
    result = Agent(client, ctx.config, observers=[recorder]).run("Fix the failing test.")

    assert result.status == "completed", result
    assert result.message == "Fixed add() to use +."
    assert result.changed_files == ["calc.py"]
    assert result.verification is not None and result.verification.status == "passed"
    assert result.steps == 5 and result.tool_calls == 4
    assert result.usage == Usage(50, 25)
    assert (ctx.workspace.root / "calc.py").read_text() == "def add(a, b):\n    return a + b\n"
    assert recorder.events[-1] == "verify:passed"
    assert client.received[0] == "Fix the failing test."
    assert all(r.ok for msg in client.received[1:] for r in tool_results(msg))


def test_failed_verification_is_fed_back_to_the_model(tmp_path) -> None:  # type: ignore[no-untyped-def]
    ctx = project(tmp_path)
    harmless = "@@ -1,1 +1,1 @@\n-def add(a, b):\n+def add(a, b):  # adds\n"
    client = ScriptedClient(
        [
            patch(harmless),
            final(),
            patch(FIX.replace("def add(a, b):", "def add(a, b):  # adds")),
            final(),
        ]
    )
    result = Agent(client, ctx.config).run("Fix it.")

    assert result.status == "completed"
    feedback = client.received[2]
    assert isinstance(feedback, str)
    assert feedback.startswith("Automatic verification failed")
    assert "assert -1 == 5" in feedback


def test_gives_up_after_repeated_verification_failures(tmp_path) -> None:  # type: ignore[no-untyped-def]
    root = tmp_path / "p"
    root.mkdir()
    ctx = make_ctx(root, max_verify_attempts=1)
    write(ctx, "calc.py", BUGGY)
    write(ctx, "test_calc.py", TEST)
    harmless = " def add(a, b):\n-    return a - b\n+    return a - b  # still wrong\n"
    client = ScriptedClient([patch(harmless), final(), final()])
    result = Agent(client, ctx.config).run("Fix it.")
    assert result.status == "verification_failed"


def test_no_verification_when_nothing_changed(tmp_path) -> None:  # type: ignore[no-untyped-def]
    ctx = project(tmp_path)
    client = ScriptedClient([calls(("read_file", {"path": "calc.py"})), final("add() subtracts.")])
    result = Agent(client, ctx.config).run("What does add do?")
    assert result.status == "completed"
    assert result.verification is None


def test_step_limit(tmp_path) -> None:  # type: ignore[no-untyped-def]
    ctx = make_ctx(tmp_path, max_steps=2)
    client = ScriptedClient([calls(("list_files", {}))] * 3)
    result = Agent(client, ctx.config).run("Loop forever.")
    assert result.status == "step_limit" and result.steps == 2


def test_identical_calls_are_short_circuited(tmp_path) -> None:  # type: ignore[no-untyped-def]
    ctx = project(tmp_path)
    read = calls(("read_file", {"path": "calc.py"}))
    client = ScriptedClient([read, read, read, final()])
    Agent(client, ctx.config).run("Read it.")
    third = tool_results(client.received[3])[0]
    assert not third.ok and "exact read_file call 3 times" in third.output


def test_identical_calls_are_allowed_after_an_edit(tmp_path) -> None:  # type: ignore[no-untyped-def]
    ctx = project(tmp_path)
    run = calls(("run_tests", {}))
    client = ScriptedClient([run, run, patch(FIX), run, final()])
    Agent(client, ctx.config).run("Fix it.")
    assert tool_results(client.received[4])[0].ok


def test_declined_actions_are_not_executed(tmp_path) -> None:  # type: ignore[no-untyped-def]
    ctx = project(tmp_path)
    client = ScriptedClient([patch(FIX), final()])
    result = Agent(client, ctx.config, approve=lambda call, preview: False).run("Fix it.")
    declined = tool_results(client.received[1])[0]
    assert not declined.ok and "declined" in declined.output
    assert (ctx.workspace.root / "calc.py").read_text() == BUGGY
    assert result.changed_files == []


def test_read_only_tools_skip_approval(tmp_path) -> None:  # type: ignore[no-untyped-def]
    ctx = project(tmp_path)
    asked: list[str] = []

    def approve(call: ToolCall, preview: ToolResult | None) -> bool:
        asked.append(call.name)
        return True

    client = ScriptedClient([calls(("read_file", {"path": "calc.py"}), ("run_tests", {})), final()])
    Agent(client, ctx.config, approve=approve).run("Look.")
    assert asked == ["run_tests"]


def test_empty_responses_get_a_nudge(tmp_path) -> None:  # type: ignore[no-untyped-def]
    ctx = project(tmp_path)
    client = ScriptedClient([ModelTurn(finish_reason="MALFORMED_FUNCTION_CALL"), final()])
    result = Agent(client, ctx.config).run("Hi.")
    assert result.status == "completed"
    nudge = client.received[1]
    assert isinstance(nudge, str) and "MALFORMED_FUNCTION_CALL" in nudge


def test_llm_errors_end_the_run_cleanly(tmp_path) -> None:  # type: ignore[no-untyped-def]
    class Broken(ScriptedClient):
        def send(self, message: Message) -> ModelTurn:
            raise LLMError("quota exceeded")

    result = Agent(Broken([]), AgentConfig(workdir=tmp_path)).run("Hi.")
    assert result.status == "error" and result.message == "quota exceeded"


def test_verification_needs_approval(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[no-untyped-def]
    """Running the tests executes repo code, so declining run_tests must also skip verification."""
    ctx = project(tmp_path)

    def must_not_run(*_args: object) -> None:
        raise AssertionError("verification ran without approval")

    monkeypatch.setattr(agent_module, "run_verification", must_not_run)
    client = ScriptedClient([patch(FIX), final()])
    result = Agent(client, ctx.config, approve=lambda call, preview: call.name != "run_tests").run(
        "Fix it."
    )

    assert result.status == "completed"
    assert result.verification is not None and result.verification.status == "declined"
    assert (ctx.workspace.root / "calc.py").read_text().endswith("return a + b\n")


def test_approver_sees_a_preview_before_anything_is_written(tmp_path) -> None:  # type: ignore[no-untyped-def]
    ctx = project(tmp_path)
    previews: list[ToolResult | None] = []

    def approve(call: ToolCall, preview: ToolResult | None) -> bool:
        previews.append(preview)
        if call.name == "apply_patch":
            assert (ctx.workspace.root / "calc.py").read_text() == BUGGY  # not applied yet
        return True

    client = ScriptedClient([patch(FIX), final()])
    Agent(client, ctx.config, approve=approve).run("Fix it.")

    edit_preview, verify_preview = previews
    assert edit_preview is not None and edit_preview.ok
    assert isinstance(edit_preview.detail, Edit)
    assert "+    return a + b" in edit_preview.detail.diff
    assert verify_preview is None  # run_tests has nothing to preview


def test_recent_passing_test_run_is_reused_for_verification(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    ctx = project(tmp_path)

    def must_not_run(*_args: object) -> None:
        raise AssertionError("tests were run again although nothing changed")

    # Only the agent's own verification is patched; the run_tests tool still runs them.
    monkeypatch.setattr(agent_module, "run_verification", must_not_run)
    client = ScriptedClient([patch(FIX), calls(("run_tests", {})), final()])
    result = Agent(client, ctx.config).run("Fix it.")
    assert result.verification is not None and result.verification.status == "passed"


def test_calls_that_would_fail_are_not_put_to_the_user(tmp_path) -> None:  # type: ignore[no-untyped-def]
    ctx = project(tmp_path)
    asked: list[str] = []

    def approve(call: ToolCall, preview: ToolResult | None) -> bool:
        asked.append(call.name)
        return True

    bad = patch("-this line is not in the file\n+x\n")
    client = ScriptedClient([bad, final()])
    Agent(client, ctx.config, approve=approve).run("Fix it.")
    failed = tool_results(client.received[1])[0]
    assert not failed.ok and "does not match" in failed.output
    assert asked == []


def test_files_changed_by_run_python_invalidate_the_last_test_run(tmp_path) -> None:  # type: ignore[no-untyped-def]
    ctx = project(tmp_path)
    write(ctx, "fix.py", "open('calc.py', 'w').write('def add(a, b):\\n    return 0\\n')\n")
    client = ScriptedClient(
        [patch(FIX), calls(("run_tests", {})), calls(("run_python", {"path": "fix.py"})), final()]
        + [final()] * 3
    )
    result = Agent(client, ctx.config).run("Fix it.")
    # The earlier passing run is stale, so the tests run again and catch the breakage.
    assert result.status == "verification_failed"
