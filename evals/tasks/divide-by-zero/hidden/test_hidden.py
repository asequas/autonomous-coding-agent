import subprocess
import sys
from pathlib import Path

import pytest

from pkg.calculator import Calculator

ROOT = Path(__file__).resolve().parents[1]


def test_raises_value_error():
    with pytest.raises(ValueError, match="division by zero"):
        Calculator().evaluate("1 / 0")


def test_cli_message():
    out = subprocess.run(
        [sys.executable, "main.py", "1 / 0"], cwd=ROOT, capture_output=True, text=True
    ).stdout
    assert out.strip() == "Error: division by zero"


def test_normal_division_still_works():
    assert Calculator().evaluate("9 / 3") == 3
