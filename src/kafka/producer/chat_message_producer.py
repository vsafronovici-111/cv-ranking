from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from aiokafka import AIOKafkaProducer

from cv_ranker.db import Message

CHAT_MESSAGES_TOPIC = "chat-messages"
CHAT_MESSAGES_DLT_TOPIC = "chat-messages-dlt"


class ChatMessageProducer:
    def __init__(self, bootstrap_servers: str):
        self.producer = AIOKafkaProducer(
            bootstrap_servers=bootstrap_servers,
            acks="all",
            enable_idempotence=True,
        )

    async def start(self):
        await self.producer.start()

    async def stop(self):
        await self.producer.stop()

    async def send(self, topic: str, message: bytes, key: bytes | None = None):
        await self.producer.send_and_wait(
            topic,
            message,
            key=key,
        )

    async def publish_message(self, message: Message) -> None:
        payload = {
            "id": message.id,
            "conversation_id": message.conversation_id,
            "role": message.role,
            "content": message.content,
            "created_at": message.created_at.isoformat(),
        }
        await self.send(
            CHAT_MESSAGES_TOPIC,
            json.dumps(payload).encode("utf-8"),
            key=str(message.conversation_id).encode("utf-8"),
        )

    async def publish_assistant_reply(self, conversation_id: int, content: str) -> None:
        """Publish an AI-generated reply that doesn't have a `messages` row yet.

        Unlike `publish_message`, there's no `id`/`created_at` here — the
        consumer's `_on_ai_model_response` is what persists this as a new
        `messages` row once it picks the event back up.
        """
        payload = {"conversation_id": conversation_id, "role": "assistant", "content": content}
        await self.send(
            CHAT_MESSAGES_TOPIC,
            json.dumps(payload).encode("utf-8"),
            key=str(conversation_id).encode("utf-8"),
        )

    async def publish_to_dlt(self, original_payload: dict[str, Any], error: str, attempts: int) -> None:
        """Dead-letter an event from `chat-messages` that failed every retry.

        Wraps the original (still-valid) event payload with failure context
        so `chat-messages-dlt` is self-contained for inspection/replay,
        rather than just the bare original bytes.
        """
        envelope = {
            "original": original_payload,
            "error": error,
            "attempts": attempts,
            "failed_at": datetime.now(UTC).isoformat(),
        }
        conversation_id = original_payload.get("conversation_id")
        key = str(conversation_id).encode("utf-8") if conversation_id is not None else None
        await self.send(CHAT_MESSAGES_DLT_TOPIC, json.dumps(envelope).encode("utf-8"), key=key)
