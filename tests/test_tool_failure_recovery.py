import os
import shutil
from aiagent.functions.write_file import write_file

BASE_DIR = os.path.dirname(__file__)
WORKSPACE = os.path.join(BASE_DIR, "failure_workspace")
TEST_FILE = "demo.py"


def reset_workspace():
    if os.path.exists(WORKSPACE):
        shutil.rmtree(WORKSPACE)
    os.makedirs(WORKSPACE)


def read_file():
    with open(os.path.join(WORKSPACE, TEST_FILE), "r", encoding="utf-8") as f:
        return f.read()


def test_tool_failure_recovery():
    reset_workspace()

    write_file(WORKSPACE, TEST_FILE, "x = 1\ny = 2\nprint(x+y)\n", mode="write")

    bad_patch = """\
@@ -1,1 +1,1 @@
-x = 1
+x = 
"""

    try:
        write_file(WORKSPACE, TEST_FILE, None, mode="patch", patch_content=bad_patch)
        assert False
    except Exception:
        assert True

    good_patch = """\
@@ -1,3 +1,3 @@
-x = 1
+x = 10
 y = 2
 print(x+y)
"""

    res = write_file(WORKSPACE, TEST_FILE, None, mode="patch", patch_content=good_patch)
    assert "Patch applied" in res

    assert "x = 10" in read_file()