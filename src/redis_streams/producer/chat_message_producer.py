from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import redis.asyncio as redis

from cv_ranker.db import Message

CHAT_MESSAGES_STREAM = "chat-messages-v2"
CHAT_MESSAGES_DLT_STREAM = "chat-messages-v2-dlt"


class ChatMessageStreamProducer:
    """v2 counterpart to `kafka.producer.chat_message_producer.ChatMessageProducer`.

    Same event shapes and same three publish methods, but events are
    written to a Redis Stream (`XADD`) instead of a Kafka topic.
    """

    def __init__(self, url: str):
        self.client = redis.from_url(url, decode_responses=True)

    async def start(self) -> None:
        await self.client.ping()

    async def stop(self) -> None:
        await self.client.aclose()

    async def send(self, stream: str, payload: dict[str, Any]) -> None:
        await self.client.xadd(stream, {"payload": json.dumps(payload)})

    async def publish_message(self, message: Message) -> None:
        payload = {
            "id": message.id,
            "conversation_id": message.conversation_id,
            "role": message.role,
            "content": message.content,
            "created_at": message.created_at.isoformat(),
        }
        await self.send(CHAT_MESSAGES_STREAM, payload)

    async def publish_assistant_reply(self, conversation_id: int, content: str) -> None:
        """Publish an AI-generated reply that doesn't have a `messages` row yet.

        Unlike `publish_message`, there's no `id`/`created_at` here — the
        consumer's `_on_ai_model_response` is what persists this as a new
        `messages` row once it picks the event back up.
        """
        payload = {"conversation_id": conversation_id, "role": "assistant", "content": content}
        await self.send(CHAT_MESSAGES_STREAM, payload)

    async def publish_to_dlt(self, original_payload: dict[str, Any], error: str, attempts: int) -> None:
        """Dead-letter an event from `chat-messages-v2` that failed every retry.

        Wraps the original (still-valid) event payload with failure context
        so `chat-messages-v2-dlt` is self-contained for inspection/replay,
        rather than just the bare original payload.
        """
        envelope = {
            "original": original_payload,
            "error": error,
            "attempts": attempts,
            "failed_at": datetime.now(UTC).isoformat(),
        }
        await self.send(CHAT_MESSAGES_DLT_STREAM, envelope)
