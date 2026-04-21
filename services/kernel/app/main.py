from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from aether_core.config import get_settings
from aether_core.event_bus import InMemoryEventBus, build_event_bus, connect_event_bus_with_retry
from aether_core.observability import configure_logging, instrument_fastapi, mount_metrics

from .clients import AetherServiceClients
from .models import KernelPipelineRequest, KernelPipelineResult
from .orchestrator import KernelOrchestrator

settings = get_settings("aether-kernel")
logger = configure_logging(settings.service_name, settings.log_level)

clients = AetherServiceClients(settings)
event_bus = build_event_bus(settings)
orchestrator = KernelOrchestrator(clients, event_bus, settings.service_name)


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
        logger.warning("Falling back to in-memory kernel event bus", extra={"detail": str(exc)})
        event_bus = InMemoryEventBus()
        await event_bus.connect()
        orchestrator.event_bus = event_bus
    yield
    await event_bus.close()
    await clients.close()


app = FastAPI(title="AETHER Kernel Service", version="1.0.0", lifespan=lifespan)
instrument_fastapi(app, settings)
mount_metrics(app)


@app.get("/healthz")
async def healthcheck() -> dict[str, str]:
    return {"status": "ok", "service": settings.service_name}


@app.post("/api/v1/kernel/pipeline/run", response_model=KernelPipelineResult)
async def run_pipeline(request: KernelPipelineRequest) -> KernelPipelineResult:
    result = await orchestrator.run_pipeline(request)
    logger.info(
        "Completed kernel pipeline",
        extra={
            "registered_streams": len(result.registered_streams),
            "packet_count": len(result.packets),
            "decision": result.governance_decision["action_taken"],
        },
    )
    return result


@app.post("/api/v1/kernel/pipeline/demo", response_model=KernelPipelineResult)
async def run_demo() -> KernelPipelineResult:
    return await orchestrator.run_pipeline(KernelPipelineRequest())
