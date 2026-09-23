from __future__ import annotations

import json
from typing import Any

import redis.asyncio as redis

AI_MODEL_RESPONSE_CHANNEL = "ai-model-response"
AI_MODEL_RESPONSE_CHANNEL_V2 = "ai-model-response-v2"


class RedisPubSubProducer:
    def __init__(self, url: str):
        self.client = redis.from_url(url, decode_responses=True)

    async def start(self) -> None:
        await self.client.ping()

    async def stop(self) -> None:
        await self.client.aclose()

    async def publish(self, channel: str, message: dict[str, Any]) -> None:
        await self.client.publish(channel, json.dumps(message))

    async def publish_ai_model_response(self, payload: dict[str, Any]) -> None:
        await self.publish(AI_MODEL_RESPONSE_CHANNEL, payload)

    async def publish_ai_model_response_v2(self, payload: dict[str, Any]) -> None:
        await self.publish(AI_MODEL_RESPONSE_CHANNEL_V2, payload)
