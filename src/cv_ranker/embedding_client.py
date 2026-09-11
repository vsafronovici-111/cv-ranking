from __future__ import annotations

from dataclasses import dataclass

from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI


class EmbeddingClientError(RuntimeError):
    pass


@dataclass
class EmbeddingClientConfig:
    base_url: str
    api_key: str
    model: str
    timeout_seconds: int = 90


class EmbeddingClient:
    """Thin wrapper around the OpenAI SDK's embeddings API.

    Both Ollama (`/v1` endpoint) and vLLM expose OpenAI-compatible embeddings
    APIs, so the same client works against either backend by only changing
    `base_url` / `api_key` / `model` (see `cv_ranker.config`) — mirrors
    `cv_ranker.llm_client.LLMClient`.
    """

    def __init__(self, config: EmbeddingClientConfig):
        self.config = config
        self._client = OpenAI(
            base_url=config.base_url,
            api_key=config.api_key,
            timeout=config.timeout_seconds,
        )

    def embed(self, text: str) -> list[float]:
        """Return the embedding vector for `text` as a list of floats."""
        try:
            response = self._client.embeddings.create(
                model=self.config.model,
                input=text,
            )
        except APITimeoutError as exc:
            raise EmbeddingClientError("Embedding request timed out") from exc
        except APIConnectionError as exc:
            raise EmbeddingClientError(f"Cannot reach embedding server at {self.config.base_url}: {exc}") from exc
        except APIStatusError as exc:
            raise EmbeddingClientError(f"Embedding server returned an error: {exc}") from exc

        if not response.data:
            raise EmbeddingClientError(f"Embedding server returned no data for model '{self.config.model}'")

        return [float(x) for x in response.data[0].embedding]
