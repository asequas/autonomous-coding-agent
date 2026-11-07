"""Running commands inside the workspace."""

from __future__ import annotations

import os
import re
import shlex
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from aiagent.text import truncate_middle

# Environment variables whose names look like credentials are not passed to
# code the agent runs; model-written code should never see the API key.
SECRET_NAME = re.compile(r"KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL", re.IGNORECASE)


def scrubbed_env() -> dict[str, str]:
    env = {name: value for name, value in os.environ.items() if not SECRET_NAME.search(name)}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def _decode(output: str | bytes | None) -> str:
    if output is None:
        return ""
    return output.decode(errors="replace") if isinstance(output, bytes) else output


@dataclass(frozen=True)
class CommandResult:
    argv: tuple[str, ...]
    exit_code: int | None
    stdout: str
    stderr: str
    timed_out: bool = False

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and not self.timed_out

    @property
    def display_command(self) -> str:
        argv = ["python" if arg == sys.executable else arg for arg in self.argv]
        return shlex.join(argv)

    @property
    def status(self) -> str:
        return "timed out" if self.timed_out else f"exit code {self.exit_code}"

    def format(self, max_chars: int) -> str:
        """Command, status and output, with stdout and stderr sharing ``max_chars``."""
        streams = [
            (name, text.rstrip())
            for name, text in [("stdout", self.stdout), ("stderr", self.stderr)]
            if text.strip()
        ]
        parts = [f"$ {self.display_command}", f"[{self.status}]"]
        for name, text in streams:
            parts.append(f"--- {name} ---\n" + truncate_middle(text, max_chars // len(streams)))
        if not streams:
            parts.append("(no output)")
        return "\n".join(parts)


def run_command(argv: Sequence[str], cwd: Path, timeout: float) -> CommandResult:
    try:
        completed = subprocess.run(
            list(argv),
            cwd=cwd,
            env=scrubbed_env(),
            capture_output=True,
            text=True,
            timeout=timeout,
            stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired as exc:
        return CommandResult(
            tuple(argv), None, _decode(exc.stdout), _decode(exc.stderr), timed_out=True
        )
    return CommandResult(tuple(argv), completed.returncode, completed.stdout, completed.stderr)
