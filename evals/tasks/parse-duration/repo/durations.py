import re


def parse_duration(text: str) -> int:
    """Parse durations like '1h30m', '45s' or '2h' into seconds."""
    text = text.strip()
    match = re.fullmatch(r"(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?", text)
    if not text or not match:
        raise ValueError(f"invalid duration: {text!r}")
    hours, minutes, seconds = (int(group) if group else 0 for group in match.groups())
    return hours * 3600 + minutes + seconds
