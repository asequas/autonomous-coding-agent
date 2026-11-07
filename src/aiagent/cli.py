"""Command-line entry point: ``aiagent run "<task>"``."""

from __future__ import annotations

import argparse
import shlex
import sys
from pathlib import Path

from rich.console import Console

from aiagent import __version__
from aiagent.agent import Agent, AgentObserver
from aiagent.config import AgentConfig, default_model, load_api_key
from aiagent.llm import GeminiClient
from aiagent.sandbox import SandboxError, Workspace
from aiagent.trace import JsonlTrace
from aiagent.ui import InteractiveApprover, RichReporter


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aiagent",
        description="An autonomous coding agent that edits code with verified patches.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser("run", help="Run the agent on a task.")
    run.add_argument("task", help="What the agent should do, in plain English.")
    run.add_argument(
        "-C", "--workdir", type=Path, default=Path("."), help="Project directory (the sandbox)."
    )
    run.add_argument("-m", "--model", help="Gemini model (default: $AIAGENT_MODEL or built-in).")
    run.add_argument("--max-steps", type=int, default=30, help="Maximum model turns.")
    run.add_argument(
        "--test-command",
        help="Command that verifies the work, e.g. 'python -m pytest -q'. Auto-detected if unset.",
    )
    run.add_argument("--no-verify", action="store_true", help="Skip test-based verification.")
    run.add_argument(
        "-y", "--yes", action="store_true", help="Don't ask before edits and commands."
    )
    run.add_argument("--trace", type=Path, help="Write a JSONL trace of the run to this file.")
    run.add_argument("--record", type=Path, help="Save the terminal output as an SVG.")
    run.add_argument("-v", "--verbose", action="store_true", help="Show more detail.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    console = Console(record=args.record is not None)

    api_key = load_api_key()
    if not api_key:
        console.print("[red]GEMINI_API_KEY is not set.[/red] Add it to your environment or .env.")
        return 2
    if not args.yes and not sys.stdin.isatty():
        console.print("[red]stdin is not a terminal.[/red] Pass --yes to run non-interactively.")
        return 2
    try:
        Workspace(args.workdir)
    except SandboxError as exc:
        console.print(f"[red]{exc}[/red]")
        return 2

    config = AgentConfig(
        workdir=args.workdir,
        model=args.model or default_model(),
        max_steps=args.max_steps,
        test_command=tuple(shlex.split(args.test_command)) if args.test_command else None,
        verify=not args.no_verify,
    )
    trace = JsonlTrace(args.trace) if args.trace else None
    observers: list[AgentObserver] = [RichReporter(console, args.verbose)]
    if trace:
        observers.append(trace)

    agent = Agent(
        GeminiClient(api_key, config.model),
        config,
        approve=None if args.yes else InteractiveApprover(console),
        observers=observers,
    )
    try:
        result = agent.run(args.task)
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/yellow]")
        return 130
    finally:
        if trace:
            trace.close()
        if args.record:
            console.save_svg(str(args.record), title="aiagent")
    return 0 if result.succeeded else 1
