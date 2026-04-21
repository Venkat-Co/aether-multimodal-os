from aether_core.models import ReasoningMode, ReasoningRequest
from services.reasoning.app.engine import ReasoningEngine


def test_predictive_reasoning_returns_requested_horizon() -> None:
    engine = ReasoningEngine()
    request = ReasoningRequest(
        query="Forecast thermal load",
        current_state={"temperature": 80.0, "vibration": 1.1},
        history=[{"temperature": 70.0, "vibration": 0.9}, {"temperature": 75.0, "vibration": 1.0}],
        mode=ReasoningMode.predictive,
        horizon=4,
    )

    result = engine.reason(request)

    assert len(result.predictions) == 4
    assert result.mode == ReasoningMode.predictive


def test_proactive_trigger_detects_anomaly() -> None:
    engine = ReasoningEngine()
    request = ReasoningRequest(
        query="Watch for anomalies",
        current_state={"temperature_c": 99.0, "vibration_g": 99.0, "pressure_kpa": 999.0, "fusion_confidence": 95.0},
        mode=ReasoningMode.proactive,
    )

    result = engine.reason(request)

    assert result.mode == ReasoningMode.proactive
    assert result.action_plan
    assert "Top drivers" in result.summary


def test_proactive_trigger_stays_quiet_for_nominal_demo_state() -> None:
    engine = ReasoningEngine()

    trigger = engine.check_proactive_triggers(
        {
            "fusion_confidence": 0.809405,
            "modality_count": 4,
            "temperature_c": 88.5,
            "vibration_g": 1.25,
            "pressure_kpa": 210.0,
        }
    )

    assert trigger["triggered"] is False
    assert trigger["anomaly_score"] < engine.trigger_threshold
