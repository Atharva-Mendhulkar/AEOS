import json
import logging
import asyncio
from aiokafka import AIOKafkaProducer, AIOKafkaConsumer

logger = logging.getLogger(__name__)

class KafkaPubSub:
    def __init__(self, kafka_url: str):
        # We handle single brokers usually in the form "kafka:29092"
        # Aiokafka expects a list of brokers or a single string
        self.bootstrap_servers = kafka_url
        self.producer = None

    async def connect_producer(self, retries=5, delay=2.0):
        if not self.producer:
            for attempt in range(retries):
                try:
                    self.producer = AIOKafkaProducer(bootstrap_servers=self.bootstrap_servers)
                    await self.producer.start()
                    logger.info("AIOKafkaProducer started.")
                    return
                except Exception as e:
                    logger.warning(f"Failed to connect AIOKafkaProducer (attempt {attempt+1}/{retries}): {e}")
                    if attempt < retries - 1:
                        await asyncio.sleep(delay)
                    else:
                        raise e

    async def disconnect_producer(self):
        if self.producer:
            await self.producer.stop()
            self.producer = None

    async def publish(self, topic: str, message: dict):
        if not self.producer:
            await self.connect_producer()
        # Convert dictionary to JSON string, then to bytes
        value = json.dumps(message).encode('utf-8')
        await self.producer.send_and_wait(topic, value)
        logger.debug(f"Published message to Kafka topic: {topic}")

    async def subscribe(self, topic: str, group_id: str, callback, retries=10, delay=3.0):
        """
        Subscribes to a topic and yields messages.
        Note: The callback should be an async function taking a single dictionary argument.
        """
        consumer = None
        for attempt in range(retries):
            try:
                consumer = AIOKafkaConsumer(
                    topic,
                    bootstrap_servers=self.bootstrap_servers,
                    group_id=group_id,
                    auto_offset_reset='latest'
                )
                await consumer.start()
                logger.info(f"AIOKafkaConsumer started for topic {topic} (group: {group_id}).")
                break
            except Exception as e:
                logger.warning(f"Failed to start AIOKafkaConsumer (attempt {attempt+1}/{retries}): {e}")
                if attempt < retries - 1:
                    await asyncio.sleep(delay)
                else:
                    raise e
        
        try:
            async for msg in consumer:
                try:
                    payload = json.loads(msg.value.decode('utf-8'))
                    await callback(payload)
                except Exception as e:
                    logger.error(f"Error processing Kafka message: {e}")
        finally:
            await consumer.stop()
            logger.info(f"AIOKafkaConsumer stopped for topic {topic}.")
