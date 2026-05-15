import os
import sys
from dotenv import load_dotenv
from google import genai
from google.genai import types

from functions.get_files_info import schema_get_files_info, get_files_info
from functions.get_file_content import schema_get_files_content
from functions.write_file import schema_write_file
from functions.run_python_file import schema_run_python_file, run_python_file
from functions.call_functions import call_function
from config import MAX_ITERATIONS, WORKING_DIRECTORY


def choose_file_to_run():
    """Pick a Python file that is safe to run (not agent infrastructure)."""

    files = get_files_info(WORKING_DIRECTORY)
    python_files = [f for f in files if f.endswith(".py")]

    if not python_files:
        return None

    # Ignore internal agent files
    safe_files = [f for f in python_files if os.path.basename(f)]

    # Prefer app.py or server.py or calculator.py, etc.
    priority = ["app.py", "server.py", "calculator.py"]

    for p in priority:
        if p in safe_files:
            return p

    # Otherwise pick the first safe file
    return safe_files[0] if safe_files else None


def main():
    load_dotenv()
    api_key = os.environ.get("GEMINI_API_KEY")
    client = genai.Client(api_key=api_key)

    if len(sys.argv) < 2:
        print("Please provide a prompt as a command-line argument.")
        return

    verbose = "--verbose" in sys.argv

    system_prompt = """
You are an intelligent AI coding agent.

Your job is to understand the user's request, decide whether a tool call is needed, 
and solve the task with the minimum number of steps using the available tools.

AVAILABLE TOOLS:
- list files
- read files
- modify files (write, append, insert, replace, patch)
- run python programs for debugging

CRITICAL RULES FOR CODE EDITING:

1. Always prefer PATCH mode.
   - Use unified diff format whenever possible:
       @@ -old_start,old_len +new_start,new_len @@
       - old line
       + new line
   - Use minimal diff (+/-/space) when unified diffs are not needed.

2. Avoid using write/replace/insert unless patch cannot express the change.

3. NEVER rewrite an entire file unless explicitly instructed by the user.

4. Produce syntactically correct Python.
   - All patches and edits must result in valid Python syntax.
   - A syntax validator (AST) will reject invalid changes.
   - If a patch is rejected, generate a corrected patch and try again.

5. Avoid unnecessary actions:
   - Do not re-read a file unless absolutely required.
   - Do not list directories unless needed.
   - Do not repeat tool calls with the same arguments.

6. After changing a Python file:
   - The program may be executed once for debugging.
   - If execution output shows an error, generate a patch to fix it.
   - Continue fixing until the program runs without errors.

7. Finish cleanly:
   - When the task is complete and the program runs successfully,
     respond with a clear final answer.
"""

    # Initial message
    messages = [
        types.Content(
            role="user",
            parts=[types.Part(text=sys.argv[1])]
        )
    ]

    available_functions = types.Tool(
        function_declarations=[
            schema_get_files_info,
            schema_get_files_content,
            schema_write_file,
            schema_run_python_file,
        ],
    )

    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        tools=[available_functions],
    )

    for i in range(MAX_ITERATIONS):

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=messages,
            config=config,
        )

        # Print usage if verbose
        if verbose and response.usage_metadata:
            print(f"\n--- ITERATION {i+1} ---")
            print("Prompt tokens:", response.usage_metadata.prompt_token_count)
            print("Response tokens:", response.usage_metadata.candidates_token_count)

        # Add model messages
        if response.candidates:
            for candidate in response.candidates:
                if candidate and candidate.content:
                    messages.append(candidate.content)

        if response.function_calls:
            for fn_call in response.function_calls:
                tool_output = call_function(fn_call, verbose)

                # Add tool output back to model conversation
                messages.append(tool_output)

            continue   # Next iteration

        print("\nModel believes final answer is ready. Running debug...")

        file_to_run = choose_file_to_run()

        if file_to_run:
            print(f"Running {file_to_run} for debug...")

            run_out = run_python_file(
                working_directory=WORKING_DIRECTORY,
                file_path=file_to_run,
                args=None
            )

            # Send execution output back to model
            tool_response = types.Content(
                role="tool",
                parts=[
                    types.Part.from_function_response(
                        name="run_python_file",
                        response={"result": run_out}
                    )
                ]
            )

            messages.append(tool_response)

            # If crash → fix
            if "Traceback" in str(run_out) or "Error" in str(run_out):
                print("\nProgram crashed → letting model fix it...")
                continue

            # If no crash → final answer
            print("\n=== PROGRAM RAN SUCCESSFULLY ===")
            print(response.text)
            return

        else:
            # No file to run → finalize
            print("\n=== FINAL ANSWER ===")
            print(response.text)
            return

    print("\nReached MAX_ITERATIONS without a final answer.")

if __name__ == "__main__":
    main()