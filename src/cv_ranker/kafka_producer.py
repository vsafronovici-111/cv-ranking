from __future__ import annotations

import json
from dataclasses import dataclass

from kafka import KafkaProducer
from kafka.errors import KafkaError

from cv_ranker.db import Message

CHAT_MESSAGES_TOPIC = "chat-messages"


class ChatMessageProducerError(RuntimeError):
    pass


@dataclass
class KafkaProducerConfig:
    bootstrap_servers: str


class ChatMessageProducer:
    """Publishes chat message events to the `chat-messages` Kafka topic."""

    def __init__(self, config: KafkaProducerConfig):
        self.config = config
        self._producer = KafkaProducer(
            bootstrap_servers=config.bootstrap_servers,
            key_serializer=lambda key: key.encode("utf-8"),
            value_serializer=lambda value: json.dumps(value).encode("utf-8"),
        )

    def publish_message(self, message: Message) -> None:
        payload = {
            "id": message.id,
            "conversation_id": message.conversation_id,
            "role": message.role,
            "content": message.content,
            "created_at": message.created_at.isoformat(),
        }
        try:
            future = self._producer.send(CHAT_MESSAGES_TOPIC, value=payload, key=str(message.conversation_id))
            future.get(timeout=10)
        except KafkaError as exc:
            raise ChatMessageProducerError(f"Failed to publish message {message.id}: {exc}") from exc

    def publish_assistant_reply(self, conversation_id: int, content: str) -> None:
        """Publish an AI-generated reply that doesn't have a `messages` row yet.

        Unlike `publish_message`, there's no `id`/`created_at` here — the
        consumer's `_on_ai_model_response` is what persists this as a new
        `messages` row once it picks the event back up.
        """
        payload = {"conversation_id": conversation_id, "role": "assistant", "content": content}
        try:
            future = self._producer.send(CHAT_MESSAGES_TOPIC, value=payload, key=str(conversation_id))
            future.get(timeout=10)
        except KafkaError as exc:
            raise ChatMessageProducerError(
                f"Failed to publish assistant reply for conversation {conversation_id}: {exc}"
            ) from exc

    def close(self) -> None:
        self._producer.close()
