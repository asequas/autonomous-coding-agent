from records import format_admin, format_user


def test_format_user():
    assert format_user({"name": " ada lovelace ", "email": "ADA@Example.com"}) == (
        "Ada Lovelace <ada@example.com>"
    )


def test_format_admin():
    assert format_admin({"email": "root@x.io"}) == "Unknown <root@x.io> [admin]"
