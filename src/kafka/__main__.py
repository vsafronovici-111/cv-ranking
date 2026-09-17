import asyncio

from cv_ranker.config import load_db_settings, load_kafka_settings, load_llm_settings
from cv_ranker.db import CVStore, DBSettings
from cv_ranker.llm_client import LLMClient, LLMClientConfig
from cv_ranker.logging_config import configure_logging
from kafka.consumer.chat_message_consumer import ChatMessageConsumer
from kafka.producer.chat_message_producer import ChatMessageProducer


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

    consumer = ChatMessageConsumer(
        bootstrap_servers=kafka_settings.bootstrap_servers,
        producer=producer,
        store=store,
        llm_client=llm_client,
    )
    try:
        await consumer.start()
    except KeyboardInterrupt:
        await consumer.stop()
    finally:
        await producer.stop()


if __name__ == "__main__":
    asyncio.run(main())
