"""JSONL traces: one event per line, enough to replay or audit a run."""

from __future__ import annotations

import dataclasses
import json
import time
from pathlib import Path
from types import TracebackType
from typing import Any

from aiagent.agent import AgentObserver, RunResult
from aiagent.config import AgentConfig
from aiagent.llm import ModelTurn, ToolCall
from aiagent.tools import ToolResult
from aiagent.tools.edit import Edit
from aiagent.verify import Verification


def _plain(value: Any) -> Any:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return dataclasses.asdict(value)
    return value


class JsonlTrace(AgentObserver):
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._file = path.open("w", encoding="utf-8")

    def __enter__(self) -> JsonlTrace:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def _write(self, event: str, **data: Any) -> None:
        record = {"ts": time.time(), "event": event, **{k: _plain(v) for k, v in data.items()}}
        self._file.write(json.dumps(record, default=str) + "\n")
        self._file.flush()

    def on_start(self, task: str, config: AgentConfig, model: str) -> None:
        self._write("start", task=task, config=config, model=model)

    def on_model_turn(self, step: int, turn: ModelTurn) -> None:
        self._write("model_turn", step=step, turn=turn)

    def on_tool_call(self, call: ToolCall) -> None:
        self._write("tool_call", call=call)

    def on_tool_result(self, call: ToolCall, result: ToolResult) -> None:
        # An Edit holds both full file versions; its diff is what is worth keeping.
        detail = result.detail
        record = detail.diff if isinstance(detail, Edit) else detail
        self._write("tool_result", call=call, ok=result.ok, output=result.output, detail=record)

    def on_verification(self, verification: Verification) -> None:
        self._write("verification", verification=verification)

    def on_finish(self, result: RunResult) -> None:
        self._write("finish", result=result)

    def close(self) -> None:
        self._file.close()
