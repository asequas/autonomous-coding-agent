import pytest

from aiagent.patching import PatchError, apply_patch, make_diff, parse_patch

SOURCE = """\
def add(a, b):
    return a + b


def sub(a, b):
    return a - b


print(add(1, 2))
"""


def test_unified_diff_single_hunk() -> None:
    patch = """\
@@ -1,2 +1,2 @@
-def add(a, b):
+def add_numbers(a, b):
     return a + b
"""
    assert apply_patch(SOURCE, patch).startswith("def add_numbers(a, b):\n    return a + b\n")


def test_unified_diff_multiple_hunks() -> None:
    patch = """\
@@ -1,2 +1,2 @@
-def add(a, b):
+def add_numbers(a, b):
     return a + b
@@ -9,1 +9,1 @@
-print(add(1, 2))
+print(add_numbers(1, 2))
"""
    result = apply_patch(SOURCE, patch)
    assert "def add_numbers" in result
    assert "print(add_numbers(1, 2))" in result
    assert "def sub(a, b):" in result


def test_file_headers_are_ignored() -> None:
    patch = """\
diff --git a/m.py b/m.py
--- a/m.py
+++ b/m.py
@@ -5,2 +5,2 @@
 def sub(a, b):
-    return a - b
+    return b - a
"""
    assert "return b - a" in apply_patch(SOURCE, patch)


def test_blank_context_lines_do_not_shift_the_file() -> None:
    """Regression: the old engine skipped ' ' lines without advancing, corrupting the file."""
    patch = """\
@@ -2,4 +2,4 @@
     return a + b


-def sub(a, b):
+def subtract(a, b):
"""
    expected = SOURCE.replace("def sub(", "def subtract(")
    assert apply_patch(SOURCE, patch) == expected


def test_wrong_line_numbers_are_corrected_by_content() -> None:
    patch = """\
@@ -40,2 +40,2 @@
 def sub(a, b):
-    return a - b
+    return -(b - a)
"""
    assert "return -(b - a)" in apply_patch(SOURCE, patch)


def test_nearest_match_to_hint_wins_when_context_repeats() -> None:
    text = "x = 1\npass\nx = 1\npass\n"
    patch = "@@ -3,1 +3,1 @@\n-x = 1\n+x = 2\n"
    assert apply_patch(text, patch) == "x = 1\npass\nx = 2\npass\n"


def test_trailing_whitespace_differences_are_tolerated() -> None:
    text = "a = 1   \nb = 2\n"
    assert apply_patch(text, " a = 1\n-b = 2\n+b = 3\n") == "a = 1   \nb = 3\n"


def test_minimal_diff_is_located_by_content() -> None:
    patch = """
 def sub(a, b):
-    return a - b
+    return a - b  # subtract
"""
    assert "# subtract" in apply_patch(SOURCE, patch)


def test_pure_insertion_with_header() -> None:
    text = "a\nb\nc\n"
    assert apply_patch(text, "@@ -1,0 +2,1 @@\n+inserted\n") == "a\ninserted\nb\nc\n"


def test_minimal_insertion_without_context_is_rejected() -> None:
    with pytest.raises(PatchError, match="nothing to anchor"):
        apply_patch("a\n", "+b\n")


def test_mismatch_reports_closest_match_and_changes_nothing() -> None:
    patch = """\
@@ -1,2 +1,2 @@
 def add(a, b):
-    return a + c
+    return a * b
"""
    with pytest.raises(PatchError) as info:
        apply_patch(SOURCE, patch)
    message = str(info.value)
    assert "Hunk 1 does not match" in message
    assert "closest match" in message
    assert "    1 | def add(a, b):" in message


def test_failed_second_hunk_applies_nothing() -> None:
    text = "a\nb\nc\n"
    patch = "@@ -1,1 +1,1 @@\n-a\n+A\n@@ -3,1 +3,1 @@\n-zzz\n+Z\n"
    with pytest.raises(PatchError, match="Hunk 2"):
        apply_patch(text, patch)


def test_no_newline_marker_is_ignored() -> None:
    patch = "-b\n\\ No newline at end of file\n+B\n\\ No newline at end of file\n"
    assert apply_patch("a\nb", " a\n" + patch) == "a\nB"


def test_trailing_newline_is_preserved() -> None:
    assert apply_patch("a\nb\n", " a\n-b\n+c\n") == "a\nc\n"
    assert apply_patch("a\nb", " a\n-b\n+c\n") == "a\nc"


def test_invalid_line_prefix_is_rejected() -> None:
    with pytest.raises(PatchError, match="must start with"):
        apply_patch(SOURCE, "@@ -1,1 +1,1 @@\n*def add(a, b):\n")


def test_patch_without_changes_is_rejected() -> None:
    with pytest.raises(PatchError, match="no changes"):
        parse_patch(" def add(a, b):\n")


def test_hunks_cannot_go_backwards() -> None:
    text = "a\nb\nc\n"
    patch = "@@ -3,1 +3,1 @@\n-c\n+C\n@@ -1,1 +1,1 @@\n-a\n+A\n"
    with pytest.raises(PatchError, match="Hunk 2"):
        apply_patch(text, patch)


def test_make_diff_round_trips() -> None:
    new = SOURCE.replace("a - b", "a - b - 0")
    diff = make_diff(SOURCE, new, "m.py")
    assert diff.startswith("--- a/m.py\n+++ b/m.py\n@@")
    assert apply_patch(SOURCE, diff) == new
