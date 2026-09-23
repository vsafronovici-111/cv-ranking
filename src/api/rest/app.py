import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import psycopg
from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from api.rest import appV2
from api.rest.dependencies import get_store
from cv_ranker.config import (
    load_db_settings,
    load_embedding_settings,
    load_kafka_settings,
    load_llm_settings,
    load_qdrant_settings,
    load_redis_settings,
)
from cv_ranker.db import Conversation, CVStore, DBSettings, Message
from cv_ranker.embedding_client import EmbeddingClient, EmbeddingClientConfig
from cv_ranker.llm_client import LLMClient, LLMClientConfig
from cv_ranker.logging_config import configure_logging
from cv_ranker.qdrant_store import CVVectorStore, QdrantSettings
from cv_ranker.websocket_manager import WSConnectionManager
from kafka.consumer.chat_message_consumer import ChatMessageConsumer
from kafka.consumer.recruiter_assistant import RecruiterAssistant
from kafka.producer.chat_message_producer import ChatMessageProducer
from redis_pubsub.consumer.redis_pubsub_consumer import RedisPubSubConsumer
from redis_pubsub.producer.redis_pubsub_producer import AI_MODEL_RESPONSE_CHANNEL_V2, RedisPubSubProducer
from redis_streams.consumer.chat_message_consumer import ChatMessageStreamConsumer
from redis_streams.consumer.recruiter_agent import RecruiterAgent
from redis_streams.producer.chat_message_producer import ChatMessageStreamProducer

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    logger.info("Starting up: applying database migrations")
    db_settings = load_db_settings()
    store = CVStore(DBSettings(dsn=db_settings.dsn))
    store.init_schema()

    kafka_bootstrap_servers = load_kafka_settings().bootstrap_servers
    producer = ChatMessageProducer(bootstrap_servers=kafka_bootstrap_servers)
    await producer.start()

    ws_connection_manager = WSConnectionManager()
    app.state.ws_connection_manager = ws_connection_manager

    ws_connection_manager_v2 = WSConnectionManager()
    app.state.ws_connection_manager_v2 = ws_connection_manager_v2

    redis_url = load_redis_settings().url
    redis_producer = RedisPubSubProducer(url=redis_url)
    await redis_producer.start()

    redis_consumer = RedisPubSubConsumer(url=redis_url, ws_connection_manager=ws_connection_manager)
    redis_consumer_task = asyncio.create_task(redis_consumer.start())

    redis_consumer_v2 = RedisPubSubConsumer(
        url=redis_url, ws_connection_manager=ws_connection_manager_v2, channel=AI_MODEL_RESPONSE_CHANNEL_V2
    )
    redis_consumer_v2_task = asyncio.create_task(redis_consumer_v2.start())

    llm_settings = load_llm_settings()
    llm_client = LLMClient(
        LLMClientConfig(
            base_url=llm_settings.base_url,
            api_key=llm_settings.api_key,
            model=llm_settings.model,
            timeout_seconds=llm_settings.timeout_seconds,
        )
    )

    embedding_settings = load_embedding_settings()
    embedding_client = EmbeddingClient(
        EmbeddingClientConfig(
            base_url=embedding_settings.base_url,
            api_key=embedding_settings.api_key,
            model=embedding_settings.model,
            timeout_seconds=embedding_settings.timeout_seconds,
        )
    )
    qdrant_settings = load_qdrant_settings()
    vector_store = CVVectorStore(QdrantSettings(url=qdrant_settings.url, api_key=qdrant_settings.api_key))
    recruiter_assistant = RecruiterAssistant(
        llm_client=llm_client, embedding_client=embedding_client, vector_store=vector_store
    )

    consumer = ChatMessageConsumer(
        bootstrap_servers=kafka_bootstrap_servers,
        producer=producer,
        store=store,
        recruiter_assistant=recruiter_assistant,
        redis_producer=redis_producer,
    )
    consumer_task = asyncio.create_task(consumer.start())

    app.state.chat_message_producer = producer

    redis_stream_producer = ChatMessageStreamProducer(url=redis_url)
    await redis_stream_producer.start()

    recruiter_agent = RecruiterAgent(
        llm_config=LLMClientConfig(
            base_url=llm_settings.base_url,
            api_key=llm_settings.api_key,
            model=llm_settings.model,
            timeout_seconds=llm_settings.timeout_seconds,
        ),
        embedding_client=embedding_client,
        vector_store=vector_store,
    )

    stream_consumer = ChatMessageStreamConsumer(
        url=redis_url,
        producer=redis_stream_producer,
        store=store,
        recruiter_agent=recruiter_agent,
        redis_pubsub_producer=redis_producer,
    )
    stream_consumer_task = asyncio.create_task(stream_consumer.start())

    app.state.chat_message_stream_producer = redis_stream_producer

    logger.info("Startup complete")
    try:
        yield
    finally:
        await consumer.stop()
        await consumer_task
        await producer.stop()
        await stream_consumer.stop()
        await stream_consumer_task
        await redis_stream_producer.stop()
        await redis_consumer.stop()
        await redis_consumer_task
        await redis_consumer_v2.stop()
        await redis_consumer_v2_task
        await redis_producer.stop()


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(appV2.router)


