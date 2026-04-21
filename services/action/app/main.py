from __future__ import annotations

from typing import Any

from fastapi import FastAPI

from aether_core.config import get_settings
from aether_core.models import ActionRequest
from aether_core.observability import configure_logging, instrument_fastapi, mount_metrics

from .orchestrator import ActionOrchestrator

settings = get_settings("aether-action")
logger = configure_logging(settings.service_name, settings.log_level)
orchestrator = ActionOrchestrator()

app = FastAPI(title="AETHER Action Service", version="1.0.0")
instrument_fastapi(app, settings)
mount_metrics(app)


@app.get("/healthz")
async def healthcheck() -> dict[str, str]:
    return {"status": "ok", "service": settings.service_name}


@app.post("/api/v1/actions/dispatch")
async def dispatch(request: ActionRequest) -> dict[str, Any]:
    result = await orchestrator.dispatch(request)
    logger.info("Dispatched action", extra={"target": request.target, "status": result["status"]})
    return result


@app.get("/api/v1/actions/dead-letter")
async def dead_letter_queue() -> list[dict[str, Any]]:
    return orchestrator.dead_letter_queue
