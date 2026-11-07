"""Patch engine: parse model-written diffs and apply them safely.

Two input formats are accepted:

* **Unified diffs** with ``@@ -a,b +c,d @@`` hunk headers. Line numbers are
  used only as a hint: models often miscount them, so each hunk is located by
  its content, preferring the match closest to the stated position (the same
  idea as GNU ``patch``'s offset search).
* **Minimal diffs**: a single hunk of `` ``/``-``/``+`` lines with no header,
  located purely by content.

Every context (`` ``) and removal (``-``) line is checked against the file
before anything changes. If any hunk fails to match, nothing is applied and
the error explains where the closest match was, so the model can repair its
patch instead of silently corrupting the file.
"""

from __future__ import annotations

import difflib
import re
from collections.abc import Callable
from dataclasses import dataclass, field

HUNK_HEADER = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
FILE_HEADER_PREFIXES = ("--- ", "+++ ", "diff ", "index ")

# Matching strategies, strictest first. Trailing whitespace is the most common
# thing models get wrong in context lines, and it never changes semantics.
_NORMALIZERS: tuple[Callable[[str], str], ...] = (lambda s: s, str.rstrip)


class PatchError(ValueError):
    """Raised when a patch is malformed or does not match the target file."""


@dataclass
class Hunk:
    old_start: int | None  # 1-based, from the header; None for minimal diffs
    old_count: int | None
    lines: list[tuple[str, str]] = field(default_factory=list)  # (op, text)

    @property
    def before(self) -> list[str]:
        return [text for op, text in self.lines if op != "+"]

    @property
    def after(self) -> list[str]:
        return [text for op, text in self.lines if op != "-"]

    @property
    def has_changes(self) -> bool:
        return any(op != " " for op, _ in self.lines)


def parse_patch(patch: str) -> list[Hunk]:
    """Parse a unified or minimal diff into hunks."""
    raw = patch.splitlines()
    unified = any(HUNK_HEADER.match(line) for line in raw)

    hunks: list[Hunk] = []
    current: Hunk | None = None
    for lineno, line in enumerate(raw, start=1):
        header = HUNK_HEADER.match(line)
        if header:
            count = header.group(2)
            current = Hunk(int(header.group(1)), int(count) if count is not None else 1)
            hunks.append(current)
            continue
        if current is None:
            # Preamble before the first hunk: file headers and blank lines.
            if unified or not line.strip() or line.startswith(FILE_HEADER_PREFIXES):
                continue
            current = Hunk(None, None)
            hunks.append(current)
        if line.startswith("\\"):  # "\ No newline at end of file"
            continue
        if line == "":
            # Editors and models often strip the space from blank context lines.
            current.lines.append((" ", ""))
            continue
        op = line[0]
        if op not in " +-":
            raise PatchError(f"Patch line {lineno} must start with ' ', '+' or '-' (got {line!r}).")
        current.lines.append((op, line[1:]))

    for hunk in hunks:
        _trim_blank_context(hunk)
    hunks = [hunk for hunk in hunks if hunk.has_changes]
    if not hunks:
        raise PatchError("Patch contains no changes.")
    return hunks


def _trim_blank_context(hunk: Hunk) -> None:
    """Drop blank context lines at the edges of a hunk.

    They carry no information and are usually artefacts of how the patch was
    quoted. Trimming the front shifts where the hunk starts, so the header
    hint is moved to match.
    """
    while hunk.lines and hunk.lines[0] == (" ", ""):
        hunk.lines.pop(0)
        if hunk.old_start is not None:
            hunk.old_start += 1
    while hunk.lines and hunk.lines[-1] == (" ", ""):
        hunk.lines.pop()


