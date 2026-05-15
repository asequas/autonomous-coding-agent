import os
import shutil
from aiagent.functions.write_file import write_file
from aiagent.functions.run_python_file import run_python_file


BASE_DIR = os.path.dirname(__file__)
WORKSPACE = os.path.join(BASE_DIR, "agent_workspace")
TEST_FILE = "demo.py"


def reset_workspace():
    if os.path.exists(WORKSPACE):
        shutil.rmtree(WORKSPACE)
    os.makedirs(WORKSPACE)


def write_demo_file():
    code = """\
def add(a, b):
    return a + b

print(add(1, 2))
"""
    write_file(WORKSPACE, TEST_FILE, code, mode="write")


def read_workspace_file():
    abs_path = os.path.join(WORKSPACE, TEST_FILE)
    with open(abs_path, "r", encoding="utf-8") as f:
        return f.read()


def test_agent_basic_flow():
    """
    Simulates a single-agent-cycle:
    1. Prepare a dummy source file
    2. Apply a small patch
    3. Validate that patch applied correctly
    4. Run the file and ensure it executes
    """

    reset_workspace()
    write_demo_file()

    # Small patch: rename function add -> add_numbers
    patch = """\
@@ -1,2 +1,2 @@
-def add(a, b):
+def add_numbers(a, b):
@@ -4,1 +4,1 @@
-print(add(1, 2))
+print(add_numbers(1, 2))
"""

    # Apply patch
    result = write_file(
        WORKSPACE,
        TEST_FILE,
        content=None,
        mode="patch",
        patch_content=patch
    )

    assert "Patch applied" in result

    # Verify file content updated
    updated = read_workspace_file()
    assert "add_numbers" in updated

    # Execute file
    run_result = run_python_file(WORKSPACE, TEST_FILE, args=None)

    # Should print "3"
    assert "3" in str(run_result)