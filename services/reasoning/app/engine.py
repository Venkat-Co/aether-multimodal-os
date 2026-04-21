from __future__ import annotations

from collections import defaultdict
from typing import Any

from aether_core.models import CauseCandidate, Prediction, ReasoningMode, ReasoningRequest, ReasoningResult


class CausalInferenceEngine:
    def infer_causes(self, observed_effect: str, evidence: dict[str, Any]) -> list[CauseCandidate]:
        candidates: list[CauseCandidate] = []
        for key, value in evidence.items():
            support = 0.5
            if isinstance(value, (int, float)):
                support = min(abs(float(value)) / 100.0, 1.0)
            elif isinstance(value, str) and observed_effect.lower() in value.lower():
                support = 0.8
            score = min(1.0, 0.4 + support * 0.6)
            candidates.append(
                CauseCandidate(
                    cause_id=key,
                    description=f"{key} plausibly contributes to {observed_effect}",
                    score=score,
                    confidence_interval=[max(score - 0.1, 0.0), min(score + 0.1, 1.0)],
                )
            )
        return sorted(candidates, key=lambda item: item.score, reverse=True)[:5]


class PredictiveModel:
    def predict(self, state: dict[str, Any], history: list[dict[str, Any]], horizon: int) -> list[Prediction]:
        numeric_history: dict[str, list[float]] = defaultdict(list)
        for point in history:
            for key, value in point.items():
                if isinstance(value, (int, float)):
                    numeric_history[key].append(float(value))
        predictions: list[Prediction] = []
        for step in range(1, horizon + 1):
            predicted_state: dict[str, Any] = {}
            confidence = max(0.5, 0.95 - step * 0.1)
            for key, value in state.items():
                if isinstance(value, (int, float)):
                    series = numeric_history.get(key, [float(value)])
                    trend = 0.0 if len(series) < 2 else series[-1] - series[-2]
                    predicted_value = float(value) + (trend * 0.4 * step) + (series[-1] * 0.02 * step)
                    predicted_state[key] = round(predicted_value, 3)
                else:
                    predicted_state[key] = value
            predictions.append(
                Prediction(
                    horizon_step=step,
                    predicted_state=predicted_state,
                    lower_bound=max(0.0, confidence - 0.1),
                    upper_bound=min(1.0, confidence + 0.05),
                    confidence=confidence,
                )
            )
        return predictions


