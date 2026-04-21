from __future__ import annotations

import asyncio
from typing import Any

from aether_core.models import ActionRequest, ActionResult, ActionType

from services.governance.app.engine import ConstitutionalGovernanceLayer


class ActionOrchestrator:
    def __init__(self, governance: ConstitutionalGovernanceLayer | None = None) -> None:
        self.governance = governance or ConstitutionalGovernanceLayer()
        self.idempotency_cache: dict[str, ActionResult] = {}
        self.dead_letter_queue: list[dict[str, Any]] = []

    async def _execute(self, request: ActionRequest) -> ActionResult:
        await asyncio.sleep(0)
        detail = f"Executed {request.action_type.value} action against {request.target}"
        rollback_reference = None
        if request.action_type != ActionType.rollback:
            rollback_reference = f"rbk_{request.idempotency_key[:8]}"
        return ActionResult(
            status="success",
            target=request.target,
            action_type=request.action_type,
            idempotency_key=request.idempotency_key,
            detail=detail,
            rollback_reference=rollback_reference,
        )

    async def dispatch(self, request: ActionRequest) -> dict[str, Any]:
        if request.idempotency_key in self.idempotency_cache:
            return {"status": "deduplicated", "result": self.idempotency_cache[request.idempotency_key].model_dump()}

        governance_context = {
            "action": request.parameters.get("action", request.target),
            "amount": request.parameters.get("amount", 0),
            "reversibility": request.reversibility,
            "criticality": request.criticality,
            "data_type": request.parameters.get("data_type"),
            "intent": request.parameters.get("intent"),
            "capability": request.parameters.get("capability"),
            "sensor_confidence": request.parameters.get("sensor_confidence", 1.0),
        }

        decision = self.governance.evaluate_action(governance_context)
        if decision.action_taken.value in {"BLOCK", "ESCALATE"}:
            return {"status": decision.action_taken.value.lower(), "decision": decision.model_dump()}

        for attempt in range(1, 4):
            try:
                result = await self._execute(request)
                self.idempotency_cache[request.idempotency_key] = result
                return {
                    "status": "executed",
                    "attempt": attempt,
                    "decision": decision.model_dump(),
                    "result": result.model_dump(),
                }
            except Exception as exc:
                if attempt == 3:
                    self.dead_letter_queue.append(
                        {"request": request.model_dump(), "error": str(exc), "attempts": attempt}
                    )
                    return {"status": "failed", "decision": decision.model_dump(), "error": str(exc)}
                await asyncio.sleep(attempt * 0.2)
        raise RuntimeError("Unreachable retry loop")

