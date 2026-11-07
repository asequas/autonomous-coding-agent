from __future__ import annotations

from pathlib import Path

import pytest

from aiagent.config import AgentConfig
from aiagent.sandbox import Workspace
from aiagent.tools import ToolContext


def make_ctx(root: Path, **config: object) -> ToolContext:
    return ToolContext(Workspace(root), AgentConfig(workdir=root, **config))  # type: ignore[arg-type]


@pytest.fixture
def ctx(tmp_path: Path) -> ToolContext:
    root = tmp_path / "project"
    root.mkdir()
    return make_ctx(root)


def write(ctx: ToolContext, path: str, text: str) -> Path:
    target = ctx.workspace.root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return target
