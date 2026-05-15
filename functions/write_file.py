import os
import re
import ast
from google.genai import types

def is_valid_python(source_code: str) -> bool:
    """Return True if source_code is syntactically valid Python."""
    try:
        ast.parse(source_code)
        return True
    except SyntaxError:
        return False

def validate_if_python(abs_file_path: str, new_text: str):
    """Only validate syntax if writing into a .py file."""
    if abs_file_path.endswith(".py"):
        if not is_valid_python(new_text):
            raise ValueError(
                "The applied change produced invalid Python syntax. Patch/Write rejected."
            )

def apply_patch(original_lines, patch_content):
    """
    Detect the correct patch type and apply it.
    Unified diff (@@...) → apply_unified_diff
    Minimal diff (+/-/space) → apply_minimal_diff
    """

    patch_lines = patch_content.splitlines()

    # Detect unified diff markers anywhere
    if any(line.startswith("@@") for line in patch_lines):
        return apply_unified_diff(original_lines, patch_lines)

    return apply_minimal_diff(original_lines, patch_lines)


def apply_unified_diff(original_lines, patch_lines):
    new_lines = []
    pointer = 0
    i = 0

    while i < len(patch_lines):
        line = patch_lines[i]

        if line.startswith("@@"):
            hunk = re.match(r"@@ -(\d+),?(\d*) \+(\d+),?(\d*) @@", line)
            if not hunk:
                raise ValueError(f"Invalid unified diff header: {line}")

            old_start = int(hunk.group(1)) - 1
            old_len = int(hunk.group(2)) if hunk.group(2) else 1
            new_start = int(hunk.group(3)) - 1
            new_len = int(hunk.group(4)) if hunk.group(4) else 1

            # Add unchanged block before the hunk
            new_lines.extend(original_lines[pointer:old_start])
            pointer = old_start

            i += 1
            while i < len(patch_lines) and not patch_lines[i].startswith("@@"):
                pline = patch_lines[i]

                if pline.startswith(" "):
                    new_lines.append(original_lines[pointer])
                    pointer += 1

                elif pline.startswith("-"):
                    pointer += 1  # skip/deleting the line

                elif pline.startswith("+"):
                    new_lines.append(pline[1:] + "\n")

                elif pline.strip() == "":
                    pass  # ignore blank lines

                else:
                    raise ValueError(f"Invalid hunk line: {pline}")

                i += 1

        else:
            i += 1

    new_lines.extend(original_lines[pointer:])
    return new_lines


def apply_minimal_diff(original_lines, patch_lines):
    new_lines = []
    original_pointer = 0

    for line in patch_lines:
        line = line.rstrip("\n")

        if line.startswith(" "):
            expected = line[1:]
            if original_pointer >= len(original_lines):
                raise ValueError("Patch context exceeds file length.")

            if original_lines[original_pointer].rstrip("\n") != expected:
                raise ValueError(
                    f"Context mismatch: expected '{expected}', found '{original_lines[original_pointer].rstrip()}'"
                )

            new_lines.append(original_lines[original_pointer])
            original_pointer += 1

        elif line.startswith("-"):
            expected = line[1:]
            if original_pointer >= len(original_lines):
                raise ValueError("Patch delete exceeds file length.")

            if original_lines[original_pointer].rstrip("\n") != expected:
                raise ValueError(
                    f"Delete mismatch: expected '{expected}', found '{original_lines[original_pointer].rstrip()}'"
                )

            original_pointer += 1

        elif line.startswith("+"):
            new_lines.append(line[1:] + "\n")

        elif line.strip() == "":
            continue

        else:
            raise ValueError(f"Invalid minimal patch line: {line}")

    new_lines.extend(original_lines[original_pointer:])
    return new_lines

