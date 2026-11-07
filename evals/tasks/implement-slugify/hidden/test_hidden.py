import pytest

from textutils import slugify


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Hello, World!", "hello-world"),
        ("Crème Brûlée", "creme-brulee"),
        ("  --Already--Slugged--  ", "already-slugged"),
        ("Python 3.14 is out", "python-3-14-is-out"),
        ("!!!", ""),
        ("", ""),
    ],
)
def test_slugify(text, expected):
    assert slugify(text) == expected


def test_truncation_never_ends_on_hyphen():
    assert slugify("aaaaaaaaaa b", max_length=11) == "aaaaaaaaaa"
    assert len(slugify("word " * 30)) <= 50
