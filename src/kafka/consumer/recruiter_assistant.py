from __future__ import annotations

import json
import logging
from typing import Any

from cv_ranker.embedding_client import EmbeddingClient, EmbeddingClientError
from cv_ranker.llm_client import LLMClient, LLMClientError
from cv_ranker.qdrant_store import CVVectorStore, CVVectorStoreError

logger = logging.getLogger(__name__)

RECRUITER_SYSTEM_PROMPT = (
    "You are an AI recruiter assistant. You help the user evaluate and discuss "
    "candidate CVs that have already been ingested into the system. When the "
    "user asks you to find, recommend, or rank the best candidates for some "
    "role or search criteria, call the search_candidates tool with that "
    "criteria instead of guessing — it performs a semantic search over the "
    "ingested CVs' embeddings. Base your answer only on the candidates the "
    "tool returns; don't invent candidates it didn't return. For anything "
    "else, reply normally."
)

SEARCH_CANDIDATES_TOOL = {
    "type": "function",
    "function": {
        "name": "search_candidates",
        "description": (
            "Semantically search ingested candidate CVs for the best matches "
            "to free-text job/search criteria (e.g. required skills, role, "
            "years of experience)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "criteria": {
                    "type": "string",
                    "description": "Free-text description of the role/skills/experience to search for.",
                },
                "top_k": {
                    "type": "integer",
                    "description": "Number of candidates to return (default 10).",
                },
            },
            "required": ["criteria"],
        },
    },
}


class RecruiterAssistant:
    """Generates chat replies with a recruiter persona, backed by CV search.

    Wraps `LLMClient` the same way `cv_ranker.ranker.CVRanker` does, but for
    open-ended chat rather than one-shot scoring: every reply is generated
    with a recruiter system prompt prepended, and the model may call the
    `search_candidates` tool (implemented via `EmbeddingClient` +
    `CVVectorStore`, mirroring `cv_ranker.cli._run_find`) to look up matching
    CVs before answering.
    """

    def __init__(self, llm_client: LLMClient, embedding_client: EmbeddingClient, vector_store: CVVectorStore):
        self._llm_client = llm_client
        self._embedding_client = embedding_client
        self._vector_store = vector_store

    def generate_reply(self, messages: list[dict[str, str]]) -> str:
        """Generate the assistant's reply to a `{role, content}` conversation history."""
        chat_messages: list[dict[str, Any]] = [
            {"role": "system", "content": RECRUITER_SYSTEM_PROMPT},
            *messages,
        ]

        message = self._llm_client.generate_chat_with_tools(chat_messages, tools=[SEARCH_CANDIDATES_TOOL])

        if not message.tool_calls:
            content = message.content
            if not isinstance(content, str):
                raise LLMClientError("LLM response content is not text")
            return content.strip()

        call = message.tool_calls[0]
        try:
            arguments = json.loads(call.function.arguments)
        except json.JSONDecodeError as exc:
            raise LLMClientError(f"Tool call arguments were not valid JSON: {exc}") from exc

        criteria = str(arguments.get("criteria", "")).strip()
        top_k = int(arguments.get("top_k") or 10)
        results = self._search_candidates(criteria, top_k) if criteria else []

        chat_messages.append(
            {
                "role": "assistant",
                "content": message.content or "",
                "tool_calls": [
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {"name": call.function.name, "arguments": call.function.arguments},
                    }
                ],
            }
        )
        chat_messages.append({"role": "tool", "tool_call_id": call.id, "content": json.dumps(results)})

        return self._llm_client.generate_chat(chat_messages)

    def _search_candidates(self, criteria: str, top_k: int) -> list[dict[str, Any]]:
        """Embed `criteria` and return the closest CV chunks, mirroring `cv_ranker.cli._run_find`."""

        logger.info("Searching in vector db for criteria: %s", criteria)
        try:
            vector = self._embedding_client.embed(criteria)
            matches = self._vector_store.search_similar(vector, top_k=top_k)
        except (EmbeddingClientError, CVVectorStoreError) as exc:
            logger.warning("Candidate search failed for criteria %r: %s", criteria, exc)
            return []

        return [
            {
                "score": match["score"],
                "cv_id": match["payload"].get("cv_id"),
                "cv_file_name": match["payload"].get("cv_file_name"),
                "chunk_type": match["payload"].get("chunk_type"),
            }
            for match in matches
        ]
