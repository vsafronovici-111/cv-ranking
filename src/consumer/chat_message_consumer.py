from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass

from kafka import KafkaConsumer

from cv_ranker.kafka_producer import CHAT_MESSAGES_TOPIC

logger = logging.getLogger(__name__)

_POLL_TIMEOUT_MS = 1000


@dataclass
class KafkaConsumerConfig:
    bootstrap_servers: str
    group_id: str = "chat-message-consumer"


class ChatMessageConsumer:
    """Consumes chat message events from the `chat-messages` topic.

    Just logs each message for now; a future change can route these to
    wherever they need to end up (e.g. search indexing, notifications).
    """

    def __init__(self, config: KafkaConsumerConfig):
        self.config = config
        self._consumer = KafkaConsumer(
            CHAT_MESSAGES_TOPIC,
            bootstrap_servers=config.bootstrap_servers,
            group_id=config.group_id,
            value_deserializer=lambda value: json.loads(value.decode("utf-8")),
            auto_offset_reset="earliest",
        )
        self._stop_event = threading.Event()

    def run(self) -> None:
        """Poll for messages, logging each one, until `stop()` is called."""
        logger.info("Listening for messages on topic '%s'", CHAT_MESSAGES_TOPIC)
        try:
            while not self._stop_event.is_set():
                records_by_partition = self._consumer.poll(timeout_ms=_POLL_TIMEOUT_MS)
                for records in records_by_partition.values():
                    for record in records:
                        logger.info("Received chat message: %s", record.value)
        finally:
            self._consumer.close()
            logger.info("Stopped listening for messages on topic '%s'", CHAT_MESSAGES_TOPIC)

    def stop(self) -> None:
        """Signal `run()`'s poll loop to exit; safe to call from another thread."""
        self._stop_event.set()
