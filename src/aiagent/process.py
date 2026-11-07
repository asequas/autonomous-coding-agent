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

# Environment variables whose names look like credentials are not passed to
# code the agent runs; model-written code should never see the API key.
SECRET_NAME = re.compile(r"KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL", re.IGNORECASE)


def scrubbed_env() -> dict[str, str]:
    env = {name: value for name, value in os.environ.items() if not SECRET_NAME.search(name)}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def truncate_middle(text: str, max_chars: int) -> str:
    """Shorten text by cutting the middle; errors usually sit at the end."""
    if len(text) <= max_chars:
        return text
    head = max_chars // 4
    tail = max_chars - head
    skipped = len(text) - head - tail
    return f"{text[:head]}\n[... {skipped} characters omitted ...]\n{text[-tail:]}"


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

    def format(self, max_chars: int) -> str:
        status = "timed out" if self.timed_out else f"exit code {self.exit_code}"
        parts = [f"$ {self.display_command}", f"[{status}]"]
        if self.stdout.strip():
            parts.append("--- stdout ---\n" + truncate_middle(self.stdout.rstrip(), max_chars))
        if self.stderr.strip():
            parts.append("--- stderr ---\n" + truncate_middle(self.stderr.rstrip(), max_chars))
        if not self.stdout.strip() and not self.stderr.strip():
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
