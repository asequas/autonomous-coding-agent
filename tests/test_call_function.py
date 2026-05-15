import os
import shutil
from aiagent.functions.call_functions import call_function
from aiagent.functions.write_file import write_file
from aiagent.functions.run_python_file import run_python_file
from aiagent.functions.get_file_content import get_files_content
from aiagent.functions.get_files_info import get_files_info
from google.genai.types import ToolFunctionCall, FunctionCallPart
from google.genai import types

BASE_DIR = os.path.dirname(__file__)
WORKSPACE = os.path.join(BASE_DIR, "call_fn_workspace")
TEST_FILE = "demo.py"


def reset_workspace():
    if os.path.exists(WORKSPACE):
        shutil.rmtree(WORKSPACE)
    os.makedirs(WORKSPACE)


def make_fn(name, args):
    return ToolFunctionCall(parts=[FunctionCallPart(name=name, args=args)])


def read_file():
    with open(os.path.join(WORKSPACE, TEST_FILE), "r", encoding="utf-8") as f:
        return f.read()


def test_call_write_file():
    reset_workspace()
    fn = make_fn("write_file", {
        "file_path": TEST_FILE,
        "content": "print(1)",
        "mode": "write"
    })
    out = call_function(fn, verbose=False)
    assert "result" in out.parts[0].function_response.response
    assert "overwritten" in out.parts[0].function_response.response["result"]


def test_call_get_files_info():
    reset_workspace()
    write_file(WORKSPACE, TEST_FILE, "print(1)", mode="write")
    fn = make_fn("get_files_info", {"directory": None})
    out = call_function(fn)
    assert "result" in out.parts[0].function_response.response
    assert TEST_FILE in str(out.parts[0].function_response.response["result"])


def test_call_get_files_content():
    reset_workspace()
    write_file(WORKSPACE, TEST_FILE, "print(2)", mode="write")
    fn = make_fn("get_files_content", {"file_path": TEST_FILE})
    out = call_function(fn)
    res = out.parts[0].function_response.response["result"]
    assert "print(2)" in str(res)


def test_call_run_python_file():
    reset_workspace()
    write_file(WORKSPACE, TEST_FILE, "print(3)", mode="write")
    fn = make_fn("run_python_file", {"file_path": TEST_FILE, "args": None})
    out = call_function(fn)
    res = out.parts[0].function_response.response["result"]
    assert "3" in str(res)


def test_call_unknown_function():
    fn = make_fn("unknown_tool", {})
    out = call_function(fn)
    assert "error" in out.parts[0].function_response.response