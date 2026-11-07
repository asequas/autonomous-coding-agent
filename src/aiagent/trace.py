"""JSONL traces: one event per line, enough to replay or audit a run."""

from __future__ import annotations

import dataclasses
import json
import time
from pathlib import Path
from typing import Any

from aiagent.agent import AgentObserver, RunResult
from aiagent.config import AgentConfig
from aiagent.llm import ModelTurn, ToolCall
from aiagent.tools import ToolResult
from aiagent.verify import Verification


def _plain(value: Any) -> Any:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return dataclasses.asdict(value)
    return value


class JsonlTrace(AgentObserver):
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._file = path.open("w", encoding="utf-8")

    def _write(self, event: str, **data: Any) -> None:
        record = {"ts": time.time(), "event": event, **{k: _plain(v) for k, v in data.items()}}
        self._file.write(json.dumps(record, default=str) + "\n")
        self._file.flush()

    def on_start(self, task: str, config: AgentConfig) -> None:
        self._write("start", task=task, config=config)

    def on_model_turn(self, step: int, turn: ModelTurn) -> None:
        self._write("model_turn", step=step, turn=turn)

    def on_tool_call(self, call: ToolCall) -> None:
        self._write("tool_call", call=call)

    def on_tool_result(self, call: ToolCall, result: ToolResult) -> None:
        self._write("tool_result", call=call, result=result)

    def on_verification(self, verification: Verification) -> None:
        self._write("verification", verification=verification)

    def on_finish(self, result: RunResult) -> None:
        self._write("finish", result=result)

    def close(self) -> None:
        self._file.close()
