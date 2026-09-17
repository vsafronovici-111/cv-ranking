from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from kafka import KafkaConsumer

from cv_ranker.db import CVStore
from cv_ranker.kafka_producer import CHAT_MESSAGES_TOPIC, ChatMessageProducer, ChatMessageProducerError
from cv_ranker.llm_client import LLMClient, LLMClientError

logger = logging.getLogger(__name__)

_POLL_TIMEOUT_MS = 1000


@dataclass
class KafkaConsumerConfig:
    bootstrap_servers: str
    group_id: str = "chat-message-consumer"


class ChatMessageConsumer:
    """Consumes chat message events from the `chat-messages` topic.

    User messages get a same-process LLM reply (`_on_ai_model_request`,
    tracked for idempotency in `message_responses`), which is itself
    published back to the topic as an assistant event; assistant messages
    are then persisted as a new `messages` row (`_on_ai_model_response`).
    """

    def __init__(
        self, config: KafkaConsumerConfig, store: CVStore, llm_client: LLMClient, producer: ChatMessageProducer
    ):
        self.config = config
        self._store = store
        self._llm_client = llm_client
        self._producer = producer
        self._consumer = KafkaConsumer(
            CHAT_MESSAGES_TOPIC,
            bootstrap_servers=config.bootstrap_servers,
            group_id=config.group_id,
            value_deserializer=lambda value: json.loads(value.decode("utf-8")),
            auto_offset_reset="earliest",
        )
        self._stop_event = threading.Event()

    def run(self) -> None:
        """Poll for messages, handling each one, until `stop()` is called."""
        logger.info("Listening for messages on topic '%s'", CHAT_MESSAGES_TOPIC)
        try:
            while not self._stop_event.is_set():
                records_by_partition = self._consumer.poll(timeout_ms=_POLL_TIMEOUT_MS)
                for records in records_by_partition.values():
                    for record in records:
                        logger.info("Received chat message: %s", record.value)
                        self._handle_message(record.value)
        finally:
            self._consumer.close()
            logger.info("Stopped listening for messages on topic '%s'", CHAT_MESSAGES_TOPIC)

    def stop(self) -> None:
        """Signal `run()`'s poll loop to exit; safe to call from another thread."""
        self._stop_event.set()

    def _handle_message(self, payload: dict[str, Any]) -> None:
        if payload["role"] == "assistant":
            self._on_ai_model_response(payload)
        elif payload["role"] == "user":
            self._on_ai_model_request(payload)

    def _on_ai_model_response(self, payload: dict[str, Any]) -> None:
        self._store.create_message(payload["conversation_id"], payload["role"], payload["content"])

    def _on_ai_model_request(self, payload: dict[str, Any]) -> None:
        message_id = payload["id"]
        if self._store.create_message_response(message_id) is None:
            logger.info("Message %s already has a response in progress or done; skipping", message_id)
            return

        history = self._store.list_messages_before(
            payload["conversation_id"], datetime.fromisoformat(payload["created_at"])
        )
        chat_messages = [{"role": message.role, "content": message.content} for message in history]
        chat_messages.append({"role": payload["role"], "content": payload["content"]})

        try:
            response = self._llm_client.generate_chat(chat_messages)
            self._producer.publish_assistant_reply(payload["conversation_id"], response)
        except (LLMClientError, ChatMessageProducerError):
            logger.exception("Failed to generate/publish AI response for message %s", message_id)
            self._store.mark_message_response_failed(message_id)
            return

        logger.info("AI response for message %s: %s", message_id, response)
        self._store.mark_message_response_succeeded(message_id)
