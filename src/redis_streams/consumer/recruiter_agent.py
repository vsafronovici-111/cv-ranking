from __future__ import annotations

import logging
from typing import Any

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

from cv_ranker.embedding_client import EmbeddingClient, EmbeddingClientError
from cv_ranker.llm_client import LLMClientConfig, LLMClientError
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


class RecruiterAgent:
    """LangChain-based counterpart to `kafka.consumer.recruiter_assistant.RecruiterAssistant`.

    `RecruiterAssistant` drives the request/response and tool-calling flow
    by hand: call the model, inspect `tool_calls`, invoke the tool itself,
    append a `role: "tool"` message, call the model again. This class wraps
    the same `search_candidates` capability as a LangChain tool and lets
    `langchain.agents.create_agent`'s prebuilt tool-calling loop drive that
    instead, via an OpenAI-compatible `ChatOpenAI` model (works against the
    same Ollama/vLLM backends as `LLMClient`).
    """

    def __init__(self, llm_config: LLMClientConfig, embedding_client: EmbeddingClient, vector_store: CVVectorStore):
        self._embedding_client = embedding_client
        self._vector_store = vector_store

        chat_model = ChatOpenAI(
            base_url=llm_config.base_url,
            api_key=llm_config.api_key,
            model=llm_config.model,
            timeout=llm_config.timeout_seconds,
            temperature=0,
        )

        @tool
        def search_candidates(criteria: str, top_k: int = 10) -> list[dict[str, Any]]:
            """Semantically search ingested candidate CVs for the best matches to
            free-text job/search criteria (e.g. required skills, role, years of
            experience)."""
            return self._search_candidates(criteria, top_k)

        self._graph = create_agent(model=chat_model, tools=[search_candidates], system_prompt=RECRUITER_SYSTEM_PROMPT)

    def generate_reply(self, messages: list[dict[str, str]]) -> str:
        """Generate the assistant's reply to a `{role, content}` conversation history."""
        if not messages:
            raise LLMClientError("Cannot generate a reply for an empty conversation")

        chat_messages: list[BaseMessage] = [
            AIMessage(content=entry["content"])
            if entry["role"] == "assistant"
            else HumanMessage(content=entry["content"])
            for entry in messages
        ]

        result = self._graph.invoke({"messages": chat_messages})
        content = result["messages"][-1].content
        if not isinstance(content, str):
            raise LLMClientError("LangChain agent response content is not text")
        return content.strip()

    def _search_candidates(self, criteria: str, top_k: int) -> list[dict[str, Any]]:
        """Embed `criteria` and return the closest CV chunks, mirroring `RecruiterAssistant._search_candidates`."""

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
