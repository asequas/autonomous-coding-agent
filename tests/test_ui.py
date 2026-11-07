import io
from pathlib import Path

import pytest
from rich.console import Console
from rich.text import Text

from aiagent import ui
from aiagent.llm import ToolCall
from aiagent.tools.edit import Edit


@pytest.fixture
def console() -> Console:
    return Console(file=io.StringIO(), record=True, width=120, color_system=None)


def ask_with(monkeypatch: pytest.MonkeyPatch, answer: str) -> list[object]:
    prompts: list[object] = []

    def fake_ask(prompt: object, **_kwargs: object) -> str:
        prompts.append(prompt)
        return answer

    monkeypatch.setattr(ui.Prompt, "ask", fake_ask)
    return prompts


def test_approval_prompt_shows_arguments_verbatim(
    console: Console, monkeypatch: pytest.MonkeyPatch
) -> None:
    prompts = ask_with(monkeypatch, "n")
    sneaky = "pkg/render.py[conceal]/../../.git/config" + " " * 80 + "tail"
    approved = ui.InteractiveApprover(console)(ToolCall("write_file", {"path": sneaky}), None)

    assert approved is False
    (prompt,) = prompts
    # A Text prompt is not parsed as markup, and paths are not truncated.
    assert isinstance(prompt, Text)
    assert "[conceal]/../../.git/config" in prompt.plain
    assert prompt.plain.endswith("tail')?")


def test_approval_shows_the_proposed_diff(
    console: Console, monkeypatch: pytest.MonkeyPatch
) -> None:
    ask_with(monkeypatch, "y")
    edit = Edit(Path("m.py"), "m.py", "x\n", "y\n", "Patched")
    preview = edit.result()
    assert ui.InteractiveApprover(console)(ToolCall("apply_patch", {"path": "m.py"}), preview)
    output = console.export_text()
    assert "proposed: Patched m.py (+1 -1)." in output and "+y" in output


def test_approve_all_stops_asking(console: Console, monkeypatch: pytest.MonkeyPatch) -> None:
    prompts = ask_with(monkeypatch, "a")
    approver = ui.InteractiveApprover(console)
    assert approver(ToolCall("run_tests", {}), None)
    assert approver(ToolCall("run_tests", {}), None)
    assert len(prompts) == 1
