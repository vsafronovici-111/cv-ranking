from consumer.chat_message_consumer import ChatMessageConsumer, KafkaConsumerConfig
from cv_ranker.config import load_kafka_settings
from cv_ranker.logging_config import configure_logging


def main() -> None:
    configure_logging()
    kafka_settings = load_kafka_settings()
    consumer = ChatMessageConsumer(KafkaConsumerConfig(bootstrap_servers=kafka_settings.bootstrap_servers))
    try:
        consumer.run()
    except KeyboardInterrupt:
        consumer.stop()


if __name__ == "__main__":
    main()
