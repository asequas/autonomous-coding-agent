import sys

from conftest import make_ctx, write

from aiagent.tools import ToolContext
from aiagent.verify import detect_test_command, run_verification


def test_detects_pytest_for_pytest_style_tests(ctx: ToolContext) -> None:
    write(ctx, "tests/test_x.py", "def test_x():\n    assert True\n")
    assert detect_test_command(ctx) == (
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "-p",
        "no:cacheprovider",
    )


def test_falls_back_to_unittest_for_other_test_files(ctx: ToolContext) -> None:
    write(ctx, "tests.py", "import unittest\n")
    assert detect_test_command(ctx) == (
        sys.executable,
        "-m",
        "unittest",
        "discover",
        "-p",
        "test*.py",
    )


def test_no_tests_means_nothing_to_run(ctx: ToolContext) -> None:
    write(ctx, "main.py", "print(1)\n")
    verification = run_verification(ctx)
    assert verification.passed is None and verification.command is None


def test_explicit_test_command_wins(tmp_path) -> None:  # type: ignore[no-untyped-def]
    ctx = make_ctx(tmp_path, test_command=(sys.executable, "-c", "raise SystemExit(3)"))
    verification = run_verification(ctx)
    assert verification.passed is False
    assert verification.command is not None and verification.command.exit_code == 3


def test_passing_and_failing_suites(ctx: ToolContext) -> None:
    write(ctx, "calc.py", "def add(a, b):\n    return a + b\n")
    write(
        ctx, "test_calc.py", "from calc import add\n\ndef test_add():\n    assert add(2, 2) == 4\n"
    )
    assert run_verification(ctx).passed is True

    write(ctx, "calc.py", "def add(a, b):\n    return a - b\n")
    failed = run_verification(ctx)
    assert failed.passed is False
    assert "assert 0 == 4" in failed.summary(8000)
