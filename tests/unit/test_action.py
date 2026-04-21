import pytest

from aether_core.models import ActionRequest, ActionType
from services.action.app.orchestrator import ActionOrchestrator


@pytest.mark.asyncio
async def test_action_orchestrator_deduplicates_by_idempotency_key() -> None:
    orchestrator = ActionOrchestrator()
    request = ActionRequest(
        action_type=ActionType.notify,
        target="slack://incident-room",
        idempotency_key="fixed-key",
    )

    first = await orchestrator.dispatch(request)
    second = await orchestrator.dispatch(request)

    assert first["status"] == "executed"
    assert second["status"] == "deduplicated"

