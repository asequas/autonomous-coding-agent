"""Benchmark the agent on small, realistic coding tasks graded by hidden tests.

Each task in evals/tasks/<id>/ contains:

    task.toml   the prompt given to the agent, plus a `kind` label
    repo/       the project the agent works on (copied to a temp dir per trial)
    hidden/     tests the agent never sees; copied in after it finishes to grade the result
    solution/   a reference solution, used by --validate to check the task itself

Usage:

    python evals/run_evals.py                       # every task, one trial each
    python evals/run_evals.py --trials 3 --tasks fix-pagination parse-duration
    python evals/run_evals.py --validate            # check tasks; no API calls
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import shutil
import sys
import tempfile
import time
import tomllib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from rich.console import Console

from aiagent.agent import Agent, AgentObserver
from aiagent.config import AgentConfig, default_model, load_api_key
from aiagent.llm import GeminiClient, LLMClient
from aiagent.process import CommandResult, run_command
from aiagent.sandbox import Workspace
from aiagent.tools import ToolContext
from aiagent.trace import JsonlTrace
from aiagent.ui import RichReporter
from aiagent.verify import run_verification

EVALS_DIR = Path(__file__).resolve().parent
TASKS_DIR = EVALS_DIR / "tasks"
RESULTS_DIR = EVALS_DIR / "results"
HIDDEN_DIR_NAME = "_hidden_tests"


@dataclass(frozen=True)
class Task:
    id: str
    kind: str
    prompt: str
    path: Path


@dataclass(frozen=True)
class Outcome:
    task: str
    kind: str
    trial: int
    passed: bool
    agent_status: str
    steps: int
    tool_calls: int
    input_tokens: int
    cached_tokens: int
    output_tokens: int
    cost_usd: float | None
    duration_s: float


def load_tasks(selected: Sequence[str] = ()) -> list[Task]:
    tasks = []
    for path in sorted(p for p in TASKS_DIR.iterdir() if (p / "task.toml").is_file()):
        meta = tomllib.loads((path / "task.toml").read_text(encoding="utf-8"))
        tasks.append(Task(path.name, meta["kind"], meta["prompt"].strip(), path))
    if selected:
        unknown = set(selected) - {task.id for task in tasks}
        if unknown:
            raise SystemExit(f"Unknown task(s): {', '.join(sorted(unknown))}")
        tasks = [task for task in tasks if task.id in selected]
    return tasks


def prepare(task: Task, dest: Path, *, with_solution: bool = False) -> Path:
    shutil.copytree(task.path / "repo", dest)
    if with_solution:
        shutil.copytree(task.path / "solution", dest, dirs_exist_ok=True)
    return dest


def run_hidden_tests(task: Task, workdir: Path) -> CommandResult:
    shutil.copytree(task.path / "hidden", workdir / HIDDEN_DIR_NAME, dirs_exist_ok=True)
    argv = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", HIDDEN_DIR_NAME]
    return run_command(argv, workdir, timeout=120)


def validate(tasks: Sequence[Task], console: Console) -> bool:
    """Each task's hidden tests must fail on the starting repo and pass on the solution."""
    all_ok = True
    for task in tasks:
        with tempfile.TemporaryDirectory() as tmp:
            before = run_hidden_tests(task, prepare(task, Path(tmp) / "start"))
            solved = prepare(task, Path(tmp) / "solved", with_solution=True)
            after = run_hidden_tests(task, solved)
            ctx = ToolContext(Workspace(solved), AgentConfig(workdir=solved))
            visible = run_verification(ctx)
        problems = []
        if before.ok:
            problems.append("hidden tests already pass on the starting repo")
        if not after.ok:
            problems.append("hidden tests fail on the reference solution\n" + after.format(4000))
        if visible.passed is False:
            problems.append("visible tests fail on the reference solution")
        status = "[green]ok[/green]" if not problems else "[red]FAIL[/red]"
        console.print(f"{status}  {task.id}")
        for problem in problems:
            console.print(f"      {problem}")
        all_ok = all_ok and not problems
    return all_ok


