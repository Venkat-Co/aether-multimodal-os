from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from aether_core.config import get_settings
from aether_core.event_bus import (
    EventBus,
    InMemoryEventBus,
    build_event_bus,
    connect_event_bus_with_retry,
)
from aether_core.models import FusedEvent, StreamPacket
from aether_core.observability import configure_logging, instrument_fastapi, mount_metrics

from .engine import MultiModalFusionEngine

settings = get_settings("aether-fusion")
logger = configure_logging(settings.service_name, settings.log_level)
engine = MultiModalFusionEngine(
    window_seconds=settings.fusion_window_seconds,
    temporal_tolerance_ms=settings.temporal_alignment_tolerance_ms,
)
event_bus = build_event_bus(settings)
bus_tasks: list[asyncio.Task[None]] = []


async def consume_stream_packets(active_bus: EventBus) -> None:
    queue = await active_bus.subscribe("streams", subscriber_id=f"{settings.service_name}-streams")
    while True:
        envelope = await queue.get()
        packet = StreamPacket.model_validate(envelope.payload)
        engine.ingest(packet)


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
        logger.warning("Falling back to in-memory fusion event bus", extra={"detail": str(exc)})
        event_bus = InMemoryEventBus()
        await event_bus.connect()

    bus_tasks.append(asyncio.create_task(consume_stream_packets(event_bus)))
    yield
    for task in bus_tasks:
        task.cancel()
    for task in bus_tasks:
        with suppress(asyncio.CancelledError):
            await task
    bus_tasks.clear()
    await event_bus.close()


app = FastAPI(title="AETHER Fusion Service", version="1.0.0", lifespan=lifespan)
instrument_fastapi(app, settings)
mount_metrics(app)


class WindowRequest(BaseModel):
    window_center: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))


@app.get("/healthz")
async def healthcheck() -> dict[str, str]:
    return {"status": "ok", "service": settings.service_name}


@app.post("/api/v1/fusion/ingest")
async def ingest_packet(packet: StreamPacket) -> dict[str, str]:
    engine.ingest(packet)
    logger.info("Ingested packet into fusion buffer", extra={"packet_id": packet.packet_id})
    return {"status": "accepted", "packet_id": packet.packet_id}


@app.post("/api/v1/fusion/window", response_model=FusedEvent)
async def fuse_window(request: WindowRequest) -> FusedEvent:
    try:
        fused_event = engine.fuse_window(request.window_center)
        try:
            await event_bus.publish("fusion", fused_event.model_dump(mode="json"), source=settings.service_name)
        except Exception as exc:
            logger.warning("Failed to publish fused event", extra={"detail": str(exc), "event_id": fused_event.event_id})
        return fused_event
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/v1/fusion/buffer")
async def buffer_state() -> dict[str, int]:
    return {"buffered_packets": len(engine.packet_buffer)}
