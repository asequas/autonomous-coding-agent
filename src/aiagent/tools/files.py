"""Read-only tools: list, read and search files in the workspace."""

from __future__ import annotations

import re
from pathlib import Path

from aiagent.text import LINE_PREFIX_WIDTH, format_numbered
from aiagent.tools import Tool, ToolContext, ToolError, schema

MAX_LISTED_FILES = 300
MAX_SEARCH_MATCHES = 100
MAX_SEARCH_FILE_BYTES = 1_000_000
MAX_MATCH_LINE_CHARS = 200


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ToolError(f"'{path.name}' is not a UTF-8 text file.") from exc


def _human_size(size: int) -> str:
    return f"{size} B" if size < 1024 else f"{size / 1024:.1f} KB"


def list_files(ctx: ToolContext, directory: str = ".") -> str:
    start = ctx.workspace.resolve(directory)
    if not start.is_dir():
        raise ToolError(f"'{directory}' is not a directory.")

    files = list(ctx.workspace.iter_files(start))
    if not files:
        return f"No files under '{directory}'."
    shown = [
        f"{ctx.workspace.relative(path)}  ({_human_size(path.stat().st_size)})"
        for path in files[:MAX_LISTED_FILES]
    ]
    if len(files) > MAX_LISTED_FILES:
        shown.append(f"... and {len(files) - MAX_LISTED_FILES} more files")
    return "\n".join(shown)


def read_file(ctx: ToolContext, path: str, start_line: int = 1, end_line: int | None = None) -> str:
    target = ctx.workspace.resolve(path)
    if not target.is_file():
        raise ToolError(f"'{path}' is not a file.")

    lines = read_text(target).splitlines()
    if not lines:
        return f"'{path}' is empty."
    start = max(start_line, 1)
    end = min(end_line or len(lines), len(lines))
    if start > end:
        raise ToolError(f"Invalid range {start_line}-{end_line}; '{path}' has {len(lines)} lines.")

    selected: list[str] = []
    budget = ctx.config.max_read_chars
    for line in lines[start - 1 : end]:
        budget -= len(line) + LINE_PREFIX_WIDTH + 1
        if budget < 0 and selected:
            break
        selected.append(line)

    body = format_numbered(selected, start)
    last = start + len(selected) - 1
    if last < end:
        body += (
            f"\n[Truncated at line {last} of {len(lines)}. "
            f"Call read_file with start_line={last + 1} to continue.]"
        )
    return body


def search_code(ctx: ToolContext, pattern: str, directory: str = ".") -> str:
    try:
        regex = re.compile(pattern)
    except re.error as exc:
        raise ToolError(f"Invalid regular expression: {exc}") from exc
    start = ctx.workspace.resolve(directory)

    matches: list[str] = []
    files = [start] if start.is_file() else ctx.workspace.iter_files(start)
    for path in files:
        if path.stat().st_size > MAX_SEARCH_FILE_BYTES:
            continue
        try:
            text = read_text(path)
        except (ToolError, OSError):
            continue
        if not regex.search(text):  # most files don't match; skip splitting them
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if regex.search(line):
                shown = line.strip()[:MAX_MATCH_LINE_CHARS]
                matches.append(f"{ctx.workspace.relative(path)}:{lineno}: {shown}")
                if len(matches) >= MAX_SEARCH_MATCHES:
                    matches.append(f"[Stopped after {MAX_SEARCH_MATCHES} matches.]")
                    return "\n".join(matches)
    return "\n".join(matches) if matches else f"No matches for /{pattern}/."


TOOLS = [
    Tool(
        name="list_files",
        description=(
            "Recursively list files in the workspace (or a subdirectory) with their sizes. "
            "VCS, virtualenv and cache directories are skipped."
        ),
        parameters=schema(
            {
                "directory": {
                    "type": "string",
                    "description": "Directory relative to the workspace root. Defaults to '.'.",
                }
            }
        ),
        handler=list_files,
    ),
    Tool(
        name="read_file",
        description=(
            "Read a text file. Each line is prefixed with its line number as '  12 | '; "
            "the prefix is NOT part of the file. Use start_line/end_line for large files."
        ),
        parameters=schema(
            {
                "path": {"type": "string", "description": "File path relative to the workspace."},
                "start_line": {"type": "integer", "description": "First line to read (1-based)."},
                "end_line": {"type": "integer", "description": "Last line to read (inclusive)."},
            },
            required=["path"],
        ),
        handler=read_file,
    ),
    Tool(
        name="search_code",
        description=(
            "Search files for a Python regular expression. Returns 'path:line: text' matches."
        ),
        parameters=schema(
            {
                "pattern": {"type": "string", "description": "Python regular expression."},
                "directory": {
                    "type": "string",
                    "description": "File or directory to search, relative to the workspace.",
                },
            },
            required=["pattern"],
        ),
        handler=search_code,
    ),
]
