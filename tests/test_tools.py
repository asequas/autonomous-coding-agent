import sys

from conftest import make_ctx, write

from aiagent.tools import ToolContext, default_registry
from aiagent.tools.edit import Edit

REGISTRY = default_registry()


def call(ctx: ToolContext, name: str, **args: object):  # type: ignore[no-untyped-def]
    return REGISTRY.call(name, args, ctx)


def test_list_files_shows_relative_paths_and_skips_noise(ctx: ToolContext) -> None:
    write(ctx, "main.py", "print(1)\n")
    write(ctx, "pkg/util.py", "x = 1\n")
    write(ctx, ".git/HEAD", "ref")
    result = call(ctx, "list_files")
    assert result.ok
    assert "main.py" in result.output and "pkg/util.py" in result.output
    assert ".git" not in result.output


def test_read_file_numbers_lines_and_supports_ranges(ctx: ToolContext) -> None:
    write(ctx, "m.py", "a = 1\nb = 2\nc = 3\n")
    assert (
        call(ctx, "read_file", path="m.py").output == "    1 | a = 1\n    2 | b = 2\n    3 | c = 3"
    )
    assert call(ctx, "read_file", path="m.py", start_line=2, end_line=2).output == "    2 | b = 2"


def test_read_file_truncates_large_files_with_a_continuation_hint(tmp_path) -> None:  # type: ignore[no-untyped-def]
    ctx = make_ctx(tmp_path, max_read_chars=200)
    write(ctx, "big.py", "".join(f"line_{i} = {i}\n" for i in range(100)))
    output = call(ctx, "read_file", path="big.py").output
    assert "[Truncated at line" in output
    assert "start_line=" in output


def test_read_file_errors_are_returned_not_raised(ctx: ToolContext) -> None:
    missing = call(ctx, "read_file", path="nope.py")
    assert not missing.ok and "not a file" in missing.output
    escape = call(ctx, "read_file", path="../../etc/passwd")
    assert not escape.ok and "outside the workspace" in escape.output


def test_search_code_finds_matches(ctx: ToolContext) -> None:
    write(ctx, "a.py", "def foo():\n    return 1\n")
    write(ctx, "b.py", "from a import foo\n")
    output = call(ctx, "search_code", pattern=r"\bfoo\b").output
    assert "a.py:1: def foo():" in output
    assert "b.py:1: from a import foo" in output
    assert not call(ctx, "search_code", pattern="(").ok


def test_apply_patch_edits_and_reports_diff(ctx: ToolContext) -> None:
    write(ctx, "m.py", "x = 1\ny = 2\n")
    result = call(ctx, "apply_patch", path="m.py", patch=" x = 1\n-y = 2\n+y = 3\n")
    assert result.ok
    # The model gets a one-line summary; the diff travels as structured detail.
    assert result.output == "Patched m.py (+1 -1)."
    assert isinstance(result.detail, Edit) and "+y = 3" in result.detail.diff
    assert (ctx.workspace.root / "m.py").read_text() == "x = 1\ny = 3\n"
    assert ctx.changed_files == {"m.py"}
    assert ctx.edit_count == 1


def test_apply_patch_rejects_invalid_python_and_leaves_file_intact(ctx: ToolContext) -> None:
    write(ctx, "m.py", "print(123)\n")
    result = call(ctx, "apply_patch", path="m.py", patch="-print(123)\n+print(123\n")
    assert not result.ok
    assert "would not be valid Python" in result.output
    assert (ctx.workspace.root / "m.py").read_text() == "print(123)\n"
    assert ctx.changed_files == set()


def test_apply_patch_on_missing_file_suggests_write_file(ctx: ToolContext) -> None:
    result = call(ctx, "apply_patch", path="new.py", patch="+x\n")
    assert not result.ok and "write_file" in result.output


def test_write_file_creates_nested_files(ctx: ToolContext) -> None:
    result = call(ctx, "write_file", path="pkg/new.py", content="VALUE = 1\n")
    assert result.ok and result.output.startswith("Created pkg/new.py")
    assert (ctx.workspace.root / "pkg/new.py").read_text() == "VALUE = 1\n"


def test_non_python_files_are_not_syntax_checked(ctx: ToolContext) -> None:
    assert call(ctx, "write_file", path="notes.md", content="print(\n").ok


def test_run_python_captures_output_and_exit_code(ctx: ToolContext) -> None:
    write(ctx, "ok.py", "import sys\nprint(int(sys.argv[1]) * 2)\n")
    output = call(ctx, "run_python", path="ok.py", args=["21"]).output
    assert "[exit code 0]" in output and "42" in output

    write(ctx, "boom.py", "print(1 / 0)\n")
    output = call(ctx, "run_python", path="boom.py").output
    assert "[exit code 1]" in output and "ZeroDivisionError" in output


