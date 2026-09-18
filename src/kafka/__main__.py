import asyncio

from cv_ranker.config import load_db_settings, load_kafka_settings, load_llm_settings, load_redis_settings
from cv_ranker.db import CVStore, DBSettings
from cv_ranker.llm_client import LLMClient, LLMClientConfig
from cv_ranker.logging_config import configure_logging
from kafka.consumer.chat_message_consumer import ChatMessageConsumer
from kafka.producer.chat_message_producer import ChatMessageProducer
from redis_pubsub.producer.redis_pubsub_producer import RedisPubSubProducer


async def main() -> None:
    configure_logging()
    kafka_settings = load_kafka_settings()
    store = CVStore(DBSettings(dsn=load_db_settings().dsn))
    llm_settings = load_llm_settings()
    llm_client = LLMClient(
        LLMClientConfig(
            base_url=llm_settings.base_url,
            api_key=llm_settings.api_key,
            model=llm_settings.model,
            timeout_seconds=llm_settings.timeout_seconds,
        )
    )

    producer = ChatMessageProducer(bootstrap_servers=kafka_settings.bootstrap_servers)
    await producer.start()

    redis_producer = RedisPubSubProducer(url=load_redis_settings().url)
    await redis_producer.start()

    consumer = ChatMessageConsumer(
        bootstrap_servers=kafka_settings.bootstrap_servers,
        producer=producer,
        store=store,
        llm_client=llm_client,
        redis_producer=redis_producer,
    )
    try:
        await consumer.start()
    except KeyboardInterrupt:
        await consumer.stop()
    finally:
        await redis_producer.stop()
        await producer.stop()


if __name__ == "__main__":
    asyncio.run(main())
