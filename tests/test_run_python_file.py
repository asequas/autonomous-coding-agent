import os
import shutil
from aiagent.functions.run_python_file import run_python_file
from aiagent.functions.write_file import write_file

BASE_DIR = os.path.dirname(__file__)
WORKSPACE = os.path.join(BASE_DIR, "run_workspace")
TEST_FILE = "demo.py"


def reset_workspace():
    if os.path.exists(WORKSPACE):
        shutil.rmtree(WORKSPACE)
    os.makedirs(WORKSPACE)


def test_run_python_file_success():
    reset_workspace()
    write_file(WORKSPACE, TEST_FILE, "print(5+7)", mode="write")
    output = run_python_file(WORKSPACE, TEST_FILE, args=None)
    assert "12" in str(output)


def test_run_python_file_with_args():
    reset_workspace()
    code = """\
import sys
print(int(sys.argv[1]) * 2)
"""
    write_file(WORKSPACE, TEST_FILE, code, mode="write")
    output = run_python_file(WORKSPACE, TEST_FILE, args=["10"])
    assert "20" in str(output)


def test_run_python_file_syntax_error():
    reset_workspace()
    write_file(WORKSPACE, TEST_FILE, "print(5+)", mode="write")
    output = run_python_file(WORKSPACE, TEST_FILE, args=None)
    assert "SyntaxError" in str(output)


def test_run_python_file_runtime_error():
    reset_workspace()
    write_file(WORKSPACE, TEST_FILE, "print(10/0)", mode="write")
    output = run_python_file(WORKSPACE, TEST_FILE, args=None)
    assert "ZeroDivisionError" in str(output)