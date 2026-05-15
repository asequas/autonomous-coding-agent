from functions.get_files_info import get_files_info
from functions.get_file_content import get_files_content
from functions.write_file import write_file
from functions.run_python_file import run_python_file
from google.genai import types
from config import WORKING_DIRECTORY

working_directory = WORKING_DIRECTORY

def call_function(function_call_part, verbose=False):
    function_name = function_call_part.name
    function_args = function_call_part.args

    if verbose:
        print(f"Calling function: {function_name} with arguments: {function_args}")

    try:
        if function_name == "get_files_info":
            result = get_files_info(
                working_directory=working_directory,
                directory=function_args.get("directory")
            )

        elif function_name == "get_files_content":
            result = get_files_content(
                working_directory=working_directory,
                file_path=function_args.get("file_path")
            )

        elif function_name == "write_file":
            result = write_file(
                working_directory=working_directory,
                file_path=function_args.get("file_path"),
                content=function_args.get("content"),
                mode=function_args.get("mode"),
                line_number=function_args.get("line_number"),
                start_line=function_args.get("start_line"),
                end_line=function_args.get("end_line"),
                patch_content=function_args.get("patch_content")
            )

        elif function_name == "run_python_file":
            result = run_python_file(
                working_directory=working_directory,
                file_path=function_args.get("file_path"),
                args=function_args.get("args")
            )

        else:
            result = {"error": f"Unknown function: {function_name}"}

        return types.Content(
            role="tool",
            parts=[
                types.Part.from_function_response(
                    name=function_name,
                    response={"result": result}
                )
            ]
        )

    except Exception as e:
        return types.Content(
            role="tool",
            parts=[
                types.Part.from_function_response(
                    name=function_name,
                    response={"error": str(e)}
                )
            ]
        )