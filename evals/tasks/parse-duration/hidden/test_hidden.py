import pytest

from durations import parse_duration


@pytest.mark.parametrize(
    ("text", "seconds"),
    [("1h30m", 5400), ("45s", 45), ("2h", 7200), ("1h 30m 15s", 5415), ("10m 5s", 605)],
)
def test_valid(text, seconds):
    assert parse_duration(text) == seconds


@pytest.mark.parametrize("text", ["", "abc", "90", "1x", "h"])
def test_invalid(text):
    with pytest.raises(ValueError):
        parse_duration(text)
