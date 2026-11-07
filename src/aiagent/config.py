"""Runtime configuration for an agent run."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values, find_dotenv

DEFAULT_MODEL = "gemini-3.8-flash"


@dataclass(frozen=True)
class Price:
    """USD per million tokens. Output includes thinking tokens."""

    input: float
    cached_input: float
    output: float


# Paid-tier list prices from https://ai.google.dev/gemini-api/docs/pricing,
# checked 2026-11-07 (introductory pricing, valid through 2026-12-31).
PRICES = {
    "gemini-3.8-flash": Price(input=0.75, cached_input=0.075, output=3.75),
}


def default_model() -> str:
    return os.environ.get("AIAGENT_MODEL", DEFAULT_MODEL)


def format_usd(value: float) -> str:
    return f"${value:.3f}"


API_KEY_NAMES = ("GEMINI_API_KEY", "GOOGLE_API_KEY")


def load_api_key() -> str | None:
    """Read the API key from the environment, falling back to the nearest .env file.

    Only the key is read from .env; nothing is copied into os.environ. The agent
    usually runs inside the repository it is working on, and that repository's
    .env must not be able to set variables such as GOOGLE_GEMINI_BASE_URL, which
    would send the key and every request to another host.
    """
    file_values = dotenv_values(find_dotenv(usecwd=True))
    for name in API_KEY_NAMES:
        value = os.environ.get(name) or file_values.get(name)
        if value:
            return value
    return None


@dataclass(frozen=True)
class AgentConfig:
    workdir: Path
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