def run_trial(
    task: Task,
    client: LLMClient,
    model: str,
    trial: int,
    console: Console,
    *,
    verbose: bool = False,
    traces: Path | None = None,
) -> Outcome:
    with tempfile.TemporaryDirectory() as tmp:
        workdir = prepare(task, Path(tmp) / "repo")
        config = AgentConfig(workdir=workdir, model=model)
        observers: list[AgentObserver] = [RichReporter(console, verbose=True)] if verbose else []
        trace = JsonlTrace(traces / f"{task.id}-{trial}.jsonl") if traces else None
        if trace:
            observers.append(trace)
        try:
            result = Agent(client, config, observers=observers).run(task.prompt)
        finally:
            if trace:
                trace.close()
        check = run_hidden_tests(task, workdir)
    return Outcome(
        task=task.id,
        kind=task.kind,
        trial=trial,
        passed=check.ok,
        agent_status=result.status,
        steps=result.steps,
        tool_calls=result.tool_calls,
        input_tokens=result.usage.input_tokens,
        cached_tokens=result.usage.cached_tokens,
        output_tokens=result.usage.output_tokens,
        cost_usd=result.usage.cost(model),
        duration_s=round(result.duration_s, 1),
    )


def summarize(outcomes: Sequence[Outcome], model: str, trials: int) -> str:
    rows = [
        "| Task | Kind | Passed | Avg steps | Avg tokens (in / out) | Avg cost | Avg time |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for task in dict.fromkeys(o.task for o in outcomes):
        runs = [o for o in outcomes if o.task == task]
        n = len(runs)
        rows.append(
            f"| `{task}` | {runs[0].kind} | {sum(o.passed for o in runs)}/{n} "
            f"| {sum(o.steps for o in runs) / n:.1f} "
            f"| {sum(o.input_tokens for o in runs) / n:,.0f} / "
            f"{sum(o.output_tokens for o in runs) / n:,.0f} "
            f"| {_dollars(sum(o.cost_usd or 0 for o in runs) / n)} "
            f"| {sum(o.duration_s for o in runs) / n:.0f}s |"
        )
    passed = sum(o.passed for o in outcomes)
    total = len(outcomes)
    total_cost = sum(o.cost_usd or 0 for o in outcomes)
    date = time.strftime("%Y-%m-%d")
    return "\n".join(
        [
            f"## `{model}`: {passed}/{total} passed ({passed / total:.0%})",
            "",
            f"{trials} trial(s) per task, run on {date}. A task passes when its hidden tests pass. "
            f"Total cost {_dollars(total_cost)}, estimated at list prices.",
            "",
            *rows,
            "",
        ]
    )


def _dollars(value: float) -> str:
    return f"${value:.3f}"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--tasks", nargs="*", default=[], help="Task ids (default: all).")
    parser.add_argument("--trials", type=int, default=1, help="Runs per task.")
    parser.add_argument("-m", "--model", default=None, help="Gemini model to evaluate.")
    parser.add_argument("--validate", action="store_true", help="Check the tasks themselves.")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show every agent step.")
    parser.add_argument("--traces", type=Path, help="Write a JSONL trace per trial to this dir.")
    args = parser.parse_args(argv)

    console = Console()
    tasks = load_tasks(args.tasks)
    if args.validate:
        return 0 if validate(tasks, console) else 1

    api_key = load_api_key()
    if not api_key:
        console.print("[red]GEMINI_API_KEY is not set.[/red]")
        return 2
    model = args.model or default_model()
    client = GeminiClient(api_key, model, max_retries=8)

    outcomes: list[Outcome] = []
    for task in tasks:
        for trial in range(1, args.trials + 1):
            outcome = run_trial(
                task, client, model, trial, console, verbose=args.verbose, traces=args.traces
            )
            outcomes.append(outcome)
            mark = "[green]✓[/green]" if outcome.passed else "[red]✗[/red]"
            console.print(
                f"{mark} {task.id:<22} trial {trial}  {outcome.agent_status:<20} "
                f"{outcome.steps:>2} steps  {outcome.duration_s:>5.0f}s  "
                f"{_dollars(outcome.cost_usd or 0)}"
            )

    report = summarize(outcomes, model, args.trials)
    RESULTS_DIR.mkdir(exist_ok=True)
    # Not Path.with_suffix: "gemini-3.8-flash" would lose ".8-flash" as if it were an extension.
    name = model.replace("/", "_")
    (RESULTS_DIR / f"{name}.md").write_text(report, encoding="utf-8")
    (RESULTS_DIR / f"{name}.json").write_text(
        json.dumps([dataclasses.asdict(o) for o in outcomes], indent=2) + "\n", encoding="utf-8"
    )

    console.print(report, markup=False)
    console.print(f"Saved evals/results/{name}.md and .json", style="dim")
    return 0 if all(o.passed for o in outcomes) else 1


if __name__ == "__main__":
    sys.exit(main())