def test_run_python_times_out(tmp_path) -> None:  # type: ignore[no-untyped-def]
    ctx = make_ctx(tmp_path, command_timeout=0.5)
    write(ctx, "slow.py", "import time\ntime.sleep(5)\n")
    assert "[timed out]" in call(ctx, "run_python", path="slow.py").output


def test_run_python_does_not_leak_secrets(ctx: ToolContext, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("GEMINI_API_KEY", "super-secret")
    write(ctx, "env.py", "import os\nprint(os.environ.get('GEMINI_API_KEY'))\n")
    output = call(ctx, "run_python", path="env.py").output
    assert "super-secret" not in output and "None" in output


def test_run_python_rejects_non_python_files(ctx: ToolContext) -> None:
    write(ctx, "data.txt", "hi")
    assert not call(ctx, "run_python", path="data.txt").ok


def test_registry_validates_tool_names_and_arguments(ctx: ToolContext) -> None:
    unknown = call(ctx, "delete_everything")
    assert not unknown.ok and "Available tools" in unknown.output
    missing = call(ctx, "read_file")
    assert not missing.ok and "missing required argument(s): path" in missing.output
    extra = call(ctx, "read_file", path="x", mode="fast")
    assert not extra.ok and "unexpected argument(s): mode" in extra.output


def test_registry_turns_tool_crashes_into_results(ctx: ToolContext) -> None:
    write(ctx, "m.py", "x = 1\n")
    result = call(ctx, "read_file", path="m.py", start_line="one")
    assert not result.ok and "read_file failed" in result.output


def test_every_tool_declares_a_valid_schema() -> None:
    for tool in REGISTRY.tools:
        assert tool.parameters["type"] == "object"
        assert set(tool.required) <= set(tool.properties), tool.name
    assert sys.executable  # tools run code with the agent's interpreter


def test_protected_directories_are_readable_but_not_writable(ctx: ToolContext) -> None:
    write(ctx, ".git/config", "[core]\n")
    assert call(ctx, "read_file", path=".git/config").ok
    for path in [".git/config", ".venv/lib/site.pth", "pkg/../.git/hooks/pre-commit"]:
        result = call(ctx, "write_file", path=path, content="x\n")
        assert not result.ok and "may not modify" in result.output, path
    patched = call(ctx, "apply_patch", path=".git/config", patch="-[core]\n+[core]\n\tx = 1\n")
    assert not patched.ok
    assert (ctx.workspace.root / ".git/config").read_text() == "[core]\n"


def test_preview_describes_an_edit_without_writing_it(ctx: ToolContext) -> None:
    write(ctx, "m.py", "x = 1\n")
    preview = REGISTRY.preview("apply_patch", {"path": "m.py", "patch": "-x = 1\n+x = 2\n"}, ctx)
    assert preview is not None and preview.ok
    assert isinstance(preview.detail, Edit) and "+x = 2" in preview.detail.diff
    assert (ctx.workspace.root / "m.py").read_text() == "x = 1\n"
    assert ctx.changed_files == set() and ctx.edit_count == 0

    new = REGISTRY.preview("write_file", {"path": "new.py", "content": "y = 1\n"}, ctx)
    assert new is not None and new.output.startswith("Created new.py")
    assert not (ctx.workspace.root / "new.py").exists()


def test_preview_reports_edits_that_would_fail(ctx: ToolContext) -> None:
    write(ctx, "m.py", "x = 1\n")
    bad = REGISTRY.preview("apply_patch", {"path": "m.py", "patch": "-x = 1\n+x = (\n"}, ctx)
    assert bad is not None and not bad.ok and "not be valid Python" in bad.output
    assert REGISTRY.preview("read_file", {"path": "m.py"}, ctx) is None


def test_run_tests_records_its_result_for_reuse(ctx: ToolContext) -> None:
    write(ctx, "test_ok.py", "def test_ok():\n    assert True\n")
    result = call(ctx, "run_tests")
    assert result.ok and ctx.last_tests is not None
    edit_count, verification = ctx.last_tests
    assert edit_count == 0 and verification.status == "passed"


def test_search_code_truncates_long_lines(ctx: ToolContext) -> None:
    write(ctx, "min.js", "x" * 5000 + "needle\n")
    output = call(ctx, "search_code", pattern="needle").output
    assert len(output) < 300
