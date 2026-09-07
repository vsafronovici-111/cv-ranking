from __future__ import annotations

from dataclasses import dataclass

import httpx


class EmbeddingClientError(RuntimeError):
    pass


@dataclass
class EmbeddingClientConfig:
    host: str  # e.g. "http://localhost:11434" (Ollama's native API, NOT the /v1 OpenAI-compatible path)
    model: str  # e.g. "qwen3-embedding:4b"
    timeout_seconds: int = 90


class EmbeddingClient:
    """Thin wrapper around Ollama's native `/api/embed` endpoint.

    This is intentionally separate from `LLMClient`: chat/completions go
    through the OpenAI-compatible `/v1` API (shared with vLLM), but text
    embeddings are generated via Ollama's own `/api/embed` endpoint, which
    has a different request/response shape and isn't OpenAI-compatible.

    Example request this wraps:
        curl http://localhost:11434/api/embed \\
          -d '{"model": "qwen3-embedding:4b", "input": "some text"}'
    """

    def __init__(self, config: EmbeddingClientConfig):
        self.config = config
        self._client = httpx.Client(
            base_url=config.host.rstrip("/"),
            timeout=config.timeout_seconds,
        )

    def embed(self, text: str) -> list[float]:
        """Return the embedding vector for `text` as a list of floats."""
        try:
            response = self._client.post(
                "/api/embed",
                json={"model": self.config.model, "input": text},
            )
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise EmbeddingClientError("Embedding request timed out") from exc
        except httpx.ConnectError as exc:
            raise EmbeddingClientError(f"Cannot reach Ollama at {self.config.host}: {exc}") from exc
        except httpx.HTTPStatusError as exc:
            raise EmbeddingClientError(f"Ollama embed request failed: {exc}") from exc

        data = response.json()
        embeddings = data.get("embeddings")
        if not embeddings or not isinstance(embeddings, list) or not embeddings[0]:
            raise EmbeddingClientError(f"Ollama returned no embeddings for model '{self.config.model}'")

        vector = embeddings[0]
        if not isinstance(vector, list):
            raise EmbeddingClientError("Ollama embedding response was not a list of floats")

        return [float(x) for x in vector]

