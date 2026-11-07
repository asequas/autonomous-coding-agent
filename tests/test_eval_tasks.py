"""The benchmark is only meaningful if every task is actually solvable and actually graded."""

import importlib.util
import sys
from pathlib import Path

from rich.console import Console

RUNNER = Path(__file__).resolve().parents[1] / "evals" / "run_evals.py"


def load_runner():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location("run_evals", RUNNER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses look their module up here
    spec.loader.exec_module(module)
    return module


def test_every_task_is_valid() -> None:
    runner = load_runner()
    tasks = runner.load_tasks()
    assert len(tasks) >= 8
    console = Console(record=True, width=200)
    assert runner.validate(tasks, console), console.export_text()
