"""Tool registry.

Each tool is declared once: its JSON schema is what the model sees, and its
handler is what runs. The LLM adapter turns the schemas into function
declarations, and the registry does argument checking and dispatch, so there
is no hand-written ``if name == ...`` chain to keep in sync.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from aiagent.config import AgentConfig
from aiagent.patching import PatchError
from aiagent.sandbox import SandboxError, Workspace
from aiagent.verify import Verification


class ToolError(Exception):
    """An expected tool failure whose message is shown to the model."""


@dataclass
class ToolContext:
    workspace: Workspace
    config: AgentConfig
    changed_files: set[str] = field(default_factory=set)
    # Bumped on every successful edit; lets the agent tell a repeated call from
    # the same call made again after the files changed.
    edit_count: int = 0
    # The latest test run and the edit_count it saw, so an unchanged tree isn't re-tested.
    last_tests: tuple[int, Verification] | None = None


@dataclass(frozen=True)
class ToolResult:
    ok: bool
    output: str  # what the model sees
    # Structured result for the UI and traces (an Edit, CommandResult or Verification).
    detail: object | None = None


# Handlers return the text for the model, or a ToolResult to attach a detail.
Handler = Callable[..., "str | ToolResult"]


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]  # JSON schema for the arguments object
    handler: Handler
    # Tools with side effects need approval unless the user runs with --yes.
    side_effects: bool = False
    # Optional dry run that describes what the handler would do, shown when asking approval.
    preview: Handler | None = None

    @property
    def required(self) -> list[str]:
        return list(self.parameters.get("required", []))

    @property
    def properties(self) -> dict[str, Any]:
        return dict(self.parameters.get("properties", {}))


def schema(properties: dict[str, Any], required: Iterable[str] = ()) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": list(required)}


class ToolRegistry:
    def __init__(self, tools: Iterable[Tool]) -> None:
        self._tools = {tool.name: tool for tool in tools}

    @property
    def tools(self) -> list[Tool]:
        return list(self._tools.values())

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def call(self, name: str, args: Mapping[str, Any], ctx: ToolContext) -> ToolResult:
        return self._invoke(name, args, ctx, dry_run=False)

    def preview(self, name: str, args: Mapping[str, Any], ctx: ToolContext) -> ToolResult | None:
        """Dry-run a call to show what it would do, or None if the tool has no preview."""
        tool = self._tools.get(name)
        if tool is None or tool.preview is None:
            return None
        return self._invoke(name, args, ctx, dry_run=True)

    def _invoke(
        self, name: str, args: Mapping[str, Any], ctx: ToolContext, *, dry_run: bool
    ) -> ToolResult:
        tool = self._tools.get(name)
        if tool is None:
            available = ", ".join(sorted(self._tools))
            return ToolResult(False, f"Unknown tool '{name}'. Available tools: {available}.")

        missing = [arg for arg in tool.required if args.get(arg) is None]
        if missing:
            return ToolResult(False, f"{name}: missing required argument(s): {', '.join(missing)}.")
        unknown = sorted(set(args) - set(tool.properties))
        if unknown:
            return ToolResult(False, f"{name}: unexpected argument(s): {', '.join(unknown)}.")

        handler = tool.preview if dry_run and tool.preview else tool.handler
        kwargs = {key: value for key, value in args.items() if value is not None}
        try:
            result = handler(ctx, **kwargs)
        except (ToolError, SandboxError, PatchError) as exc:
            return ToolResult(False, str(exc))
        except Exception as exc:  # a bug in a tool must not kill the agent loop
            return ToolResult(False, f"{name} failed: {type(exc).__name__}: {exc}")
        return result if isinstance(result, ToolResult) else ToolResult(True, result)


def default_registry() -> ToolRegistry:
    from aiagent.tools import edit, files, run

    return ToolRegistry([*files.TOOLS, *edit.TOOLS, *run.TOOLS])
