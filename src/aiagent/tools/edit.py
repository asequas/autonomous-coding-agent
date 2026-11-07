"""Mutating tools: patch or write files, with Python syntax validation."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

from aiagent.patching import apply_patch as apply_patch_text
from aiagent.patching import make_diff
from aiagent.tools import Tool, ToolContext, ToolError, ToolResult, schema
from aiagent.tools.files import read_text


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


@dataclass(frozen=True)
class Edit:
    """A validated change to one file that has not been written yet."""

    target: Path
    rel: str
    old: str
    new: str
    verb: str

    @cached_property
    def diff(self) -> str:
        return make_diff(self.old, self.new, self.rel)

    def summary(self) -> str:
        body = self.diff.splitlines()[2:]  # skip the ---/+++ file headers
        added = sum(line.startswith("+") for line in body)
        removed = sum(line.startswith("-") for line in body)
        return f"{self.verb} {self.rel} (+{added} -{removed})."

    def result(self) -> ToolResult:
        # The model wrote the change itself, so it only needs the summary; the
        # diff goes to the UI and trace through ``detail``.
        return ToolResult(True, self.summary(), detail=self)


def plan_patch(ctx: ToolContext, path: str, patch: str) -> Edit:
    target = ctx.workspace.resolve_writable(path)
    if not target.is_file():
        raise ToolError(f"'{path}' does not exist. Use write_file to create new files.")
    old = read_text(target)
    new = apply_patch_text(old, patch)
    if new == old:
        raise ToolError("The patch applied cleanly but did not change the file.")
    return _validated(ctx, target, old, new, "Patched")


def plan_write(ctx: ToolContext, path: str, content: str) -> Edit:
    target = ctx.workspace.resolve_writable(path)
    if target.is_dir():
        raise ToolError(f"'{path}' is a directory.")
    old = read_text(target) if target.exists() else ""
    verb = "Overwrote" if target.exists() else "Created"
    return _validated(ctx, target, old, content, verb)


def _validated(ctx: ToolContext, target: Path, old: str, new: str, verb: str) -> Edit:
    rel = ctx.workspace.relative(target)
    validate_python(rel, new)
    return Edit(target, rel, old, new, verb)


def _commit(ctx: ToolContext, edit: Edit) -> ToolResult:
    edit.target.parent.mkdir(parents=True, exist_ok=True)
    edit.target.write_text(edit.new, encoding="utf-8")
    ctx.changed_files.add(edit.rel)
    ctx.edit_count += 1
    ctx.version += 1
    return edit.result()


def apply_patch(ctx: ToolContext, path: str, patch: str) -> ToolResult:
    return _commit(ctx, plan_patch(ctx, path, patch))


def write_file(ctx: ToolContext, path: str, content: str) -> ToolResult:
    return _commit(ctx, plan_write(ctx, path, content))


def preview_patch(ctx: ToolContext, path: str, patch: str) -> ToolResult:
    return plan_patch(ctx, path, patch).result()


def preview_write(ctx: ToolContext, path: str, content: str) -> ToolResult:
    return plan_write(ctx, path, content).result()


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
        preview=preview_patch,
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
        preview=preview_write,
        side_effects=True,
    ),
]
