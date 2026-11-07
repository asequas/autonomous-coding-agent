def slugify(text: str, max_length: int = 50) -> str:
    """Convert text into a URL slug.

    - Lowercase the text.
    - Replace accented characters with their ASCII equivalents ("é" -> "e").
    - Replace every run of characters that are not a-z or 0-9 with a single hyphen.
    - Strip leading and trailing hyphens.
    - Truncate to at most max_length characters, never ending on a hyphen.

    >>> slugify("Hello, World!")
    'hello-world'
    """
    raise NotImplementedError
