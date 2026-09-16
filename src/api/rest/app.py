import logging
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import psycopg
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from consumer.chat_message_consumer import ChatMessageConsumer, KafkaConsumerConfig
from cv_ranker.config import load_db_settings, load_kafka_settings
from cv_ranker.db import Conversation, CVStore, DBSettings, Message
from cv_ranker.kafka_producer import ChatMessageProducer, KafkaProducerConfig
from cv_ranker.logging_config import configure_logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    logger.info("Starting up: applying database migrations")
    db_settings = load_db_settings()
    CVStore(DBSettings(dsn=db_settings.dsn)).init_schema()

    kafka_bootstrap_servers = load_kafka_settings().bootstrap_servers
    app.state.chat_message_producer = ChatMessageProducer(
        KafkaProducerConfig(bootstrap_servers=kafka_bootstrap_servers)
    )

    chat_message_consumer = ChatMessageConsumer(KafkaConsumerConfig(bootstrap_servers=kafka_bootstrap_servers))
    consumer_thread = threading.Thread(target=chat_message_consumer.run, name="chat-message-consumer", daemon=True)
    consumer_thread.start()

    logger.info("Startup complete")
    yield

    app.state.chat_message_producer.close()
    chat_message_consumer.stop()
    consumer_thread.join(timeout=5)


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_store() -> CVStore:
    return CVStore(DBSettings(dsn=load_db_settings().dsn))


def get_producer(request: Request) -> ChatMessageProducer:
    return request.app.state.chat_message_producer


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
def create_message(
    conversation_id: int,
    body: MessageCreate,
    store: CVStore = Depends(get_store),
    producer: ChatMessageProducer = Depends(get_producer),
) -> Message:
    try:
        message_id = store.create_message(conversation_id, body.role, body.content)
    except psycopg.errors.ForeignKeyViolation as exc:
        raise HTTPException(status_code=404, detail="Conversation not found") from exc
    message = store.get_message(message_id)
    producer.publish_message(message)
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


# @app.websocket("/ws")
# async def hello_world_ws(websocket: WebSocket) -> None:
#     await websocket.accept()
#     try:
#         while True:
#             data = await websocket.receive_text()
#             await websocket.send_text(f"Hello, World! You said: {data}")
#     except WebSocketDisconnect:
#         pass
