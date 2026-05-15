import os
import shutil
from aiagent.functions.write_file import write_file

BASE_DIR = os.path.dirname(__file__)
WORKSPACE = os.path.join(BASE_DIR, "multi_patch_workspace")
TEST_FILE = "multi.py"


def reset_workspace():
    if os.path.exists(WORKSPACE):
        shutil.rmtree(WORKSPACE)
    os.makedirs(WORKSPACE)


def read_file():
    with open(os.path.join(WORKSPACE, TEST_FILE), "r", encoding="utf-8") as f:
        return f.read()


def test_patch_multiple_hunks():
    reset_workspace()

    original = """\
a = 1
b = 2
c = 3
d = 4
e = 5
print(a, b, c, d, e)
"""
    write_file(WORKSPACE, TEST_FILE, original, mode="write")

    patch = """\
@@ -1,2 +1,2 @@
-a = 1
+a = 10
 b = 2
@@ -4,2 +4,2 @@
-d = 4
+d = 40
 e = 5
"""

    res = write_file(WORKSPACE, TEST_FILE, None, mode="patch", patch_content=patch)
    assert "Patch applied" in res

    txt = read_file()

    assert "a = 10" in txt
    assert "d = 40" in txt