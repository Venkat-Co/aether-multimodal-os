from __future__ import annotations

import hashlib
import json
from collections import deque
from datetime import UTC, datetime
from typing import Any, Awaitable, Callable

from aether_core.models import GovernanceAction, GovernanceDecision, GovernanceRule, RiskLevel


DEFAULT_RULES = [
    GovernanceRule(
        rule_id="SAFETY_001",
        name="Critical System Shutdown",
        condition={"action": {"equals": "shutdown"}, "criticality": {"gt": 0.8}},
        action=GovernanceAction.escalate,
        risk_level=RiskLevel.critical,
        description="Block autonomous shutdown of critical systems without human review.",
    ),
    GovernanceRule(
        rule_id="SAFETY_002",
        name="Financial Transaction Limit",
        condition={"amount": {"gt": 1_000_000}},
        action=GovernanceAction.block,
        risk_level=RiskLevel.high,
        description="Block unusually large financial transfers.",
    ),
    GovernanceRule(
        rule_id="SAFETY_003",
        name="Human Override Required",
        condition={"reversibility": {"equals": "none"}},
        action=GovernanceAction.escalate,
        risk_level=RiskLevel.high,
        description="Escalate irreversible actions.",
    ),
    GovernanceRule(
        rule_id="SAFETY_004",
        name="Anomaly Response",
        condition={"sensor_confidence": {"lt": 0.6}},
        action=GovernanceAction.monitor,
        risk_level=RiskLevel.medium,
        description="Monitor low-confidence sensor inputs before acting.",
    ),
    GovernanceRule(
        rule_id="SAFETY_005",
        name="Data Privacy Protection",
        condition={"data_type": {"in": ["PII", "PHI", "classified"]}},
        action=GovernanceAction.block,
        risk_level=RiskLevel.critical,
        description="Block handling of protected or classified data.",
    ),
    GovernanceRule(
        rule_id="SAFETY_006",
        name="Autonomous Weaponization",
        condition={"intent": {"equals": "harm"}, "capability": {"equals": "weapon"}},
        action=GovernanceAction.block,
        risk_level=RiskLevel.critical,
        description="Block harmful weaponization requests.",
    ),
]


class AuditLogger:
    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []
        self._merkle_chain: list[str] = []

    def _hash_entry(self, entry: dict[str, Any], previous_hash: str) -> str:
        payload = json.dumps({"previous_hash": previous_hash, "entry": entry}, sort_keys=True, default=str)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def append(self, entry: dict[str, Any]) -> str:
        previous_hash = self._merkle_chain[-1] if self._merkle_chain else "ROOT"
        current_hash = self._hash_entry(entry, previous_hash)
        self.entries.append({**entry, "hash": current_hash, "previous_hash": previous_hash})
        self._merkle_chain.append(current_hash)
        return current_hash

    def window(self, start: datetime | None = None, end: datetime | None = None) -> list[dict[str, Any]]:
        def inside(entry: dict[str, Any]) -> bool:
            entry_time = datetime.fromisoformat(entry["timestamp"])
            if start and entry_time < start:
                return False
            if end and entry_time > end:
                return False
            return True

        return [entry for entry in self.entries if inside(entry)]


class ConstitutionalGovernanceLayer:
    def __init__(self, rules: list[GovernanceRule] | None = None) -> None:
        self.rules = rules or DEFAULT_RULES
        self.audit_logger = AuditLogger()
        self.escalation_queue: deque[dict[str, Any]] = deque(maxlen=500)

    def _match_predicate(self, actual: Any, predicate: dict[str, Any]) -> bool:
        if "equals" in predicate:
            return actual == predicate["equals"]
        if "gt" in predicate:
            return float(actual) > float(predicate["gt"])
        if "lt" in predicate:
            return float(actual) < float(predicate["lt"])
        if "in" in predicate:
            return actual in predicate["in"]
        return False

    def _rule_matches(self, rule: GovernanceRule, context: dict[str, Any]) -> bool:
        for key, predicate in rule.condition.items():
            if key not in context or not self._match_predicate(context[key], predicate):
                return False
        return True

    def evaluate_action(self, action_context: dict[str, Any], action_embedding: list[float] | None = None) -> GovernanceDecision:
        context_hash = hashlib.sha256(
            json.dumps({"context": action_context, "embedding": action_embedding or []}, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        matching_rule = next((rule for rule in self.rules if self._rule_matches(rule, action_context)), None)
        if matching_rule is None:
            decision = GovernanceDecision(
                rule_id="DEFAULT_ALLOW",
                action_taken=GovernanceAction.allow,
                risk_level=RiskLevel.low,
                context_hash=context_hash,
                reasoning="No constitutional rule matched; action allowed under default posture.",
                confidence=0.8,
                approved=True,
                audit_trail=[{"step": "rule_evaluation", "timestamp": datetime.now(tz=UTC).isoformat(), "details": {"matched": False}}],
            )
        else:
            approved = matching_rule.action == GovernanceAction.allow
            decision = GovernanceDecision(
                rule_id=matching_rule.rule_id,
                action_taken=matching_rule.action,
                risk_level=matching_rule.risk_level,
                context_hash=context_hash,
                reasoning=f"Rule {matching_rule.rule_id} triggered: {matching_rule.description}",
                confidence=0.98 if matching_rule.risk_level == RiskLevel.critical else 0.9,
                approved=approved,
                audit_trail=[
                    {
                        "step": "rule_evaluation",
                        "timestamp": datetime.now(tz=UTC).isoformat(),
                        "details": {"matched": True, "rule_id": matching_rule.rule_id},
                    }
                ],
            )
            if matching_rule.action == GovernanceAction.escalate:
                self.escalation_queue.append(
                    {"decision_id": decision.decision_id, "timestamp": decision.timestamp.isoformat(), "context": action_context}
                )
        self.audit_logger.append(decision.model_dump(mode="json"))
        return decision

    async def execute_with_governance(
        self,
        action_context: dict[str, Any],
        executor: Callable[[dict[str, Any]], Awaitable[dict[str, Any]]],
        action_embedding: list[float] | None = None,
    ) -> dict[str, Any]:
        decision = self.evaluate_action(action_context, action_embedding)
        if decision.action_taken == GovernanceAction.block:
            return {"status": "blocked", "decision": decision.model_dump()}
        if decision.action_taken == GovernanceAction.escalate:
            return {"status": "escalated", "decision": decision.model_dump()}
        execution = await executor(action_context)
        return {"status": "executed", "decision": decision.model_dump(), "result": execution}

