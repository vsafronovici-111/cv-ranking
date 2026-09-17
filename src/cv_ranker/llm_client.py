from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI


class LLMClientError(RuntimeError):
    pass


@dataclass
class LLMClientConfig:
    base_url: str
    api_key: str
    model: str
    timeout_seconds: int = 150


class LLMClient:
    """Thin wrapper around the OpenAI SDK's chat completions API.

    Both Ollama (`/v1` endpoint) and vLLM expose OpenAI-compatible chat
    completion APIs, so the same client works against either backend by
    only changing `base_url` / `api_key` / `model` (see `cv_ranker.config`).
    """

    def __init__(self, config: LLMClientConfig):
        self.config = config
        self._client = OpenAI(
            base_url=config.base_url,
            api_key=config.api_key,
            timeout=config.timeout_seconds,
        )

    def generate(self, prompt: str, system: str | None = None) -> str:
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return self.generate_chat(messages)

    def generate_chat(self, messages: list[dict[str, str]]) -> str:
        """Like `generate`, but for a full conversation history of `{role, content}` turns."""
        try:
            response = self._client.chat.completions.create(
                model=self.config.model,
                messages=messages,  # type: ignore[arg-type]
                temperature=0,
            )
        except APITimeoutError as exc:
            raise LLMClientError("LLM request timed out") from exc
        except APIConnectionError as exc:
            raise LLMClientError(f"Cannot reach LLM server at {self.config.base_url}: {exc}") from exc
        except APIStatusError as exc:
            raise LLMClientError(f"LLM server returned an error: {exc}") from exc

        if not response.choices:
            raise LLMClientError("LLM response contained no choices")

        content = response.choices[0].message.content
        if not isinstance(content, str):
            raise LLMClientError("LLM response content is not text")

        return content.strip()

    def generate_tool_call(self, prompt: str, system: str, tool: dict[str, Any]) -> dict[str, Any]:
        """Call the model with a single tool, forced, and return its parsed arguments.

        `tool` is an OpenAI-style tool/function schema
        (`{"type": "function", "function": {"name": ..., "parameters": {...}}}`).
        The model is forced to call it via `tool_choice`, so the return value
        is always the parsed JSON arguments object rather than free-text.
        """
        tool_name = tool["function"]["name"]
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ]

        try:
            response = self._client.chat.completions.create(
                model=self.config.model,
                messages=messages,  # type: ignore[arg-type]
                tools=[tool],  # type: ignore[list-item]
                tool_choice={"type": "function", "function": {"name": tool_name}},
                temperature=0,
            )
        except APITimeoutError as exc:
            raise LLMClientError("LLM request timed out") from exc
        except APIConnectionError as exc:
            raise LLMClientError(f"Cannot reach LLM server at {self.config.base_url}: {exc}") from exc
        except APIStatusError as exc:
            raise LLMClientError(f"LLM server returned an error: {exc}") from exc

        if not response.choices:
            raise LLMClientError("LLM response contained no choices")

        tool_calls = response.choices[0].message.tool_calls
        if not tool_calls:
            raise LLMClientError(f"LLM response contained no call to tool '{tool_name}'")

        call = tool_calls[0]
        if call.function.name != tool_name:
            raise LLMClientError(f"LLM called unexpected tool '{call.function.name}' instead of '{tool_name}'")

        try:
            arguments = json.loads(call.function.arguments)
        except json.JSONDecodeError as exc:
            raise LLMClientError(f"Tool call arguments were not valid JSON: {exc}") from exc

        if not isinstance(arguments, dict):
            raise LLMClientError("Tool call arguments were not a JSON object")

        return arguments
