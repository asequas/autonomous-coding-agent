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
from aiagent.config import AgentConfig, format_usd
from aiagent.llm import ModelTurn, ToolCall
from aiagent.process import CommandResult
from aiagent.tools import ToolResult
from aiagent.tools.edit import Edit
from aiagent.verify import Verification

STATUS_STYLE = {"completed": "bold green", "verification_failed": "bold red"}
MAX_DIFF_LINES = 80


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


def print_edit(console: Console, edit: Edit, mark: str = "✓", style: str = "green") -> None:
    console.print(Text(f"  {mark} {edit.summary()}", style=style))
    lines = edit.diff.splitlines()
    if len(lines) > MAX_DIFF_LINES:
        lines = [*lines[:MAX_DIFF_LINES], f"… {len(lines) - MAX_DIFF_LINES} more lines"]
    console.print(Syntax("\n".join(lines), "diff", theme="ansi_dark", background_color="default"))


def print_command(console: Console, command: CommandResult, verbose: bool) -> None:
    console.print(Text(f"  [{command.status}]", style="green" if command.ok else "yellow"))
    if verbose or not command.ok:
        output = (command.stdout + command.stderr).rstrip().splitlines()[-12:]
        console.print(Text("\n".join("    " + line for line in output), style="dim"))


def verification_line(verification: Verification) -> Text:
    command = verification.command
    shown = Text(command.display_command) if command else Text()
    if verification.status == "passed":
        return Text("✓ verified: ", style="green") + shown
    if verification.status == "failed":
        return Text("✗ verification failed: ", style="red") + shown
    if verification.status == "declined":
        return Text("⚠ tests not run (declined); change is unverified", style="yellow")
    return Text("⚠ no tests found; change is unverified", style="yellow")


class RichReporter(AgentObserver):
    def __init__(self, console: Console, verbose: bool = False) -> None:
        self.console = console
        self.verbose = verbose

    def on_start(self, task: str, config: AgentConfig, model: str) -> None:
        body = Group(
            Text(task, style="bold"),
            Text(f"workspace: {config.workdir}   model: {model}", style="dim"),
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
        detail = result.detail
        if not result.ok:
            self.console.print(Text("  ✗ " + _first_lines(result.output, 6), style="red"))
        elif isinstance(detail, Edit):
            print_edit(self.console, detail)
        elif isinstance(detail, CommandResult):
            print_command(self.console, detail, self.verbose)
        elif isinstance(detail, Verification):
            self.console.print(Text("  ") + verification_line(detail))
            if detail.command and (self.verbose or detail.status == "failed"):
                print_command(self.console, detail.command, verbose=True)
        elif self.verbose:
            self.console.print(Text(f"  ✓ {len(result.output.splitlines())} lines", style="dim"))

    def on_verification(self, verification: Verification) -> None:
        self.console.print(verification_line(verification))

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
        cost = usage.cost(result.model)
        if cost is not None:
            table.add_row("cost", f"~{format_usd(cost)} (estimated at list prices)")
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
        if preview is not None and isinstance(preview.detail, Edit):
            print_edit(self.console, preview.detail, mark="proposed:", style="cyan")
        elif preview is not None and not preview.ok:
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
