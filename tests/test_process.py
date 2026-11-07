from aiagent.process import CommandResult


def test_short_stream_leaves_its_budget_to_the_long_one() -> None:
    result = CommandResult(("x",), 1, stdout="o" * 7000, stderr="warning")
    formatted = result.format(8000)
    assert "omitted" not in formatted  # 7000 + 7 chars fit in 8000
    assert formatted.count("o") >= 7000


def test_both_streams_are_capped_when_large() -> None:
    result = CommandResult(("x",), 1, stdout="o" * 20_000, stderr="e" * 20_000)
    formatted = result.format(8000)
    assert len(formatted) < 8500
    assert formatted.count("omitted") == 2
