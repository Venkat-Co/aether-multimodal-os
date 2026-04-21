from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field

from aether_core.config import get_settings
from aether_core.event_bus import InMemoryEventBus, build_event_bus, connect_event_bus_with_retry
from aether_core.models import MemoryNode, MemoryType
from aether_core.observability import configure_logging, instrument_fastapi, mount_metrics

from .graph import MemoryGraph

settings = get_settings("aether-memory")
logger = configure_logging(settings.service_name, settings.log_level)
memory_graph = MemoryGraph(settings)
memory_event_bus = build_event_bus(settings)


@asynccontextmanager
async def lifespan(_: FastAPI):
    global memory_event_bus
    await memory_graph.initialize()
    try:
        await connect_event_bus_with_retry(
            memory_event_bus,
            attempts=settings.startup_retry_attempts,
            delay_seconds=settings.startup_retry_delay_seconds,
        )
    except Exception as exc:
        logger.warning("Falling back to in-memory event bus", extra={"detail": str(exc)})
        memory_event_bus = InMemoryEventBus()
        await memory_event_bus.connect()
    yield
    await memory_event_bus.close()
    await memory_graph.close()

app = FastAPI(title="AETHER Memory Service", version="1.0.0", lifespan=lifespan)
instrument_fastapi(app, settings)
mount_metrics(app)


class TimeRange(BaseModel):
    start: datetime
    end: datetime


class LocationQuery(BaseModel):
    x: float
    y: float
    z: float
    radius: float


class MemoryQueryRequest(BaseModel):
    query_embedding: list[float]
    time_range: TimeRange | None = None
    location: LocationQuery | None = None
    memory_types: list[MemoryType] = Field(default_factory=list)
    top_k: int = 10


@app.get("/healthz")
async def healthcheck() -> dict[str, str]:
    return {"status": "ok", "service": settings.service_name}


@app.post("/api/v1/memory/store", response_model=MemoryNode)
async def store_memory(node: MemoryNode) -> MemoryNode:
    stored = await memory_graph.store_memory(node)
    try:
        await memory_event_bus.publish("memory", stored.model_dump(mode="json"), source=settings.service_name)
    except Exception as exc:
        logger.warning("Failed to publish memory event", extra={"detail": str(exc), "node_id": stored.node_id})
    logger.info("Stored memory node", extra={"node_id": node.node_id, "memory_type": node.memory_type.value})
    return stored


@app.post("/api/v1/memory/query")
async def query_memory(request: MemoryQueryRequest) -> list[dict[str, Any]]:
    results = await memory_graph.query(
        query_embedding=request.query_embedding,
        time_range=request.time_range.model_dump() if request.time_range else None,
        location=request.location.model_dump() if request.location else None,
        memory_types=request.memory_types or None,
        top_k=request.top_k,
    )
    return [result.model_dump() for result in results]


@app.post("/api/v1/memory/link/{parent_id}/{child_id}")
async def link_causal(parent_id: str, child_id: str, strength: float = 0.5) -> dict[str, Any]:
    await memory_graph.link_causal(parent_id, child_id, strength)
    payload = {"status": "linked", "parent_id": parent_id, "child_id": child_id, "strength": strength}
    try:
        await memory_event_bus.publish("memory", payload, source=settings.service_name)
    except Exception as exc:
        logger.warning("Failed to publish causal link event", extra={"detail": str(exc)})
    return payload


@app.get("/api/v1/memory/causal/{node_id}")
async def causal_chain(node_id: str, depth: int = 5) -> list[dict[str, Any]]:
    return [node.model_dump() for node in await memory_graph.extract_causal_chain(node_id, depth)]


@app.post("/api/v1/memory/consolidate")
async def consolidate() -> dict[str, int]:
    result = await memory_graph.consolidate()
    try:
        await memory_event_bus.publish("memory", result, source=settings.service_name)
    except Exception as exc:
        logger.warning("Failed to publish consolidation event", extra={"detail": str(exc)})
    return result


@app.get("/api/v1/memory/updates")
async def updates() -> list[dict[str, Any]]:
    return memory_graph.update_log[-100:]


@app.get("/api/v1/memory/backends")
async def backends() -> dict[str, Any]:
    return memory_graph.backend_status()
