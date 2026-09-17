from consumer.chat_message_consumer import ChatMessageConsumer, KafkaConsumerConfig
from cv_ranker.config import load_db_settings, load_kafka_settings, load_llm_settings
from cv_ranker.db import CVStore, DBSettings
from cv_ranker.kafka_producer import ChatMessageProducer, KafkaProducerConfig
from cv_ranker.llm_client import LLMClient, LLMClientConfig
from cv_ranker.logging_config import configure_logging


def main() -> None:
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
    producer = ChatMessageProducer(KafkaProducerConfig(bootstrap_servers=kafka_settings.bootstrap_servers))
    consumer = ChatMessageConsumer(
        KafkaConsumerConfig(bootstrap_servers=kafka_settings.bootstrap_servers), store, llm_client, producer
    )
    try:
        consumer.run()
    except KeyboardInterrupt:
        consumer.stop()
    finally:
        producer.close()


if __name__ == "__main__":
    main()
