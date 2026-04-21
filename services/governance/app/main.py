from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field

from aether_core.config import get_settings
from aether_core.models import GovernanceDecision
from aether_core.observability import configure_logging, instrument_fastapi, mount_metrics

from .engine import ConstitutionalGovernanceLayer

settings = get_settings("aether-governance")
logger = configure_logging(settings.service_name, settings.log_level)
governance = ConstitutionalGovernanceLayer()

app = FastAPI(title="AETHER Governance Service", version="1.0.0")
instrument_fastapi(app, settings)
mount_metrics(app)


class GovernanceEvaluateRequest(BaseModel):
    action_context: dict[str, Any]
    action_embedding: list[float] = Field(default_factory=list)


@app.get("/healthz")
async def healthcheck() -> dict[str, str]:
    return {"status": "ok", "service": settings.service_name}


@app.post("/api/v1/governance/evaluate", response_model=GovernanceDecision)
async def evaluate(request: GovernanceEvaluateRequest) -> GovernanceDecision:
    decision = governance.evaluate_action(request.action_context, request.action_embedding)
    logger.info(
        "Evaluated action context",
        extra={"decision_id": decision.decision_id, "action_taken": decision.action_taken.value},
    )
    return decision


@app.get("/api/v1/governance/audit")
async def audit_report(start_time: datetime | None = None, end_time: datetime | None = None) -> list[dict[str, Any]]:
    return governance.audit_logger.window(start_time, end_time)


@app.get("/api/v1/governance/escalations")
async def escalations() -> list[dict[str, Any]]:
    return list(governance.escalation_queue)