def write_file(
        working_directory,
        file_path,
        content,
        mode='write',
        line_number=None,
        start_line=None,
        end_line=None,
        patch_content=None
):
    """
    Supported modes:
        - write
        - append
        - insert
        - replace
        - patch (diff-based)
    """

    # ----- Safe path resolution -----
    abs_working_directory = os.path.abspath(working_directory)
    abs_file_path = os.path.abspath(os.path.join(abs_working_directory, file_path))

    if not abs_file_path.startswith(abs_working_directory):
        raise ValueError("File must be within the working directory.")

    # Make sure target directory exists
    parent_dir = os.path.dirname(abs_file_path)
    os.makedirs(parent_dir, exist_ok=True)

    if mode == "write":
        try:
            validate_if_python(abs_file_path, content)
            with open(abs_file_path, "w", encoding="utf-8") as f:
                f.write(content)
            return f"File '{file_path}' overwritten."
        except Exception as e:
            raise ValueError(f"Write failed: {e}")

    elif mode == "append":
        try:
            with open(abs_file_path, "r", encoding="utf-8") as f:
                new_text = f.read() + content

            validate_if_python(abs_file_path, new_text)

            with open(abs_file_path, "w", encoding="utf-8") as f:
                f.write(new_text)

            return f"Content appended to '{file_path}'."
        except Exception as e:
            raise ValueError(f"Append failed: {e}")

    elif mode == "insert":
        if line_number is None:
            raise ValueError("line_number required for insert mode.")

        try:
            with open(abs_file_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            if line_number < 0 or line_number > len(lines):
                raise ValueError("line_number out of range.")

            insert_lines = content.splitlines(keepends=True)
            for i, l in enumerate(insert_lines):
                if not l.endswith("\n"):
                    insert_lines[i] = l + "\n"

            lines[line_number:line_number] = insert_lines

            new_text = "".join(lines)
            validate_if_python(abs_file_path, new_text)

            with open(abs_file_path, "w", encoding="utf-8") as f:
                f.write(new_text)

            return f"Inserted at line {line_number} in '{file_path}'."

        except Exception as e:
            raise ValueError(f"Insert failed: {e}")

    elif mode == "replace":
        if start_line is None or end_line is None:
            raise ValueError("start_line and end_line required for replace mode.")

        try:
            with open(abs_file_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            if start_line < 0 or end_line > len(lines) or start_line >= end_line:
                raise ValueError("Invalid line range.")

            replacement = content.splitlines(keepends=True)
            for i, l in enumerate(replacement):
                if not l.endswith("\n"):
                    replacement[i] = l + "\n"

            lines[start_line:end_line] = replacement

            new_text = "".join(lines)
            validate_if_python(abs_file_path, new_text)

            with open(abs_file_path, "w", encoding="utf-8") as f:
                f.write(new_text)

            return f"Replaced lines {start_line}-{end_line} in '{file_path}'."

        except Exception as e:
            raise ValueError(f"Replace failed: {e}")

    elif mode == "patch":
        if not patch_content:
            raise ValueError("patch_content required for patch mode.")

        try:
            with open(abs_file_path, "r", encoding="utf-8") as f:
                original_lines = f.readlines()

            new_lines = apply_patch(original_lines, patch_content)
            new_text = "".join(new_lines)

            validate_if_python(abs_file_path, new_text)

            with open(abs_file_path, "w", encoding="utf-8") as f:
                f.write(new_text)

            return f"Patch applied to '{file_path}'."

        except Exception as e:
            raise ValueError(f"Patch failed: {e}")

    else:
        raise ValueError("Invalid mode. Must be one of: write, append, insert, replace, patch.")

schema_write_file = types.FunctionDeclaration(
    name="write_file",
    description=(
        "Modify files using structured editing operations:\n"
        "- write: overwrite entire file\n"
        "- append: add content to end\n"
        "- insert: add content at a specific line\n"
        "- replace: replace a range of lines\n"
        "- patch: apply a unified diff or minimal patch\n\n"
        "Use ONLY 'content' for write/append/insert/replace modes.\n"
        "Use ONLY 'patch_content' for patch mode.\n"
        "Never provide both fields at the same time."
    ),
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "file_path": types.Schema(type=types.Type.STRING),
            "content": types.Schema(type=types.Type.STRING),
            "patch_content": types.Schema(type=types.Type.STRING),
            "mode": types.Schema(type=types.Type.STRING),
            "line_number": types.Schema(type=types.Type.INTEGER),
            "start_line": types.Schema(type=types.Type.INTEGER),
            "end_line": types.Schema(type=types.Type.INTEGER),
        },
        required=["file_path", "mode"]
    ),
) 