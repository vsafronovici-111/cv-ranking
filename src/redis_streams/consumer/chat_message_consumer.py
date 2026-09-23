from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

import redis.asyncio as redis
from redis.exceptions import ResponseError

from cv_ranker.db import CVStore
from redis_pubsub.producer.redis_pubsub_producer import RedisPubSubProducer
from redis_streams.consumer.recruiter_agent import RecruiterAgent
from redis_streams.producer.chat_message_producer import CHAT_MESSAGES_STREAM, ChatMessageStreamProducer

logger = logging.getLogger(__name__)

_CONSUMER_GROUP = "chat-message-consumer-v2"
_CONSUMER_NAME = "consumer-1"
_BLOCK_MS = 1000
_READ_COUNT = 10

# Total attempts before giving up and dead-lettering, not retries *beyond*
# the first — i.e. this is 3 tries total, not 1 try + 3 retries.
_MAX_ATTEMPTS = 3
_RETRY_BACKOFF_SECONDS = 1


class ChatMessageStreamConsumer:
    """v2 counterpart to `kafka.consumer.chat_message_consumer.ChatMessageConsumer`.

    Same request/response and idempotency shape (user messages get a
    same-process reply via `_on_ai_model_request`, itself published back to
    the stream as an assistant event; assistant events are persisted as a
    new `messages` row by `_on_ai_model_response`), but consumes the
    `chat-messages-v2` Redis Stream (via a consumer group, `XREADGROUP`)
    instead of a Kafka topic, and generates replies with the LangChain-based
    `RecruiterAgent` instead of `RecruiterAssistant`.

    The DB/LLM calls in both handlers are synchronous, so they're each
    offloaded via `asyncio.to_thread` to avoid blocking the event loop this
    consumer shares with the rest of the FastAPI app.
    """

    def __init__(
        self,
        url: str,
        producer: ChatMessageStreamProducer,
        store: CVStore,
        recruiter_agent: RecruiterAgent,
        redis_pubsub_producer: RedisPubSubProducer,
    ):
        self.client = redis.from_url(url, decode_responses=True)
        self.producer = producer
        self._store = store
        self._recruiter_agent = recruiter_agent
        self._redis_pubsub_producer = redis_pubsub_producer
        self.running = True

    async def _ensure_group(self) -> None:
        try:
            await self.client.xgroup_create(CHAT_MESSAGES_STREAM, _CONSUMER_GROUP, id="0", mkstream=True)
        except ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    async def start(self) -> None:
        await self._ensure_group()
        logger.info("Listening for messages on stream '%s'", CHAT_MESSAGES_STREAM)
        try:
            # A timed `block` (rather than blocking forever) wakes up every
            # `_BLOCK_MS` even with no new entries, so `stop()` is noticed
            # promptly instead of only after the next message arrives.
            while self.running:
                response = await self.client.xreadgroup(
                    _CONSUMER_GROUP,
                    _CONSUMER_NAME,
                    {CHAT_MESSAGES_STREAM: ">"},
                    count=_READ_COUNT,
                    block=_BLOCK_MS,
                )
                if not response:
                    continue
                for _stream_name, entries in response:
                    for entry_id, fields in entries:
                        try:
                            await self.handle(fields)
                        except Exception:
                            logger.exception("Failed to handle message: %s", fields)
                        else:
                            await self.client.xack(CHAT_MESSAGES_STREAM, _CONSUMER_GROUP, entry_id)
        finally:
            await self.client.aclose()
            logger.info("Stopped listening for messages on stream '%s'", CHAT_MESSAGES_STREAM)

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
        `chat-messages-v2-dlt`, then returns `(False, None)` — dead-lettering
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

    async def handle(self, fields: dict[str, str]) -> None:
        payload = json.loads(fields["payload"])
        logger.info("Received chat message: %s", payload)
        if payload["role"] == "assistant":
            await self._on_ai_model_response(payload)
        elif payload["role"] == "user":
            await self._on_ai_model_request(payload)

    async def _on_ai_model_response(self, payload: dict[str, Any]) -> None:
        async def _persist() -> int:
            return await asyncio.to_thread(
                self._store.create_message, payload["conversation_id"], payload["role"], payload["content"]
            )

        async def _on_give_up(_exc: Exception) -> None:
            logger.exception(
                "Giving up on assistant message for conversation %s after %s attempts",
                payload["conversation_id"],
                _MAX_ATTEMPTS,
            )

        succeeded, message_id = await self._call_with_retries(_persist, _on_give_up, payload)
        if not succeeded:
            return

        message = await asyncio.to_thread(self._store.get_message, message_id)
        await self._redis_pubsub_producer.publish_ai_model_response_v2(
            {
                "id": message.id,
                "conversation_id": message.conversation_id,
                "role": message.role,
                "content": message.content,
                "created_at": message.created_at.isoformat(),
            }
        )

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
            response = await asyncio.to_thread(self._recruiter_agent.generate_reply, chat_messages)
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