def get_producer(request: Request) -> ChatMessageProducer:
    return request.app.state.chat_message_producer


def get_ws_connection_manager(request: Request) -> WSConnectionManager:
    return request.app.state.ws_connection_manager


@app.get("/")
def hello_world() -> dict[str, str]:
    return {"message": "Hello, World!"}


class ConversationCreate(BaseModel):
    user_id: str
    name: str | None = None


class ConversationUpdate(BaseModel):
    name: str


class MessageCreate(BaseModel):
    role: str
    content: str


class MessageUpdate(BaseModel):
    content: str


@app.post("/conversations", status_code=201)
def create_conversation(body: ConversationCreate, store: CVStore = Depends(get_store)) -> Conversation:
    conversation_id = store.create_conversation(body.user_id, body.name)
    return store.get_conversation(conversation_id)


@app.get("/conversations")
def list_conversations(user_id: str, store: CVStore = Depends(get_store)) -> list[Conversation]:
    return store.list_conversations_by_user(user_id)


@app.get("/conversations/{conversation_id}")
def get_conversation(conversation_id: int, store: CVStore = Depends(get_store)) -> Conversation:
    conversation = store.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


@app.patch("/conversations/{conversation_id}")
def update_conversation(
    conversation_id: int, body: ConversationUpdate, store: CVStore = Depends(get_store)
) -> Conversation:
    updated = store.update_conversation_name(conversation_id, body.name)
    if not updated:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return store.get_conversation(conversation_id)


@app.post("/conversations/{conversation_id}/messages", status_code=201)
async def create_message(
    conversation_id: int,
    body: MessageCreate,
    store: CVStore = Depends(get_store),
    producer: ChatMessageProducer = Depends(get_producer),
    ws_connection_manager: WSConnectionManager = Depends(get_ws_connection_manager),
) -> Message:
    try:
        message_id = await asyncio.to_thread(store.create_message, conversation_id, body.role, body.content)
    except psycopg.errors.ForeignKeyViolation as exc:
        raise HTTPException(status_code=404, detail="Conversation not found") from exc
    message = await asyncio.to_thread(store.get_message, message_id)
    payload = {
        "id": message.id,
        "conversation_id": message.conversation_id,
        "role": message.role,
        "content": message.content,
        "created_at": message.created_at.isoformat(),
    }
    await ws_connection_manager.broadcast(payload["conversation_id"], payload)
    await producer.publish_message(message)
    return message


@app.get("/conversations/{conversation_id}/messages")
def list_messages(conversation_id: int, store: CVStore = Depends(get_store)) -> list[Message]:
    return store.list_messages_by_conversation(conversation_id)


@app.get("/messages/{message_id}")
def get_message(message_id: int, store: CVStore = Depends(get_store)) -> Message:
    message = store.get_message(message_id)
    if message is None:
        raise HTTPException(status_code=404, detail="Message not found")
    return message


@app.patch("/messages/{message_id}")
def update_message(message_id: int, body: MessageUpdate, store: CVStore = Depends(get_store)) -> Message:
    updated = store.update_message_content(message_id, body.content)
    if not updated:
        raise HTTPException(status_code=404, detail="Message not found")
    return store.get_message(message_id)


@app.websocket("/ws/conversations/{conversation_id}")
async def conversation_messages_ws(websocket: WebSocket, conversation_id: int) -> None:
    manager: WSConnectionManager = websocket.app.state.ws_connection_manager
    await manager.connect(conversation_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(conversation_id, websocket)


# @app.websocket("/ws")
# async def hello_world_ws(websocket: WebSocket) -> None:
#     await websocket.accept()
#     try:
#         while True:
#             data = await websocket.receive_text()
#             await websocket.send_text(f"Hello, World! You said: {data}")
#     except WebSocketDisconnect:
#         pass
