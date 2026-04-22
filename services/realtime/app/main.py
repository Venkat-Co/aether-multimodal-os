from __future__ import annotations

import asyncio
from collections import defaultdict
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from aether_core.config import get_settings
from aether_core.event_bus import (
    EventBus,
    InMemoryEventBus,
    build_event_bus,
    connect_event_bus_with_retry,
)
from aether_core.observability import configure_logging, instrument_fastapi, mount_metrics

settings = get_settings("aether-realtime")
logger = configure_logging(settings.service_name, settings.log_level)


class BroadcastHub:
    def __init__(self) -> None:
        self.subscribers: dict[str, set[WebSocket]] = defaultdict(set)
        self.state: dict[str, Any] = {
            "generated_at": datetime.now(tz=UTC).isoformat(),
            "status": "booting",
            "streams": [],
            "fusion": [],
            "alerts": [],
            "reasoning": [],
            "memory_updates": [],
            "agents": [],
            "agent_runs": [],
            "tools": [],
            "tasks": [],
            "task_runs": [],
            "workflows": [],
            "workflow_runs": [],
        }
        self._lock = asyncio.Lock()

    async def connect(self, topic: str, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self.subscribers[topic].add(websocket)

    async def disconnect(self, topic: str, websocket: WebSocket) -> None:
        async with self._lock:
            self.subscribers[topic].discard(websocket)

    async def _send(self, topic: str, payload: dict[str, Any]) -> None:
        for websocket in list(self.subscribers[topic]):
            try:
                await websocket.send_json(payload)
            except RuntimeError:
                self.subscribers[topic].discard(websocket)

    async def publish(self, topic: str, message: dict[str, Any]) -> None:
        self.state["generated_at"] = datetime.now(tz=UTC).isoformat()
        if topic == "dashboard":
            self.state.update(message)
        else:
            key = f"{topic}_updates" if topic == "memory" else topic
            if key in self.state and isinstance(self.state[key], list):
                self.state[key].append(message)
                self.state[key] = self.state[key][-100:]
        if topic == "dashboard":
            await self._send("dashboard", self.state)
            return

        await self._send(topic, message)
        await self._send("dashboard", self.state)


hub = BroadcastHub()
event_bus = build_event_bus(settings)
bus_tasks: list[asyncio.Task[None]] = []


async def consume_topic(topic: str, active_bus: EventBus) -> None:
    queue = await active_bus.subscribe(topic, subscriber_id=f"{settings.service_name}-{topic}")
    while True:
        envelope = await queue.get()
        await hub.publish(topic, envelope.payload)


@asynccontextmanager
async def lifespan(_: FastAPI):
    global event_bus
    try:
        await connect_event_bus_with_retry(
            event_bus,
            attempts=settings.startup_retry_attempts,
            delay_seconds=settings.startup_retry_delay_seconds,
        )
    except Exception as exc:
        logger.warning("Falling back to in-memory realtime event bus", extra={"detail": str(exc)})
        event_bus = InMemoryEventBus()
        await event_bus.connect()

    for topic in ("streams", "fusion", "memory", "reasoning", "alerts", "dashboard"):
        bus_tasks.append(asyncio.create_task(consume_topic(topic, event_bus)))
    yield
    for task in bus_tasks:
        task.cancel()
    for task in bus_tasks:
        with suppress(asyncio.CancelledError):
            await task
    bus_tasks.clear()
    await event_bus.close()


app = FastAPI(title="AETHER Realtime Gateway", version="1.0.0", lifespan=lifespan)
instrument_fastapi(app, settings)
mount_metrics(app)


@app.get("/healthz")
async def healthcheck() -> dict[str, str]:
    return {"status": "ok", "service": settings.service_name}


@app.post("/api/v1/realtime/publish/{topic}")
async def publish(topic: str, payload: dict[str, Any]) -> dict[str, str]:
    try:
        await event_bus.publish(topic, payload, source=settings.service_name)
        if not event_bus.distributed:
            await hub.publish(topic, payload)
    except Exception:
        await hub.publish(topic, payload)
    logger.info("Published realtime payload", extra={"topic": topic})
    return {"status": "published", "topic": topic}


@app.get("/api/v1/realtime/state")
async def state() -> dict[str, Any]:
    return hub.state


async def stream_topic(websocket: WebSocket, topic: str, initial_payload: dict[str, Any] | None = None) -> None:
    await hub.connect(topic, websocket)
    try:
        if initial_payload is not None:
            await websocket.send_json(initial_payload)
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await hub.disconnect(topic, websocket)


@app.websocket("/ws/streams/{source_id}")
async def ws_streams(websocket: WebSocket, source_id: str) -> None:
    await stream_topic(websocket, "streams", {"source_id": source_id, "connected": True})


@app.websocket("/ws/fusion")
async def ws_fusion(websocket: WebSocket) -> None:
    await stream_topic(websocket, "fusion")


@app.websocket("/ws/memory/updates")
async def ws_memory(websocket: WebSocket) -> None:
    await stream_topic(websocket, "memory")


@app.websocket("/ws/governance/alerts")
async def ws_governance(websocket: WebSocket) -> None:
    await stream_topic(websocket, "alerts")


@app.websocket("/ws/reasoning/results")
async def ws_reasoning(websocket: WebSocket) -> None:
    await stream_topic(websocket, "reasoning")


@app.websocket("/ws/dashboard/state")
async def ws_dashboard(websocket: WebSocket) -> None:
    await stream_topic(websocket, "dashboard", hub.state)
