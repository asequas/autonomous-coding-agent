"""Mutating tools: patch or write files, with Python syntax validation."""

from __future__ import annotations

import ast
from pathlib import Path

from aiagent.patching import apply_patch as apply_patch_text
from aiagent.patching import make_diff
from aiagent.tools import Tool, ToolContext, ToolError, schema
from aiagent.tools.files import read_text

MAX_DIFF_CHARS = 4_000


def validate_python(path: str, text: str) -> None:
    """Reject edits that would leave a .py file unparseable."""
    if not path.endswith(".py"):
        return
    try:
        ast.parse(text, filename=path)
    except SyntaxError as exc:
        raise ToolError(
            f"Edit rejected: {path} would not be valid Python "
            f"(line {exc.lineno}: {exc.msg}). The file was not changed."
        ) from exc


def _commit(ctx: ToolContext, target: Path, old: str, new: str, verb: str) -> str:
    rel = ctx.workspace.relative(target)
    validate_python(rel, new)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(new, encoding="utf-8")
    ctx.changed_files.add(rel)
    ctx.edit_count += 1

    diff = make_diff(old, new, rel)
    body = diff.splitlines()[2:]  # skip the ---/+++ file headers
    added = sum(line.startswith("+") for line in body)
    removed = sum(line.startswith("-") for line in body)
    if len(diff) > MAX_DIFF_CHARS:
        diff = diff[:MAX_DIFF_CHARS] + "\n[diff truncated]"
    return f"{verb} {rel} (+{added} -{removed}).\n{diff}"


def apply_patch(ctx: ToolContext, path: str, patch: str) -> str:
    target = ctx.workspace.resolve(path)
    if not target.is_file():
        raise ToolError(f"'{path}' does not exist. Use write_file to create new files.")
    old = read_text(target)
    new = apply_patch_text(old, patch)
    if new == old:
        raise ToolError("The patch applied cleanly but did not change the file.")
    return _commit(ctx, target, old, new, "Patched")


def write_file(ctx: ToolContext, path: str, content: str) -> str:
    target = ctx.workspace.resolve(path)
    if target.is_dir():
        raise ToolError(f"'{path}' is a directory.")
    old = read_text(target) if target.exists() else ""
    verb = "Overwrote" if target.exists() else "Created"
    return _commit(ctx, target, old, content, verb)


TOOLS = [
    Tool(
        name="apply_patch",
        description=(
            "Edit an existing file by applying a diff. Preferred over write_file for any "
            "change to an existing file.\n"
            "Accepts a unified diff:\n"
            "@@ -12,3 +12,4 @@\n"
            " context line\n"
            "-removed line\n"
            "+added line\n"
            " context line\n"
            "or the same lines without the @@ header. Context and '-' lines must match the "
            "file exactly (without read_file's line-number prefix). Include 1-3 unchanged "
            "lines around each change. Hunk line numbers are a hint; hunks are located by "
            "content. Python files are syntax-checked and invalid edits are rejected."
        ),
        parameters=schema(
            {
                "path": {"type": "string", "description": "File path relative to the workspace."},
                "patch": {"type": "string", "description": "The diff to apply."},
            },
            required=["path", "patch"],
        ),
        handler=apply_patch,
        side_effects=True,
    ),
    Tool(
        name="write_file",
        description=(
            "Create a new file, or replace a file's entire contents. Use apply_patch "
            "for targeted edits to existing files."
        ),
        parameters=schema(
            {
                "path": {"type": "string", "description": "File path relative to the workspace."},
                "content": {"type": "string", "description": "Complete new file contents."},
            },
            required=["path", "content"],
        ),
        handler=write_file,
        side_effects=True,
    ),
]
