from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from aether_core.config import get_settings
from aether_core.event_bus import InMemoryEventBus, build_event_bus, connect_event_bus_with_retry
from aether_core.models import ModalityType, StreamPacket
from aether_core.observability import (
    ACTIVE_STREAMS_GAUGE,
    configure_logging,
    instrument_fastapi,
    mount_metrics,
)

from .adapters import StreamRegistry

settings = get_settings("aether-ingestion")
logger = configure_logging(settings.service_name, settings.log_level)
registry = StreamRegistry()
event_bus = build_event_bus(settings)


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
        logger.warning("Falling back to in-memory ingestion event bus", extra={"detail": str(exc)})
        event_bus = InMemoryEventBus()
        await event_bus.connect()
    yield
    await event_bus.close()


app = FastAPI(title="AETHER Ingestion Service", version="1.0.0", lifespan=lifespan)
instrument_fastapi(app, settings)
mount_metrics(app)


class StreamRegistrationRequest(BaseModel):
    source_id: str
    modality: ModalityType
    config: dict[str, Any] = Field(default_factory=dict)


@app.get("/healthz")
async def healthcheck() -> dict[str, str]:
    return {"status": "ok", "service": settings.service_name}


@app.post("/api/v1/streams")
async def register_stream(request: StreamRegistrationRequest) -> dict[str, Any]:
    adapter = await registry.register(request.source_id, request.modality, request.config)
    ACTIVE_STREAMS_GAUGE.labels(modality=request.modality.value).inc()
    logger.info("Registered stream", extra={"source_id": request.source_id, "modality": request.modality.value})
    payload = {
        "source_id": request.source_id,
        "modality": adapter.modality,
        "status": "registered",
        "config": request.config,
    }
    try:
        await event_bus.publish("stream_registry", {"source_id": request.source_id, "modality": request.modality.value}, source=settings.service_name)
    except Exception as exc:
        logger.warning("Failed to publish stream registration event", extra={"detail": str(exc)})
    return payload


@app.get("/api/v1/streams")
async def list_streams() -> list[dict[str, Any]]:
    return registry.list_streams()


@app.post("/api/v1/ingest")
async def ingest_raw_packet(packet: StreamPacket) -> StreamPacket:
    return packet


@app.post("/api/v1/streams/{source_id}/emit")
async def emit_packet(source_id: str) -> StreamPacket:
    if source_id not in {stream["source_id"] for stream in registry.list_streams()}:
        raise HTTPException(status_code=404, detail=f"Unknown stream: {source_id}")
    packet = await registry.emit(source_id)
    try:
        await event_bus.publish("streams", packet.model_dump(mode="json"), source=settings.service_name)
    except Exception as exc:
        logger.warning("Failed to publish stream packet", extra={"detail": str(exc), "source_id": source_id})
    return packet


@app.get("/api/v1/streams/{source_id}/health")
async def stream_health(source_id: str) -> dict[str, Any]:
    if source_id not in {stream["source_id"] for stream in registry.list_streams()}:
        raise HTTPException(status_code=404, detail=f"Unknown stream: {source_id}")
    return (await registry.health(source_id)).model_dump()


@app.get("/api/v1/streams/{source_id}/packets")
async def recent_packets(source_id: str) -> list[dict[str, Any]]:
    return [packet.model_dump() for packet in registry.recent_packets(source_id)]
