import asyncio

from cv_ranker.config import (
    load_db_settings,
    load_embedding_settings,
    load_llm_settings,
    load_qdrant_settings,
    load_redis_settings,
)
from cv_ranker.db import CVStore, DBSettings
from cv_ranker.embedding_client import EmbeddingClient, EmbeddingClientConfig
from cv_ranker.llm_client import LLMClientConfig
from cv_ranker.logging_config import configure_logging
from cv_ranker.qdrant_store import CVVectorStore, QdrantSettings
from redis_pubsub.producer.redis_pubsub_producer import RedisPubSubProducer
from redis_streams.consumer.chat_message_consumer import ChatMessageStreamConsumer
from redis_streams.consumer.recruiter_agent import RecruiterAgent
from redis_streams.producer.chat_message_producer import ChatMessageStreamProducer


async def main() -> None:
    configure_logging()
    redis_url = load_redis_settings().url
    store = CVStore(DBSettings(dsn=load_db_settings().dsn))
    llm_settings = load_llm_settings()

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

    producer = ChatMessageStreamProducer(url=redis_url)
    await producer.start()

    redis_pubsub_producer = RedisPubSubProducer(url=redis_url)
    await redis_pubsub_producer.start()

    consumer = ChatMessageStreamConsumer(
        url=redis_url,
        producer=producer,
        store=store,
        recruiter_agent=recruiter_agent,
        redis_pubsub_producer=redis_pubsub_producer,
    )
    try:
        await consumer.start()
    except KeyboardInterrupt:
        await consumer.stop()
    finally:
        await redis_pubsub_producer.stop()
        await producer.stop()


if __name__ == "__main__":
    asyncio.run(main())