class ReasoningEngine:
    def __init__(self, trigger_threshold: float = 0.8) -> None:
        self.trigger_threshold = trigger_threshold
        self.causal_engine = CausalInferenceEngine()
        self.predictive_model = PredictiveModel()
        self.metric_profiles: dict[str, dict[str, float | str]] = {
            "temperature": {"direction": "high", "warn": 75.0, "critical": 95.0, "weight": 0.4},
            "temperature_c": {"direction": "high", "warn": 75.0, "critical": 95.0, "weight": 0.4},
            "vibration": {"direction": "high", "warn": 0.8, "critical": 2.0, "weight": 0.35},
            "vibration_g": {"direction": "high", "warn": 0.8, "critical": 2.0, "weight": 0.35},
            "pressure": {"direction": "high", "warn": 180.0, "critical": 260.0, "weight": 0.25},
            "pressure_kpa": {"direction": "high", "warn": 180.0, "critical": 260.0, "weight": 0.25},
            "fusion_confidence": {"direction": "low", "warn": 0.75, "critical": 0.55, "weight": 0.2},
            "sensor_confidence": {"direction": "low", "warn": 0.75, "critical": 0.55, "weight": 0.2},
        }

    def _normalize_confidence(self, value: float) -> float:
        return value / 100.0 if value > 1.0 else value

    def _score_metric(self, key: str, value: Any) -> dict[str, float | str] | None:
        if not isinstance(value, (int, float)):
            return None
        profile = self.metric_profiles.get(key)
        if profile is None:
            return None

        numeric_value = float(value)
        if "confidence" in key:
            numeric_value = self._normalize_confidence(numeric_value)

        warn = float(profile["warn"])
        critical = float(profile["critical"])
        weight = float(profile["weight"])
        direction = str(profile["direction"])

        if direction == "high":
            severity = 0.0 if numeric_value <= warn else (numeric_value - warn) / max(critical - warn, 1e-9)
        else:
            severity = 0.0 if numeric_value >= warn else (warn - numeric_value) / max(warn - critical, 1e-9)

        severity = max(0.0, min(severity, 1.0))
        return {
            "metric": key,
            "severity": round(severity, 3),
            "weight": round(weight, 3),
            "contribution": round(severity * weight, 3),
        }

    def check_proactive_triggers(self, current_state: dict[str, Any]) -> dict[str, Any]:
        scored_metrics: list[dict[str, float | str]] = []
        fallback_components: list[float] = []
        weighted_total = 0.0
        total_weight = 0.0
        critical_breach = False

        for key, value in current_state.items():
            scored = self._score_metric(key, value)
            if scored is not None:
                severity = float(scored["severity"])
                weight = float(scored["weight"])
                weighted_total += severity * weight
                total_weight += weight
                scored_metrics.append(scored)
                critical_breach = critical_breach or severity >= 1.0
                continue

            if isinstance(value, (int, float)) and any(token in key.lower() for token in ("anomaly", "risk", "criticality")):
                fallback_components.append(max(0.0, min(float(value), 1.0)))

        if total_weight > 0:
            anomaly_score = weighted_total / total_weight
        elif fallback_components:
            anomaly_score = sum(fallback_components) / len(fallback_components)
        else:
            anomaly_score = 0.0

        drivers = sorted(
            scored_metrics,
            key=lambda item: (float(item["contribution"]), float(item["severity"])),
            reverse=True,
        )[:3]
        return {
            "triggered": critical_breach or anomaly_score >= self.trigger_threshold,
            "anomaly_score": round(anomaly_score, 3),
            "drivers": drivers,
        }

    def _reactive(self, request: ReasoningRequest) -> ReasoningResult:
        summary = f"Reactive analysis for '{request.query}' across {len(request.current_state)} state variables."
        action_plan = [{"type": "notify", "target": "operator_console", "why": "Reactive query completed"}]
        return ReasoningResult(mode=ReasoningMode.reactive, summary=summary, action_plan=action_plan, confidence=0.7)

    def _causal(self, request: ReasoningRequest) -> ReasoningResult:
        causes = self.causal_engine.infer_causes(request.query, request.current_state)
        summary = f"Causal analysis identified {len(causes)} plausible upstream drivers for '{request.query}'."
        action_plan = [{"type": "investigate", "target": cause.cause_id, "score": cause.score} for cause in causes[:3]]
        return ReasoningResult(
            mode=ReasoningMode.causal,
            summary=summary,
            causes=causes,
            action_plan=action_plan,
            confidence=0.78 if causes else 0.55,
        )

    def _predictive(self, request: ReasoningRequest) -> ReasoningResult:
        predictions = self.predictive_model.predict(request.current_state, request.history, request.horizon)
        summary = f"Predictive forecast generated {len(predictions)} future state snapshots."
        action_plan = [{"type": "monitor", "target": "predictive_timeline", "horizon": request.horizon}]
        return ReasoningResult(
            mode=ReasoningMode.predictive,
            summary=summary,
            predictions=predictions,
            action_plan=action_plan,
            confidence=sum(item.confidence for item in predictions) / max(len(predictions), 1),
        )

    def _proactive(self, request: ReasoningRequest) -> ReasoningResult:
        trigger = self.check_proactive_triggers(request.current_state)
        summary = "No proactive trigger fired."
        if trigger["triggered"]:
            driver_names = ", ".join(str(item["metric"]) for item in trigger["drivers"])
            summary = "Proactive trigger fired based on anomaly threshold breach."
            if driver_names:
                summary = f"{summary} Top drivers: {driver_names}."
        action_plan = []
        if trigger["triggered"]:
            action_plan = [
                {"type": "notify", "target": "incident_channel", "severity": "high"},
                {"type": "reason", "mode": "causal", "why": "auto-investigate anomaly"},
            ]
        return ReasoningResult(
            mode=ReasoningMode.proactive,
            summary=summary,
            action_plan=action_plan,
            confidence=max(0.6, trigger["anomaly_score"]),
        )

    def reason(self, request: ReasoningRequest) -> ReasoningResult:
        if request.mode == ReasoningMode.reactive:
            return self._reactive(request)
        if request.mode == ReasoningMode.causal:
            return self._causal(request)
        if request.mode == ReasoningMode.predictive:
            return self._predictive(request)
        return self._proactive(request)
