from fastapi.testclient import TestClient

from services.governance.app.main import app as governance_app
from services.reasoning.app.main import app as reasoning_app


def test_governance_api_contract() -> None:
    client = TestClient(governance_app)
    response = client.post(
        "/api/v1/governance/evaluate",
        json={"action_context": {"action": "shutdown", "criticality": 0.95}, "action_embedding": []},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["rule_id"] == "SAFETY_001"
    assert body["action_taken"] == "ESCALATE"


def test_reasoning_api_contract() -> None:
    client = TestClient(reasoning_app)
    response = client.post(
        "/api/v1/reason",
        json={
            "query": "Forecast thermal load",
            "current_state": {"temperature": 80},
            "history": [{"temperature": 70}, {"temperature": 75}],
            "mode": "predictive",
            "horizon": 2,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "predictive"
    assert len(body["predictions"]) == 2

