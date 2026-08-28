"""Deprecated: kept only for backward compatibility.

Use `cv_ranker.llm_client` and `cv_ranker.config` instead. This module now
re-exports the new OpenAI-SDK-based client under its old names so existing
imports keep working.
"""

from cv_ranker.llm_client import LLMClient as OllamaClient  # noqa: F401
from cv_ranker.llm_client import LLMClientConfig as OllamaConfig  # noqa: F401
from cv_ranker.llm_client import LLMClientError as OllamaClientError  # noqa: F401

