import os
from pathlib import Path

import pytest

from aiagent.config import load_api_key
from aiagent.llm import Usage


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    for name in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "GOOGLE_GEMINI_BASE_URL"):
        monkeypatch.delenv(name, raising=False)
    return tmp_path


def test_reads_only_the_key_from_dotenv(repo: Path) -> None:
    (repo / ".env").write_text(
        "GEMINI_API_KEY=from-file\nGOOGLE_GEMINI_BASE_URL=https://attacker.example\n"
    )
    assert load_api_key() == "from-file"
    # A repository's .env must not be able to redirect API traffic.
    assert "GOOGLE_GEMINI_BASE_URL" not in os.environ


def test_environment_wins_over_dotenv(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (repo / ".env").write_text("GEMINI_API_KEY=from-file\n")
    monkeypatch.setenv("GEMINI_API_KEY", "from-env")
    assert load_api_key() == "from-env"


def test_google_api_key_fallback_and_missing(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert load_api_key() is None
    monkeypatch.setenv("GOOGLE_API_KEY", "google")
    assert load_api_key() == "google"


def test_usage_cost() -> None:
    usage = Usage(input_tokens=1_000_000, output_tokens=100_000, cached_tokens=400_000)
    # 600k uncached * $0.75 + 400k cached * $0.075 + 100k out * $3.75
    assert usage.cost("gemini-3.8-flash") == pytest.approx(0.45 + 0.03 + 0.375)
    assert usage.cost("some-unknown-model") is None


def test_usage_adds_cached_tokens() -> None:
    assert Usage(10, 2, 4) + Usage(5, 1, 3) == Usage(15, 3, 7)
