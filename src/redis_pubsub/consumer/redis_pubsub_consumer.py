from __future__ import annotations

import json
import logging

import redis.asyncio as redis

from cv_ranker.websocket_manager import WSConnectionManager
from redis_pubsub.producer.redis_pubsub_producer import AI_MODEL_RESPONSE_CHANNEL

logger = logging.getLogger(__name__)

_POLL_TIMEOUT_SECONDS = 1.0


class RedisPubSubConsumer:
    """Subscribes to `AI_MODEL_RESPONSE_CHANNEL`, logs each message received,
    and relays it to the `conversations/{conversation_id}` WebSocket topic."""

    def __init__(self, url: str, ws_connection_manager: WSConnectionManager):
        self.client = redis.from_url(url, decode_responses=True)
        self.pubsub = self.client.pubsub()
        self._ws_connection_manager = ws_connection_manager
        self.running = True

    async def start(self) -> None:
        await self.pubsub.subscribe(AI_MODEL_RESPONSE_CHANNEL)
        logger.info("Listening for messages on channel '%s'", AI_MODEL_RESPONSE_CHANNEL)
        try:
            # A timed `get_message` (rather than the blocking `listen()`
            # iterator) wakes up every `_POLL_TIMEOUT_SECONDS` even with no
            # new messages, so `stop()` is noticed promptly instead of only
            # after the next message arrives.
            while self.running:
                message = await self.pubsub.get_message(ignore_subscribe_messages=True, timeout=_POLL_TIMEOUT_SECONDS)
                if message is None:
                    continue
                try:
                    await self.handle(message)
                except Exception:
                    logger.exception("Failed to handle message: %s", message)
        finally:
            await self.pubsub.unsubscribe(AI_MODEL_RESPONSE_CHANNEL)
            await self.pubsub.aclose()
            await self.client.aclose()
            logger.info("Stopped listening for messages on channel '%s'", AI_MODEL_RESPONSE_CHANNEL)

    async def stop(self) -> None:
        self.running = False

    async def handle(self, message: dict) -> None:
        logger.info("Received AI model response on '%s': %s", message["channel"], message["data"])
        payload = json.loads(message["data"])
        await self._ws_connection_manager.broadcast(payload["conversation_id"], payload)
