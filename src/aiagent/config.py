"""Runtime configuration for an agent run."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_MODEL = "gemini-2.5-flash"


def default_model() -> str:
    return os.environ.get("AIAGENT_MODEL", DEFAULT_MODEL)


@dataclass(frozen=True)
class AgentConfig:
    workdir: Path
    model: str = DEFAULT_MODEL
    max_steps: int = 30
    # Largest chunk of a file returned by a single read_file call.
    max_read_chars: int = 20_000
    # Cap on captured stdout/stderr sent back to the model.
    max_output_chars: int = 8_000
    command_timeout: float = 60.0
    # Command used to verify the agent's work. None means auto-detect.
    test_command: tuple[str, ...] | None = None
    verify: bool = True
    max_verify_attempts: int = 3
