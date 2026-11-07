"""Execution tools: run a Python file or the project's tests."""

from __future__ import annotations

import sys

from aiagent.process import run_command
from aiagent.tools import Tool, ToolContext, ToolError, schema
from aiagent.verify import run_verification


def run_python(ctx: ToolContext, path: str, args: list[str] | None = None) -> str:
    target = ctx.workspace.resolve(path)
    if not target.is_file() or target.suffix != ".py":
        raise ToolError(f"'{path}' is not a Python file.")
    argv = [sys.executable, ctx.workspace.relative(target), *(str(arg) for arg in args or [])]
    result = run_command(argv, ctx.workspace.root, ctx.config.command_timeout)
    return result.format(ctx.config.max_output_chars)


def run_tests(ctx: ToolContext) -> str:
    return run_verification(ctx).summary(ctx.config.max_output_chars)


TOOLS = [
    Tool(
        name="run_python",
        description=(
            "Run a Python file from the workspace root and return its exit code, stdout and "
            "stderr. Use it to reproduce bugs and check behaviour."
        ),
        parameters=schema(
            {
                "path": {"type": "string", "description": "Python file relative to the workspace."},
                "args": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Command-line arguments.",
                },
            },
            required=["path"],
        ),
        handler=run_python,
        side_effects=True,
    ),
    Tool(
        name="run_tests",
        description=(
            "Run the project's test suite (auto-detected pytest or unittest) and return "
            "the results. The same command is used to verify your work when you finish."
        ),
        parameters=schema({}),
        handler=run_tests,
        side_effects=True,
    ),
]
