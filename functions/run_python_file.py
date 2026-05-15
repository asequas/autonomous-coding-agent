import os
import subprocess
from google.genai import types


def run_python_file(working_directory,file_path, args=[]):
    abs_working_directory=os.path.abspath(working_directory)
    abs_file_path=os.path.abspath(os.path.join(abs_working_directory,file_path))
    if not abs_file_path.startswith(abs_working_directory):
        raise ValueError("File must be within the working directory.")
    if not os.path.isfile(abs_file_path):
        raise ValueError("Specified path is not a file.")
    if not abs_file_path.endswith('.py'):
        raise ValueError("Specified file is not a Python file.")
    try:
        final_args = ['python3', file_path]
        if args:
            final_args.extend(args)
        output=subprocess.run(final_args, cwd=abs_working_directory, timeout=30, capture_output=True, text=True)
        final_string = f"""
                    STDOUT: {output.stdout}
                    STDERR: {output.stderr}"""
        if output.returncode !=0:
            final_string+=f"\n\n[Process exited with return code {output.returncode}]"
        if output.stdout is None and output.stderr is None:
            final_string="\n\n[No output captured from the process]"
        return final_string
    except Exception as e:
        raise ValueError(f"Failed to run the Python file: {e}") 

schema_run_python_file = types.FunctionDeclaration(
    name="run_python_file",
    description="Runs a specified Python file relative to the working directory and captures its output. The file must have a .py extension. Optional arguments can be provided as a list of strings.",
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "file_path": types.Schema(
                type=types.Type.STRING,
                description="Path to the Python file to run, relative to the working directory",
            ),
            "args": types.Schema(
                type=types.Type.ARRAY,
                items=types.Schema(type=types.Type.STRING),
                description="Optional list of arguments to pass to the Python file when running it",
            ),
        },
    ),
)