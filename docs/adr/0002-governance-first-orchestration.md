# ADR 0002: Governance Precedes External Action

## Status

Accepted

## Context

AETHER performs proactive reasoning and may trigger actions before a human explicitly requests them. That creates an obvious need for hard safety stops, auditability, and escalation paths before irreversible operations happen.

## Decision

All external actions pass through the Constitutional Governance Layer before dispatch. Action orchestration is not allowed to bypass governance, even for retries, rollback, or internal automation.

## Consequences

- Governance can block or escalate dangerous actions consistently.
- Audit records remain complete because evaluation is on the hot path.
- Action latency increases slightly, but bounded governance checks are preferable to unreviewed autonomy.
- Future integrations must provide enough metadata for rule evaluation and traceability.

