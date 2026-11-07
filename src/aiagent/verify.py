"""Verification: decide whether the agent's work is done by running the project's tests."""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass
from typing import Literal

from aiagent.config import AgentConfig
from aiagent.process import CommandResult, run_command
from aiagent.sandbox import Workspace

PYTEST_ARGV = (sys.executable, "-m", "pytest", "-q", "--tb=short", "-p", "no:cacheprovider")
UNITTEST_ARGV = (sys.executable, "-m", "unittest", "discover", "-p", "test*.py")
PYTEST_NO_TESTS_COLLECTED = 5
UNITTEST_NO_TESTS = "Ran 0 tests"

Status = Literal["passed", "failed", "no_tests", "declined"]

SUMMARIES: dict[Status, str] = {
    "no_tests": "No tests found; the change could not be verified.",
    "declined": "Verification skipped: the user declined to run the tests.",
}


@dataclass(frozen=True)
class Verification:
    status: Status
    command: CommandResult | None = None

    def summary(self, max_chars: int) -> str:
        if self.command is not None and self.status in ("passed", "failed"):
            return self.command.format(max_chars)
        return SUMMARIES.get(self.status, "No tests found; the change could not be verified.")


def detect_test_command(workspace: Workspace, config: AgentConfig) -> tuple[str, ...] | None:
    """Pick a test command from the files in the workspace.

    pytest-style names (``test_*.py``, ``*_test.py``, ``conftest.py``) use pytest
    when it is installed; any other ``test*.py`` falls back to unittest discovery.
    """
    if config.test_command is not None:
        return config.test_command

    names = [path.name for path in workspace.iter_files() if path.suffix == ".py"]
    pytest_style = any(
        name.startswith("test_") or name.endswith("_test.py") or name == "conftest.py"
        for name in names
    )
    if pytest_style and importlib.util.find_spec("pytest") is not None:
        return PYTEST_ARGV
    if any(name.startswith("test") for name in names):
        return UNITTEST_ARGV
    return None


def _ran_no_tests(argv: tuple[str, ...], result: CommandResult) -> bool:
    # Covers custom --test-command values too, e.g. "uv run pytest".
    if "pytest" in argv and result.exit_code == PYTEST_NO_TESTS_COLLECTED:
        return True
    return "unittest" in argv and UNITTEST_NO_TESTS in result.stderr


def run_verification(workspace: Workspace, config: AgentConfig) -> Verification:
    argv = detect_test_command(workspace, config)
    if argv is None:
        return Verification("no_tests")
    result = run_command(argv, workspace.root, config.command_timeout)
    if _ran_no_tests(argv, result):
        return Verification("no_tests", result)
    return Verification("passed" if result.ok else "failed", result)
