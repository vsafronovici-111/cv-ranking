from __future__ import annotations

from dataclasses import dataclass

from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI


class LLMClientError(RuntimeError):
    pass


@dataclass
class LLMClientConfig:
    base_url: str
    api_key: str
    model: str
    timeout_seconds: int = 90


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

