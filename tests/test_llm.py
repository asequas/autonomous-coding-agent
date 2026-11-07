from typing import Any

import pytest
from google.genai import errors, types

from aiagent.llm import (
    GeminiClient,
    GeminiSession,
    LLMError,
    ToolCall,
    Usage,
    parse_response,
    to_content,
    to_declaration,
)
from aiagent.tools import ToolResult, default_registry


def response(
    *parts: types.Part, reason: types.FinishReason = types.FinishReason.STOP
) -> types.GenerateContentResponse:
    return types.GenerateContentResponse(
        candidates=[
            types.Candidate(
                content=types.Content(role="model", parts=list(parts)), finish_reason=reason
            )
        ],
        usage_metadata=types.GenerateContentResponseUsageMetadata(
            prompt_token_count=100,
            candidates_token_count=20,
            thoughts_token_count=7,
            cached_content_token_count=60,
        ),
    )


def test_tools_become_function_declarations() -> None:
    declarations = [to_declaration(tool) for tool in default_registry().tools]
    names = {d.name for d in declarations}
    assert names == {
        "list_files",
        "read_file",
        "search_code",
        "apply_patch",
        "write_file",
        "run_python",
        "run_tests",
    }
    patch = next(d for d in declarations if d.name == "apply_patch")
    assert patch.parameters_json_schema["required"] == ["path", "patch"]  # type: ignore[index]


def test_tool_results_become_function_responses() -> None:
    content = to_content(
        [
            (ToolCall("read_file", {"path": "a"}, id="c1"), ToolResult(True, "contents")),
            (ToolCall("run_tests", {}, id="c2"), ToolResult(False, "boom")),
        ]
    )
    assert content.role == "user"
    first, second = (part.function_response for part in content.parts or [])
    assert first is not None and second is not None
    assert (first.id, first.name, first.response) == ("c1", "read_file", {"output": "contents"})
    assert second.response == {"error": "boom"}


def test_parse_response_separates_text_thoughts_and_calls() -> None:
    turn = parse_response(
        response(
            types.Part(text="secret reasoning", thought=True),
            types.Part(text="Let me look."),
            types.Part(
                function_call=types.FunctionCall(name="read_file", args={"path": "a.py"}, id="x")
            ),
        )
    )
    assert turn.text == "Let me look."
    assert turn.tool_calls == [ToolCall("read_file", {"path": "a.py"}, "x")]
    assert turn.usage == Usage(100, 27, 60)
    assert turn.finish_reason == "STOP"


def test_parse_response_handles_empty_candidates() -> None:
    turn = parse_response(types.GenerateContentResponse(candidates=[]))
    assert turn.text == "" and turn.tool_calls == []


class FakeModels:
    def __init__(self, outcomes: list[Any]) -> None:
        self.outcomes = outcomes

    def generate_content(self, **_: Any) -> types.GenerateContentResponse:
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome  # type: ignore[no-any-return]


def session(*outcomes: Any) -> GeminiSession:
    return GeminiSession(FakeModels(list(outcomes)), "m", types.GenerateContentConfig())  # type: ignore[arg-type]


def test_session_keeps_model_content_in_history() -> None:
    chat = session(response(types.Part(text="ok")))
    assert chat.send("hi").text == "ok"
    # The model's reply is kept verbatim so thought signatures round-trip.
    assert [c.role for c in chat.contents] == ["user", "model"]


def test_api_errors_become_llm_errors() -> None:
    error = errors.ClientError(400, {"error": {"code": 400, "message": "bad", "status": "X"}})
    with pytest.raises(LLMError, match="400"):
        session(error).send("hi")


def test_client_retries_transient_errors_via_the_sdk() -> None:
    client = GeminiClient("fake-key", "gemini-3.8-flash", max_retries=3)
    options = client.retry_options
    assert options.attempts == 4
    assert options.http_status_codes == [429, 500, 502, 503, 504]
    assert options.max_delay == 30.0
