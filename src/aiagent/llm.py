"""LLM adapters.

The agent talks to a model through the small ``LLMClient``/``ChatSession``
protocol below. ``GeminiClient`` is the real implementation; ``ScriptedClient``
replays canned turns, which lets the whole agent loop run offline in tests.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from google import genai
from google.genai import errors, types
from google.genai.models import Models

from aiagent.config import PRICES
from aiagent.tools import Tool, ToolResult

RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})


class LLMError(RuntimeError):
    """The model could not be reached or returned something unusable."""


@dataclass(frozen=True)
class ToolCall:
    name: str
    args: dict[str, Any]
    id: str | None = None


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0  # includes cached_tokens
    output_tokens: int = 0
    cached_tokens: int = 0

    def __add__(self, other: Usage) -> Usage:
        return Usage(
            self.input_tokens + other.input_tokens,
            self.output_tokens + other.output_tokens,
            self.cached_tokens + other.cached_tokens,
        )

    def cost(self, model: str) -> float | None:
        """Estimated USD cost at list prices, or None for a model without a price."""
        price = PRICES.get(model)
        if price is None:
            return None
        uncached = self.input_tokens - self.cached_tokens
        return (
            uncached * price.input
            + self.cached_tokens * price.cached_input
            + self.output_tokens * price.output
        ) / 1_000_000


@dataclass(frozen=True)
class ModelTurn:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: Usage = Usage()
    finish_reason: str | None = None


ToolOutcome = tuple[ToolCall, ToolResult]
Message = str | Sequence[ToolOutcome]


class ChatSession(Protocol):
    def send(self, message: Message) -> ModelTurn:
        """Send user text or tool results and return the model's next turn."""
        ...


class LLMClient(Protocol):
    model: str

    def start(self, system_prompt: str, tools: Sequence[Tool]) -> ChatSession: ...


class GeminiClient:
    def __init__(self, api_key: str, model: str, *, max_retries: int = 5) -> None:
        self.model = model
        # The SDK retries rate limits and server errors with exponential backoff and jitter.
        self.retry_options = types.HttpRetryOptions(
            attempts=max_retries + 1,
            initial_delay=1.0,
            max_delay=30.0,
            http_status_codes=sorted(RETRYABLE_STATUS),
        )
        self._client = genai.Client(
            api_key=api_key, http_options=types.HttpOptions(retry_options=self.retry_options)
        )

    def start(self, system_prompt: str, tools: Sequence[Tool]) -> GeminiSession:
        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            tools=[types.Tool(function_declarations=[to_declaration(tool) for tool in tools])],
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )
        return GeminiSession(self._client.models, self.model, config)


def to_declaration(tool: Tool) -> types.FunctionDeclaration:
    return types.FunctionDeclaration(
        name=tool.name,
        description=tool.description,
        parameters_json_schema=tool.parameters,
    )


def to_content(message: Message) -> types.Content:
    if isinstance(message, str):
        return types.Content(role="user", parts=[types.Part(text=message)])
    parts = [
        types.Part(
            function_response=types.FunctionResponse(
                id=call.id,
                name=call.name,
                response={"output": result.output} if result.ok else {"error": result.output},
            )
        )
        for call, result in message
    ]
    return types.Content(role="user", parts=parts)


def first_candidate(response: types.GenerateContentResponse) -> types.Candidate | None:
    return response.candidates[0] if response.candidates else None


def parse_response(response: types.GenerateContentResponse) -> ModelTurn:
    candidate = first_candidate(response)
    parts = (candidate.content.parts if candidate and candidate.content else None) or []

    text = "".join(part.text for part in parts if part.text and not part.thought)
    calls = [
        ToolCall(
            part.function_call.name or "",
            dict(part.function_call.args or {}),
            part.function_call.id,
        )
        for part in parts
        if part.function_call
    ]
    meta = response.usage_metadata
    usage = (
        Usage(
            meta.prompt_token_count or 0,
            (meta.candidates_token_count or 0) + (meta.thoughts_token_count or 0),
            meta.cached_content_token_count or 0,
        )
        if meta
        else Usage()
    )
    reason = candidate.finish_reason.name if candidate and candidate.finish_reason else None
    return ModelTurn(text.strip(), calls, usage, reason)


class GeminiSession:
    def __init__(self, models: Models, model: str, config: types.GenerateContentConfig) -> None:
        self._models = models
        self._model = model
        self._config = config
        self.contents: list[types.Content] = []

    def send(self, message: Message) -> ModelTurn:
        self.contents.append(to_content(message))
        try:
            response = self._models.generate_content(
                model=self._model, contents=self.contents, config=self._config
            )
        except errors.APIError as exc:
            raise LLMError(f"Gemini API error {exc.code}: {exc.message}") from exc
        candidate = first_candidate(response)
        if candidate and candidate.content and candidate.content.parts:
            # Append the model's content verbatim: Gemini's thinking models need
            # their thought signatures sent back on the next request.
            self.contents.append(candidate.content)
        return parse_response(response)


class ScriptedClient:
    """Replays a fixed sequence of model turns; records everything it is sent."""

    def __init__(self, turns: Sequence[ModelTurn], model: str = "scripted") -> None:
        self.model = model
        self._turns = list(turns)
        self.system_prompt = ""
        self.received: list[Message] = []

    def start(self, system_prompt: str, tools: Sequence[Tool]) -> ScriptedClient:
        self.system_prompt = system_prompt
        return self

    def send(self, message: Message) -> ModelTurn:
        self.received.append(message)
        if not self._turns:
            raise LLMError("Scripted conversation ran out of turns.")
        return self._turns.pop(0)
