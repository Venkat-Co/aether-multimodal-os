from __future__ import annotations

from fastapi import FastAPI

from aether_core.config import get_settings
from aether_core.models import ReasoningRequest, ReasoningResult
from aether_core.observability import configure_logging, instrument_fastapi, mount_metrics

from .engine import ReasoningEngine

settings = get_settings("aether-reasoning")
logger = configure_logging(settings.service_name, settings.log_level)
engine = ReasoningEngine(trigger_threshold=settings.reasoning_trigger_threshold)

app = FastAPI(title="AETHER Reasoning Service", version="1.0.0")
instrument_fastapi(app, settings)
mount_metrics(app)


@app.get("/healthz")
async def healthcheck() -> dict[str, str]:
    return {"status": "ok", "service": settings.service_name}


@app.post("/api/v1/reason", response_model=ReasoningResult)
async def reason(request: ReasoningRequest) -> ReasoningResult:
    result = engine.reason(request)
    logger.info("Completed reasoning request", extra={"mode": request.mode.value, "reasoning_id": result.reasoning_id})
    return result


@app.post("/api/v1/reason/proactive-check")
async def proactive_check(current_state: dict[str, float]) -> dict[str, object]:
    return engine.check_proactive_triggers(current_state)
