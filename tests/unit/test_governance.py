from services.governance.app.engine import ConstitutionalGovernanceLayer


def test_governance_blocks_protected_data_actions() -> None:
    governance = ConstitutionalGovernanceLayer()
    decision = governance.evaluate_action({"data_type": "PII"})

    assert decision.rule_id == "SAFETY_005"
    assert decision.action_taken.value == "BLOCK"


def test_governance_escalates_critical_shutdown() -> None:
    governance = ConstitutionalGovernanceLayer()
    decision = governance.evaluate_action({"action": "shutdown", "criticality": 0.95})

    assert decision.rule_id == "SAFETY_001"
    assert decision.action_taken.value == "ESCALATE"

