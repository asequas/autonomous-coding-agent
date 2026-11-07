import inspect

import pytest

import records

CASES = [
    {"name": " ada lovelace ", "email": "ADA@Example.com"},
    {"email": "root@x.io"},
    {"name": "   ", "email": ""},
    {},
]


@pytest.mark.parametrize("record", CASES)
def test_behaviour_unchanged(record):
    name = record.get("name", "").strip().title() or "Unknown"
    email = record.get("email", "").strip().lower()
    assert records.format_user(record) == f"{name} <{email}>"
    assert records.format_admin(record) == f"{name} <{email}> [admin]"


def test_helper_is_used():
    assert records.normalize_contact(CASES[0]) == ("Ada Lovelace", "ada@example.com")
    for fn in (records.format_user, records.format_admin):
        source = inspect.getsource(fn)
        assert "normalize_contact" in source
        assert ".strip()" not in source
