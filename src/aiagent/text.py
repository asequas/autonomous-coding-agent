"""Text formats shared by tools and error messages the model reads."""

from __future__ import annotations

LINE_PREFIX_WIDTH = len(f"{0:>5} | ")


def format_numbered(lines: list[str], first_line: int) -> str:
    """Prefix lines with their numbers, as read_file shows them to the model."""
    return "\n".join(f"{first_line + i:>5} | {line}" for i, line in enumerate(lines))


def truncate_middle(text: str, max_chars: int) -> str:
    """Shorten text by cutting the middle; errors usually sit at the end."""
    if len(text) <= max_chars:
        return text
    head = max_chars // 4
    tail = max_chars - head
    skipped = len(text) - head - tail
    return f"{text[:head]}\n[... {skipped} characters omitted ...]\n{text[-tail:]}"
