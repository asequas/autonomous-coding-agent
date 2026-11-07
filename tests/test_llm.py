from typing import Any

import pytest
from google.genai import errors, types

from aiagent.llm import (
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
        self.calls = 0

    def generate_content(self, **_: Any) -> types.GenerateContentResponse:
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome  # type: ignore[no-any-return]


class FakeClient:
    def __init__(self, outcomes: list[Any]) -> None:
        self.models = FakeModels(outcomes)


def api_error(cls: type[errors.APIError], code: int) -> errors.APIError:
    return cls(code, {"error": {"code": code, "message": "nope", "status": "X"}})


def session(outcomes: list[Any], sleeps: list[float]) -> GeminiSession:
    config = types.GenerateContentConfig()
    return GeminiSession(FakeClient(outcomes), "m", config, max_retries=3, sleep=sleeps.append)  # type: ignore[arg-type]


def test_retries_transient_errors_with_backoff() -> None:
    sleeps: list[float] = []
    chat = session(
        [
            api_error(errors.ServerError, 503),
            api_error(errors.ClientError, 429),
            response(types.Part(text="ok")),
        ],
        sleeps,
    )
    assert chat.send("hi").text == "ok"
    assert len(sleeps) == 2 and 1 <= sleeps[0] < 2 and 2 <= sleeps[1] < 3
    # The model's reply is kept in history so thought signatures round-trip.
    assert [c.role for c in chat.contents] == ["user", "model"]


def test_does_not_retry_client_errors() -> None:
    sleeps: list[float] = []
    chat = session([api_error(errors.ClientError, 400)], sleeps)
    with pytest.raises(LLMError, match="400"):
        chat.send("hi")
    assert sleeps == []


def test_gives_up_after_max_retries() -> None:
    sleeps: list[float] = []
    chat = session([api_error(errors.ServerError, 500)] * 4, sleeps)
    with pytest.raises(LLMError, match="500"):
        chat.send("hi")
    assert len(sleeps) == 3