def apply_patch(original: str, patch: str) -> str:
    """Apply ``patch`` to ``original`` and return the new text.

    All hunks are applied to a copy; a failure leaves nothing half-applied.
    """
    hunks = parse_patch(patch)
    lines = original.splitlines()
    trailing_newline = original.endswith("\n") or original == ""

    offset = 0  # net lines added by earlier hunks
    search_from = 0  # hunks must not overlap or go backwards
    for index, hunk in enumerate(hunks, start=1):
        before, after = hunk.before, hunk.after
        hint = search_from if hunk.old_start is None else hunk.old_start - 1 + offset

        if before:
            pos = _locate(lines, before, hint, search_from)
            if pos is None:
                raise PatchError(_mismatch_message(index, hunk, lines, hint))
        elif hunk.old_start is not None:
            # Pure insertion: "@@ -N,0 +M,k @@" inserts after line N.
            pos = hint + 1 if hunk.old_count == 0 else hint
            pos = min(max(pos, search_from), len(lines))
        else:
            raise PatchError(
                f"Hunk {index} has only added lines, so there is nothing to anchor it to. "
                "Include at least one unchanged context line next to the insertion."
            )

        lines[pos : pos + len(before)] = _replacement(hunk, lines, pos)
        offset += len(after) - len(before)
        search_from = pos + len(after)

    text = "\n".join(lines)
    if lines and trailing_newline:
        text += "\n"
    return text


def _replacement(hunk: Hunk, lines: list[str], pos: int) -> list[str]:
    """The new lines for a hunk matched at ``pos``.

    Context lines are taken from the file, not the patch, so a fuzzy match
    never rewrites lines the hunk did not mean to change.
    """
    result: list[str] = []
    cursor = pos
    for op, text in hunk.lines:
        if op == "+":
            result.append(text)
            continue
        if op == " ":
            result.append(lines[cursor])
        cursor += 1
    return result


def _locate(lines: list[str], before: list[str], hint: int, search_from: int) -> int | None:
    """Find where ``before`` occurs in ``lines``, preferring the position nearest ``hint``."""
    size = len(before)
    for normalize in _NORMALIZERS:
        expected = [normalize(line) for line in before]
        matches = [
            pos
            for pos in range(search_from, len(lines) - size + 1)
            if all(normalize(lines[pos + i]) == expected[i] for i in range(size))
        ]
        if matches:
            return min(matches, key=lambda pos: abs(pos - hint))
    return None


def _mismatch_message(index: int, hunk: Hunk, lines: list[str], hint: int) -> str:
    before = hunk.before
    parts = [f"Hunk {index} does not match the file; no changes were made."]
    if hunk.old_start is not None and 0 <= hint < len(lines):
        parts.append(
            f"At line {hint + 1} the hunk expects {before[0]!r} but the file has {lines[hint]!r}."
        )

    best_pos, best_score = _closest_window(lines, before)
    if best_pos is not None and best_score >= 0.5:
        window = lines[best_pos : best_pos + len(before)]
        shown = "\n".join(f"{best_pos + i + 1:>5} | {text}" for i, text in enumerate(window[:12]))
        parts.append(
            f"The closest match ({best_score:.0%} similar) starts at line {best_pos + 1}:\n{shown}"
        )
    parts.append("Re-read the file and copy the context and '-' lines exactly.")
    return "\n".join(parts)


def _closest_window(lines: list[str], before: list[str]) -> tuple[int | None, float]:
    target = "\n".join(before)
    best_pos: int | None = None
    best_score = 0.0
    for pos in range(max(1, len(lines) - len(before) + 1)):
        candidate = "\n".join(lines[pos : pos + len(before)])
        score = difflib.SequenceMatcher(None, candidate, target, autojunk=False).ratio()
        if score > best_score:
            best_pos, best_score = pos, score
    return best_pos, best_score


def make_diff(old: str, new: str, path: str) -> str:
    """Render the change from ``old`` to ``new`` as a unified diff."""
    return "\n".join(
        difflib.unified_diff(
            old.splitlines(),
            new.splitlines(),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
            lineterm="",
        )
    )
