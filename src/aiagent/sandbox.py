"""Path sandbox: every file the agent touches must resolve inside the workspace root."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

IGNORED_DIRS = frozenset(
    {
        ".git",
        ".hg",
        ".venv",
        "venv",
        "env",
        "__pycache__",
        "node_modules",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        "build",
        "dist",
    }
)


# Readable, but never writable: changes here could run code outside the agent
# (git hooks and config, packages in a virtualenv).
PROTECTED_DIRS = frozenset({".git", ".hg", ".svn", ".venv", "venv", "node_modules"})


class SandboxError(ValueError):
    """Raised when a path would escape the workspace."""


class Workspace:
    """A directory the agent is confined to.

    Paths are resolved with symlinks followed and then checked for containment
    with ``Path.is_relative_to``. A plain string-prefix check is not enough:
    ``/work/app_evil`` starts with ``/work/app``.
    """

    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.root = Path(root).resolve()
        if not self.root.is_dir():
            raise SandboxError(f"Workspace root is not a directory: {self.root}")

    def resolve(self, path: str | None = None) -> Path:
        """Resolve a workspace-relative path, rejecting anything outside the root."""
        candidate = (self.root / (path or ".")).resolve()
        if not candidate.is_relative_to(self.root):
            raise SandboxError(f"Path '{path}' is outside the workspace.")
        return candidate

    def resolve_writable(self, path: str) -> Path:
        """Like ``resolve``, but also refuse paths inside protected directories."""
        candidate = self.resolve(path)
        for part in candidate.relative_to(self.root).parts:
            if part in PROTECTED_DIRS:
                raise SandboxError(f"'{path}' is inside {part}/, which the agent may not modify.")
        return candidate

    def relative(self, path: Path) -> str:
        """Render an absolute path inside the workspace as a POSIX relative path."""
        rel = path.relative_to(self.root).as_posix()
        return rel or "."

    def iter_files(self, start: Path | None = None) -> Iterator[Path]:
        """Yield files under ``start`` in sorted order, skipping ignored and escaping paths."""
        base = start or self.root
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = sorted(d for d in dirnames if d not in IGNORED_DIRS)
            for name in sorted(filenames):
                path = Path(dirpath) / name
                # A symlink inside the tree may still point outside of it.
                if path.resolve().is_relative_to(self.root):
                    yield path
