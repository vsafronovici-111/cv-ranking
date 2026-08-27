from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any
from urllib import request, error


@dataclass
class OllamaConfig:
    base_url: str = "http://localhost:11434"
    model: str = "qwen3:14b"
    timeout_seconds: int = 90


class OllamaClientError(RuntimeError):
    pass


class OllamaClient:
    def __init__(self, config: OllamaConfig):
        self.config = config

    def generate(self, prompt: str, system: str | None = None) -> str:
        payload: dict[str, Any] = {
            "model": self.config.model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0},
        }
        if system:
            payload["system"] = system

        data = json.dumps(payload).encode("utf-8")
        url = f"{self.config.base_url.rstrip('/')}/api/generate"

        req = request.Request(
            url=url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with request.urlopen(req, timeout=self.config.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except error.URLError as exc:
            raise OllamaClientError(f"Cannot reach Ollama at {self.config.base_url}: {exc}") from exc
        except TimeoutError as exc:
            raise OllamaClientError("Ollama request timed out") from exc

        try:
            parsed = json.loads(raw)
            text = parsed.get("response", "")
        except json.JSONDecodeError as exc:
            raise OllamaClientError(f"Invalid JSON from Ollama: {exc}") from exc

        if not isinstance(text, str):
            raise OllamaClientError("Ollama response field is not text")

        return text.strip()

