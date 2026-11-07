import re
import unicodedata


def slugify(text: str, max_length: int = 50) -> str:
    """Convert text into a URL slug (see the task's docstring)."""
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")
    return slug[:max_length].rstrip("-")
