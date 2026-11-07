import json
from pathlib import Path

import pytest

from aiagent import cli
from aiagent.llm import ModelTurn, ScriptedClient, ToolCall


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "load_dotenv", lambda *_: None)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)


def test_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        cli.main(["--version"])
    assert capsys.readouterr().out.startswith("aiagent ")


def test_missing_api_key(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("GEMINI_API_KEY")
    assert cli.main(["run", "task", "-C", str(tmp_path), "--yes"]) == 2


def test_missing_workdir(tmp_path: Path) -> None:
    assert cli.main(["run", "task", "-C", str(tmp_path / "nope"), "--yes"]) == 2


def test_requires_yes_without_a_terminal(tmp_path: Path) -> None:
    assert cli.main(["run", "task", "-C", str(tmp_path)]) == 2


def test_full_run_writes_trace_and_recording(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "hello.py").write_text("print('hi')\n")
    script = ScriptedClient(
        [
            ModelTurn(
                tool_calls=[
                    ToolCall(
                        "apply_patch",
                        {"path": "hello.py", "patch": "-print('hi')\n+print('hello')\n"},
                    )
                ]
            ),
            ModelTurn(text="Changed the greeting."),
        ]
    )
    monkeypatch.setattr(cli, "GeminiClient", lambda *_args, **_kw: script)
    trace = tmp_path / "trace.jsonl"
    svg = tmp_path / "run.svg"

    code = cli.main(
        [
            "run",
            "Say hello",
            "-C",
            str(project),
            "--yes",
            "--trace",
            str(trace),
            "--record",
            str(svg),
        ]
    )

    assert code == 0
    assert (project / "hello.py").read_text() == "print('hello')\n"
    events = [json.loads(line)["event"] for line in trace.read_text().splitlines()]
    assert events == [
        "start",
        "model_turn",
        "tool_call",
        "tool_result",
        "model_turn",
        "verification",
        "finish",
    ]
    assert "<svg" in svg.read_text()
