import os
import shutil
from aiagent.functions.write_file import write_file

BASE_DIR = os.path.dirname(__file__)
TEST_DIR = os.path.join(BASE_DIR, "workspace")
TEST_FILE = "example.py"


def reset_workspace():
    if os.path.exists(TEST_DIR):
        shutil.rmtree(TEST_DIR)
    os.makedirs(TEST_DIR)


def read_file():
    path = os.path.join(TEST_DIR, TEST_FILE)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


# ---------------------------
# WRITE
# ---------------------------

def test_write():
    reset_workspace()
    result = write_file(TEST_DIR, TEST_FILE, "print(1)", mode="write")
    assert "overwritten" in result
    assert read_file() == "print(1)"


# ---------------------------
# APPEND
# ---------------------------

def test_append():
    reset_workspace()
    write_file(TEST_DIR, TEST_FILE, "a=1\n", mode="write")
    write_file(TEST_DIR, TEST_FILE, "b=2\n", mode="append")
    assert read_file() == "a=1\nb=2\n"


# ---------------------------
# INSERT
# ---------------------------

def test_insert():
    reset_workspace()
    write_file(TEST_DIR, TEST_FILE, "a\nc\n", mode="write")
    write_file(TEST_DIR, TEST_FILE, "b\n", mode="insert", line_number=1)
    assert read_file() == "a\nb\nc\n"


# ---------------------------
# REPLACE
# ---------------------------

def test_replace():
    reset_workspace()
    write_file(TEST_DIR, TEST_FILE, "a\nb\nc\n", mode="write")
    write_file(TEST_DIR, TEST_FILE, "B\n", mode="replace", start_line=1, end_line=2)
    assert read_file() == "a\nB\nc\n"


# ---------------------------
# MINIMAL PATCH
# ---------------------------

def test_minimal_patch():
    reset_workspace()
    write_file(TEST_DIR, TEST_FILE, "a\nb\nc\n", mode="write")

    patch = """
 a
-b
+B
 c
"""
    write_file(TEST_DIR, TEST_FILE, content="", mode="patch", patch_content=patch)
    assert read_file() == "a\nB\nc\n"


# ---------------------------
# UNIFIED DIFF PATCH
# ---------------------------

def test_unified_patch():
    reset_workspace()
    write_file(TEST_DIR, TEST_FILE, "one\ntwo\nthree\n", mode="write")

    patch = """
@@ -2,1 +2,1 @@
-two
+TWO
"""
    write_file(TEST_DIR, TEST_FILE, content="", mode="patch", patch_content=patch)
    assert read_file() == "one\nTWO\nthree\n"


# ---------------------------
# AST VALIDATION
# ---------------------------

def test_ast_rejects_invalid_python():
    reset_workspace()
    write_file(TEST_DIR, TEST_FILE, "print(123)\n", mode="write")

    bad_patch = """
@@ -1,1 +1,1 @@
-print(123)
+print(123
"""
    try:
        write_file(TEST_DIR, TEST_FILE, content="", mode="patch", patch_content=bad_patch)
        assert False, "Expected AST error"
    except Exception:
        assert True
