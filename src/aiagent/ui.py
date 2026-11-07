"""Terminal rendering of an agent run, built on rich."""

from __future__ import annotations

from rich.console import Console, Group
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from aiagent.agent import AgentObserver, RunResult
from aiagent.config import AgentConfig
from aiagent.llm import ModelTurn, ToolCall
from aiagent.tools import ToolResult
from aiagent.verify import Verification

EDIT_TOOLS = frozenset({"apply_patch", "write_file"})
STATUS_STYLE = {"completed": "bold green", "verification_failed": "bold red"}


def describe_call(call: ToolCall, width: int | None = 60) -> str:
    """One-line summary of a tool call; multi-line arguments are reduced to a line count."""
    parts = []
    for key, value in call.args.items():
        if isinstance(value, str) and "\n" in value:
            rendered = f"<{len(value.splitlines())} lines>"
        else:
            rendered = repr(value)
            if width is not None and len(rendered) > width:
                rendered = rendered[: width - 1] + "…"
        parts.append(f"{key}={rendered}")
    return f"{call.name}({', '.join(parts)})"


def print_edit(console: Console, output: str, mark: str = "✓", style: str = "green") -> None:
    """Print an edit tool's "summary line + unified diff" output."""
    summary, _, diff = output.partition("\n")
    console.print(Text(f"  {mark} {summary}", style=style))
    if diff:
        console.print(Syntax(diff, "diff", theme="ansi_dark", background_color="default"))


class RichReporter(AgentObserver):
    def __init__(self, console: Console, verbose: bool = False) -> None:
        self.console = console
        self.verbose = verbose
        self.model = ""

    def on_start(self, task: str, config: AgentConfig) -> None:
        self.model = config.model
        body = Group(
            Text(task, style="bold"),
            Text(f"workspace: {config.workdir}   model: {config.model}", style="dim"),
        )
        self.console.print(Panel(body, title="aiagent", title_align="left", border_style="cyan"))

    def on_model_turn(self, step: int, turn: ModelTurn) -> None:
        if self.verbose:
            self.console.print(
                f"[dim]step {step} · {turn.usage.input_tokens:,} in / "
                f"{turn.usage.output_tokens:,} out tokens[/dim]"
            )
        if turn.text and turn.tool_calls:
            self.console.print(Text(turn.text, style="italic dim"))

    def on_tool_call(self, call: ToolCall) -> None:
        self.console.print(Text("→ ", style="cyan") + Text(describe_call(call)))

    def on_tool_result(self, call: ToolCall, result: ToolResult) -> None:
        if not result.ok:
            self.console.print(Text("  ✗ " + _first_lines(result.output, 6), style="red"))
            return
        if call.name in EDIT_TOOLS:
            print_edit(self.console, result.output)
        elif call.name in {"run_python", "run_tests"}:
            failed = "[exit code 0]" not in result.output
            status = result.output.splitlines()[1] if "\n" in result.output else result.output
            self.console.print(Text(f"  {status}", style="yellow" if failed else "green"))
            if self.verbose or failed:
                self.console.print(Text(_last_lines(result.output, 12), style="dim"))
        elif self.verbose:
            self.console.print(Text(f"  ✓ {len(result.output.splitlines())} lines", style="dim"))

    def on_verification(self, verification: Verification) -> None:
        command = verification.command
        if verification.declined:
            line = Text("⚠ tests not run (declined); change is unverified", style="yellow")
        elif command is None:
            line = Text("⚠ no tests found; change is unverified", style="yellow")
        elif verification.passed:
            line = Text("✓ verified: ", style="green") + Text(command.display_command)
        elif verification.passed is None:
            line = Text("⚠ test command found no tests", style="yellow")
        else:
            line = Text("✗ verification failed: ", style="red") + Text(command.display_command)
        self.console.print(line)

    def on_finish(self, result: RunResult) -> None:
        self.console.print()
        if result.message:
            self.console.print(Panel(Markdown(result.message), title="result", title_align="left"))

        table = Table.grid(padding=(0, 2))
        table.add_column(style="dim")
        table.add_column()
        table.add_row(
            "status", Text(result.status, style=STATUS_STYLE.get(result.status, "yellow"))
        )
        table.add_row("steps", f"{result.steps} model turns, {result.tool_calls} tool calls")
        table.add_row("changed", ", ".join(result.changed_files) or "—")
        usage = result.usage
        table.add_row(
            "tokens",
            f"{usage.input_tokens:,} in ({usage.cached_tokens:,} cached) / "
            f"{usage.output_tokens:,} out",
        )
        cost = usage.cost(self.model)
        if cost is not None:
            table.add_row("cost", f"~${cost:.3f} (estimated at list prices)")
        table.add_row("time", f"{result.duration_s:.1f}s")
        self.console.print(table)


class InteractiveApprover:
    """Ask before each side-effecting tool call: [y]es, [n]o, or [a]ll remaining."""

    def __init__(self, console: Console) -> None:
        self.console = console
        self.approve_all = False

    def __call__(self, call: ToolCall, preview: ToolResult | None) -> bool:
        if self.approve_all:
            return True
        if preview is not None and preview.ok:
            print_edit(self.console, preview.output, mark="proposed:", style="cyan")
        elif preview is not None:
            self.console.print(Text("  this call will fail: " + preview.output, style="red"))
        # A Text prompt is never parsed as markup, so model-chosen arguments show verbatim.
        answer = Prompt.ask(
            Text.assemble("  allow ", (describe_call(call, width=None), "bold"), "?"),
            choices=["y", "n", "a"],
            default="y",
            console=self.console,
        )
        self.approve_all = answer == "a"
        return answer in {"y", "a"}


def _first_lines(text: str, count: int) -> str:
    lines = text.splitlines()
    return "\n    ".join(lines[:count]) + ("\n    …" if len(lines) > count else "")


def _last_lines(text: str, count: int) -> str:
    lines = text.splitlines()[2:]  # skip the "$ command" and status lines
    shown = lines[-count:]
    prefix = ["    …"] if len(lines) > count else []
    return "\n".join([*prefix, *("    " + line for line in shown)])
