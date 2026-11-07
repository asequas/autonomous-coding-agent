import sys

from conftest import make_ctx, write

from aiagent.tools import ToolContext
from aiagent.verify import PYTEST_ARGV, UNITTEST_ARGV, detect_test_command, run_verification


def detect(ctx: ToolContext) -> tuple[str, ...] | None:
    return detect_test_command(ctx.workspace, ctx.config)


def verify(ctx: ToolContext):  # type: ignore[no-untyped-def]
    return run_verification(ctx.workspace, ctx.config)


def test_detects_pytest_for_pytest_style_tests(ctx: ToolContext) -> None:
    write(ctx, "tests/test_x.py", "def test_x():\n    assert True\n")
    assert detect(ctx) == PYTEST_ARGV


def test_falls_back_to_unittest_for_other_test_files(ctx: ToolContext) -> None:
    write(ctx, "tests.py", "import unittest\n")
    assert detect(ctx) == UNITTEST_ARGV


def test_no_tests_means_nothing_to_run(ctx: ToolContext) -> None:
    write(ctx, "main.py", "print(1)\n")
    verification = verify(ctx)
    assert verification.status == "no_tests" and verification.command is None


def test_explicit_test_command_wins(tmp_path) -> None:  # type: ignore[no-untyped-def]
    ctx = make_ctx(tmp_path, test_command=(sys.executable, "-c", "raise SystemExit(3)"))
    verification = verify(ctx)
    assert verification.status == "failed"
    assert verification.command is not None and verification.command.exit_code == 3


def test_passing_and_failing_suites(ctx: ToolContext) -> None:
    write(ctx, "calc.py", "def add(a, b):\n    return a + b\n")
    write(
        ctx, "test_calc.py", "from calc import add\n\ndef test_add():\n    assert add(2, 2) == 4\n"
    )
    assert verify(ctx).status == "passed"

    write(ctx, "calc.py", "def add(a, b):\n    return a - b\n")
    failed = verify(ctx)
    assert failed.status == "failed"
    assert "assert 0 == 4" in failed.summary(8000)


def test_pytest_without_collected_tests_counts_as_no_tests(ctx: ToolContext) -> None:
    write(ctx, "conftest.py", "")
    verification = verify(ctx)
    assert verification.status == "no_tests" and verification.command is not None
