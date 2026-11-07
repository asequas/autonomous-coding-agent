"""Verification: decide whether the agent's work is done by running the project's tests."""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass

from aiagent.process import CommandResult, run_command
from aiagent.tools import ToolContext

PYTEST_NO_TESTS_COLLECTED = 5


@dataclass(frozen=True)
class Verification:
    passed: bool | None  # None: there was nothing to run
    command: CommandResult | None

    def summary(self, max_chars: int) -> str:
        if self.command is None:
            return "No test command found; the change could not be verified."
        return self.command.format(max_chars)


def detect_test_command(ctx: ToolContext) -> tuple[str, ...] | None:
    """Pick a test command from the files in the workspace.

    pytest-style names (``test_*.py``, ``*_test.py``, ``conftest.py``) use pytest
    when it is installed; any other ``test*.py`` falls back to unittest discovery.
    """
    if ctx.config.test_command is not None:
        return ctx.config.test_command

    names = [path.name for path in ctx.workspace.iter_files() if path.suffix == ".py"]
    pytest_style = any(
        name.startswith("test_") or name.endswith("_test.py") or name == "conftest.py"
        for name in names
    )
    if pytest_style and importlib.util.find_spec("pytest") is not None:
        return (sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider")
    if any(name.startswith("test") for name in names):
        return (sys.executable, "-m", "unittest", "discover", "-p", "test*.py")
    return None


def run_verification(ctx: ToolContext) -> Verification:
    argv = detect_test_command(ctx)
    if argv is None:
        return Verification(passed=None, command=None)
    result = run_command(argv, ctx.workspace.root, ctx.config.command_timeout)
    if result.exit_code == PYTEST_NO_TESTS_COLLECTED and "pytest" in argv:
        return Verification(passed=None, command=result)
    return Verification(passed=result.ok, command=result)
