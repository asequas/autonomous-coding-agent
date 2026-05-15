import os
from config import MAX_CHARS
from google.genai import types


def get_files_content(working_directory, file_path):
    abs_working_directory = os.path.abspath(working_directory)
    abs_file_path = os.path.abspath(os.path.join(abs_working_directory, file_path))
    if not abs_file_path.startswith(abs_working_directory):
        raise ValueError("File must be within the working directory.")
    if not os.path.isfile(abs_file_path):
        raise ValueError("Specified path is not a file.")
    
    with open(abs_file_path, 'r') as file:
        content = file.read(MAX_CHARS)
        if len(content) == MAX_CHARS:
            content += "\n\n[Content truncated due to length]"

    return content

schema_get_files_content = types.FunctionDeclaration(
    name="get_files_content",
    description="Retrieves the content of a specified file relative to the working directory. The content is truncated if it exceeds a certain length.",
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "file_path": types.Schema(
                type=types.Type.STRING,
                description="Path to the file whose content is to be retrieved, relative to the working directory",
            ),

        },
    ),
)