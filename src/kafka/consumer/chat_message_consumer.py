from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

from aiokafka import AIOKafkaConsumer

from cv_ranker.db import CVStore
from cv_ranker.llm_client import LLMClient
from kafka.producer.chat_message_producer import CHAT_MESSAGES_TOPIC, ChatMessageProducer

logger = logging.getLogger(__name__)

_POLL_TIMEOUT_MS = 1000

# Total attempts before giving up and dead-lettering, not retries *beyond*
# the first — i.e. this is 3 tries total, not 1 try + 3 retries.
_MAX_ATTEMPTS = 3
_RETRY_BACKOFF_SECONDS = 1


class ChatMessageConsumer:
    """Consumes chat message events from the `chat-messages` topic.

    User messages get a same-process LLM reply (`_on_ai_model_request`,
    tracked for idempotency in `message_responses`), which is itself
    published back to the topic as an assistant event; assistant messages
    are then persisted as a new `messages` row (`_on_ai_model_response`).

    The DB/LLM calls in both handlers are synchronous, so they're each
    offloaded via `asyncio.to_thread` to avoid blocking the event loop this
    consumer shares with the rest of the FastAPI app.
    """

    def __init__(
        self,
        bootstrap_servers: str,
        producer: ChatMessageProducer,
        store: CVStore,
        llm_client: LLMClient,
    ):
        self.consumer = AIOKafkaConsumer(
            CHAT_MESSAGES_TOPIC,
            bootstrap_servers=bootstrap_servers,
            group_id="chat-message-consumer",
            enable_auto_commit=False,
        )
        self.producer = producer
        self._store = store
        self._llm_client = llm_client
        self.running = True

    async def start(self) -> None:
        await self.consumer.start()
        logger.info("Listening for messages on topic '%s'", CHAT_MESSAGES_TOPIC)
        try:
            # `getmany` (rather than `async for`) wakes up every
            # `_POLL_TIMEOUT_MS` even with no new records, so `stop()` is
            # noticed promptly instead of only after the next message arrives.
            while self.running:
                records_by_partition = await self.consumer.getmany(timeout_ms=_POLL_TIMEOUT_MS)
                for records in records_by_partition.values():
                    for record in records:
                        try:
                            await self.handle(record)
                        except Exception:
                            logger.exception("Failed to handle message: %s", record.value)
                        else:
                            await self.consumer.commit()
        finally:
            await self.consumer.stop()
            logger.info("Stopped listening for messages on topic '%s'", CHAT_MESSAGES_TOPIC)

    async def stop(self) -> None:
        self.running = False

    async def _call_with_retries(
        self,
        action: Callable[[], Awaitable[Any]],
        on_give_up: Callable[[Exception], Awaitable[Any]],
        payload: dict[str, Any],
    ) -> tuple[bool, Any]:
        """Call `action()`, retrying up to `_MAX_ATTEMPTS` times total.

        On exhausted failure: awaits `on_give_up(exc)` (e.g. for
        caller-specific logging) and dead-letters `payload` to
        `chat-messages-dlt`, then returns `(False, None)` — dead-lettering
        *is* the terminal handling for this event, so this never raises;
        the caller should treat it like a handled record. Returns
        `(True, result)` on success.
        """
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            try:
                return True, await action()
            except Exception as exc:
                if attempt == _MAX_ATTEMPTS:
                    await on_give_up(exc)
                    await self.producer.publish_to_dlt(payload, error=str(exc), attempts=_MAX_ATTEMPTS)
                    return False, None
                logger.warning("Attempt %s/%s failed, retrying", attempt, _MAX_ATTEMPTS, exc_info=True)
                await asyncio.sleep(_RETRY_BACKOFF_SECONDS)
        return False, None  # unreachable

    async def handle(self, message: Any) -> None:
        payload = json.loads(message.value.decode("utf-8"))
        logger.info("Received chat message: %s", payload)
        if payload["role"] == "assistant":
            await self._on_ai_model_response(payload)
        elif payload["role"] == "user":
            await self._on_ai_model_request(payload)

    async def _on_ai_model_response(self, payload: dict[str, Any]) -> None:
        async def _persist() -> None:
            await asyncio.to_thread(
                self._store.create_message, payload["conversation_id"], payload["role"], payload["content"]
            )

        async def _on_give_up(_exc: Exception) -> None:
            logger.exception(
                "Giving up on assistant message for conversation %s after %s attempts",
                payload["conversation_id"],
                _MAX_ATTEMPTS,
            )

        await self._call_with_retries(_persist, _on_give_up, payload)

    async def _on_ai_model_request(self, payload: dict[str, Any]) -> None:
        message_id = payload["id"]

        async def _claim() -> int | None:
            return await asyncio.to_thread(self._store.create_message_response, message_id)

        async def _on_give_up(_exc: Exception) -> None:
            logger.exception(
                "Giving up on claiming message %s after %s attempts; sending to DLT", message_id, _MAX_ATTEMPTS
            )

        claimed, created = await self._call_with_retries(_claim, _on_give_up, payload)
        if not claimed:
            return

        if created is None:
            logger.info("Message %s already has a response in progress or done; skipping", message_id)
            return

        async def _generate_and_publish() -> str:
            history = await asyncio.to_thread(
                self._store.list_messages_before,
                payload["conversation_id"],
                datetime.fromisoformat(payload["created_at"]),
            )
            chat_messages = [{"role": message.role, "content": message.content} for message in history]
            chat_messages.append({"role": payload["role"], "content": payload["content"]})
            response = await asyncio.to_thread(self._llm_client.generate_chat, chat_messages)
            await self.producer.publish_assistant_reply(payload["conversation_id"], response)
            return response

        async def _on_give_up(_exc: Exception) -> None:
            logger.exception("Giving up on message %s after %s attempts; sending to DLT", message_id, _MAX_ATTEMPTS)

        succeeded, response = await self._call_with_retries(_generate_and_publish, _on_give_up, payload)
        if not succeeded:
            await asyncio.to_thread(self._store.mark_message_response_failed, message_id)
            return

        logger.info("AI response for message %s: %s", message_id, response)
        await asyncio.to_thread(self._store.mark_message_response_succeeded, message_id)
