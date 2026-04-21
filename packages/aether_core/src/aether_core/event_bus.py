from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from collections import defaultdict
from contextlib import suppress
from typing import Any
from uuid import uuid4

try:
    from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
except Exception:  # pragma: no cover - optional transport dependency
    AIOKafkaConsumer = None  # type: ignore[assignment]
    AIOKafkaProducer = None  # type: ignore[assignment]

try:
    from redis.asyncio import Redis
except Exception:  # pragma: no cover - optional transport dependency
    Redis = None  # type: ignore[assignment]

from .config import AetherSettings
from .models import EventEnvelope


class EventBus(ABC):
    distributed: bool = False

    @abstractmethod
    async def connect(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def close(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def publish(
        self,
        topic: str,
        message: dict[str, Any],
        *,
        source: str,
        headers: dict[str, str] | None = None,
    ) -> EventEnvelope:
        raise NotImplementedError

    @abstractmethod
    async def subscribe(
        self,
        topic: str,
        *,
        subscriber_id: str | None = None,
        from_beginning: bool = False,
    ) -> asyncio.Queue[EventEnvelope]:
        raise NotImplementedError


class InMemoryEventBus(EventBus):
    distributed = False

    def __init__(self) -> None:
        self._subscribers: dict[str, list[asyncio.Queue[EventEnvelope]]] = defaultdict(list)

    async def connect(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def publish(
        self,
        topic: str,
        message: dict[str, Any],
        *,
        source: str,
        headers: dict[str, str] | None = None,
    ) -> EventEnvelope:
        envelope = EventEnvelope(topic=topic, source=source, payload=message, headers=headers or {})
        for queue in self._subscribers[topic]:
            await queue.put(envelope)
        return envelope

    async def subscribe(
        self,
        topic: str,
        *,
        subscriber_id: str | None = None,
        from_beginning: bool = False,
    ) -> asyncio.Queue[EventEnvelope]:
        del subscriber_id, from_beginning
        queue: asyncio.Queue[EventEnvelope] = asyncio.Queue()
        self._subscribers[topic].append(queue)
        return queue


class RedisStreamsEventBus(EventBus):
    distributed = True

    def __init__(
        self,
        redis_url: str,
        topic_prefix: str,
        poll_interval_ms: int,
    ) -> None:
        self.redis_url = redis_url
        self.topic_prefix = topic_prefix
        self.poll_interval_ms = poll_interval_ms
        self.client: Redis | None = None
        self._tasks: list[asyncio.Task[None]] = []

    def _stream_name(self, topic: str) -> str:
        return f"{self.topic_prefix}:stream:{topic}"

    async def connect(self) -> None:
        if Redis is None:
            raise RuntimeError("redis is not installed")
        self.client = Redis.from_url(self.redis_url, decode_responses=True)
        await self.client.ping()

    async def close(self) -> None:
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            with suppress(asyncio.CancelledError):
                await task
        self._tasks.clear()
        if self.client is not None:
            await self.client.close()
            self.client = None

    async def publish(
        self,
        topic: str,
        message: dict[str, Any],
        *,
        source: str,
        headers: dict[str, str] | None = None,
    ) -> EventEnvelope:
        if self.client is None:
            raise RuntimeError("Redis event bus is not connected")
        envelope = EventEnvelope(topic=topic, source=source, payload=message, headers=headers or {})
        await self.client.xadd(self._stream_name(topic), {"envelope": envelope.model_dump_json()})
        return envelope

    async def subscribe(
        self,
        topic: str,
        *,
        subscriber_id: str | None = None,
        from_beginning: bool = False,
    ) -> asyncio.Queue[EventEnvelope]:
        del subscriber_id
        if self.client is None:
            raise RuntimeError("Redis event bus is not connected")
        queue: asyncio.Queue[EventEnvelope] = asyncio.Queue()
        last_id = "0-0" if from_beginning else "$"
        task = asyncio.create_task(self._pump_stream(topic, queue, last_id))
        self._tasks.append(task)
        return queue

    async def _pump_stream(
        self,
        topic: str,
        queue: asyncio.Queue[EventEnvelope],
        last_id: str,
    ) -> None:
        if self.client is None:
            return
        stream_name = self._stream_name(topic)
        while True:
            results = await self.client.xread({stream_name: last_id}, count=100, block=self.poll_interval_ms)
            if not results:
                continue
            for _, entries in results:
                for entry_id, fields in entries:
                    raw = fields.get("envelope")
                    if raw is None:
                        continue
                    envelope = EventEnvelope.model_validate_json(raw)
                    await queue.put(envelope)
                    last_id = entry_id


class KafkaRedisEventBus(RedisStreamsEventBus):
    distributed = True

    def __init__(
        self,
        bootstrap_servers: str,
        redis_url: str,
        topic_prefix: str,
        poll_interval_ms: int,
    ) -> None:
        super().__init__(redis_url=redis_url, topic_prefix=topic_prefix, poll_interval_ms=poll_interval_ms)
        self.bootstrap_servers = bootstrap_servers
        self.producer: AIOKafkaProducer | None = None
        self._consumers: list[AIOKafkaConsumer] = []

    def _kafka_topic(self, topic: str) -> str:
        return f"{self.topic_prefix}.{topic}"

    async def connect(self) -> None:
        if AIOKafkaProducer is None:
            raise RuntimeError("aiokafka is not installed")
        self.producer = AIOKafkaProducer(bootstrap_servers=self.bootstrap_servers)
        await self.producer.start()
        await super().connect()

    async def close(self) -> None:
        for consumer in self._consumers:
            with suppress(Exception):
                await consumer.stop()
        self._consumers.clear()
        if self.producer is not None:
            await self.producer.stop()
            self.producer = None
        await super().close()

    async def publish(
        self,
        topic: str,
        message: dict[str, Any],
        *,
        source: str,
        headers: dict[str, str] | None = None,
    ) -> EventEnvelope:
        envelope = EventEnvelope(topic=topic, source=source, payload=message, headers=headers or {})
        if self.producer is None:
            raise RuntimeError("Kafka producer is not connected")
        await self.producer.send_and_wait(self._kafka_topic(topic), envelope.model_dump_json().encode("utf-8"))
        if self.client is not None:
            await self.client.xadd(self._stream_name(topic), {"envelope": envelope.model_dump_json()})
        return envelope

    async def subscribe(
        self,
        topic: str,
        *,
        subscriber_id: str | None = None,
        from_beginning: bool = False,
    ) -> asyncio.Queue[EventEnvelope]:
        if self.client is not None:
            return await super().subscribe(topic, subscriber_id=subscriber_id, from_beginning=from_beginning)
        if AIOKafkaConsumer is None:
            raise RuntimeError("aiokafka is not installed")

        consumer = AIOKafkaConsumer(
            self._kafka_topic(topic),
            bootstrap_servers=self.bootstrap_servers,
            auto_offset_reset="earliest" if from_beginning else "latest",
            enable_auto_commit=True,
            group_id=f"{subscriber_id or 'subscriber'}-{uuid4().hex[:8]}",
        )
        await consumer.start()
        self._consumers.append(consumer)
        queue: asyncio.Queue[EventEnvelope] = asyncio.Queue()
        task = asyncio.create_task(self._pump_consumer(consumer, queue))
        self._tasks.append(task)
        return queue

    async def _pump_consumer(
        self,
        consumer: AIOKafkaConsumer,
        queue: asyncio.Queue[EventEnvelope],
    ) -> None:
        async for message in consumer:
            envelope = EventEnvelope.model_validate_json(message.value.decode("utf-8"))
            await queue.put(envelope)


def build_event_bus(settings: AetherSettings) -> EventBus:
    backend = settings.event_bus_backend.lower()
    if backend == "redis_streams":
        return RedisStreamsEventBus(
            redis_url=settings.redis_url,
            topic_prefix=settings.event_bus_topic_prefix,
            poll_interval_ms=settings.event_bus_poll_interval_ms,
        )
    if backend == "kafka_redis":
        return KafkaRedisEventBus(
            bootstrap_servers=settings.kafka_bootstrap_servers,
            redis_url=settings.redis_url,
            topic_prefix=settings.event_bus_topic_prefix,
            poll_interval_ms=settings.event_bus_poll_interval_ms,
        )
    return InMemoryEventBus()


async def connect_event_bus_with_retry(
    bus: EventBus,
    *,
    attempts: int,
    delay_seconds: float,
) -> None:
    last_error: Exception | None = None
    for attempt in range(1, max(attempts, 1) + 1):
        try:
            await bus.connect()
            return
        except Exception as exc:
            last_error = exc
            if attempt >= attempts:
                break
            await asyncio.sleep(delay_seconds)
    if last_error is not None:
        raise last_error
