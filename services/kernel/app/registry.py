from __future__ import annotations

from collections import deque
from typing import Iterable
from uuid import uuid4

from aether_core.models import MemoryType, ReasoningMode

from .models import (
    ActionTemplate,
    AgentCreateRequest,
    AgentDefinition,
    AgentRunRequest,
    AgentRunResult,
    AgentRunStatus,
    AgentRunSummary,
    KernelPipelineRequest,
    StreamSpec,
    ToolBinding,
)


class AgentRegistry:
    def __init__(self, seed_agents: Iterable[AgentDefinition] | None = None) -> None:
        self._agents: dict[str, AgentDefinition] = {}
        self._runs: deque[AgentRunResult] = deque(maxlen=50)
        for agent in seed_agents or []:
            self._agents[agent.agent_id] = agent

    def list_agents(self) -> list[AgentDefinition]:
        return sorted(self._agents.values(), key=lambda agent: agent.name.lower())

    def get_agent(self, agent_id: str) -> AgentDefinition | None:
        return self._agents.get(agent_id)

    def create_agent(self, request: AgentCreateRequest) -> AgentDefinition:
        agent = AgentDefinition(**request.model_dump())
        self._agents[agent.agent_id] = agent
        return agent

    def build_pipeline_request(self, agent: AgentDefinition, request: AgentRunRequest) -> KernelPipelineRequest:
        action_template = request.action_template_override
        if action_template is None and agent.tools:
            primary_tool = agent.tools[0]
            action_template = ActionTemplate(
                action_type=primary_tool.action_type,
                target=primary_tool.target,
                parameters=primary_tool.parameters,
                requires_approval=primary_tool.requires_approval,
                reversibility=primary_tool.reversibility,
                criticality=primary_tool.criticality,
            )

        return KernelPipelineRequest(
            query=request.query or agent.default_query,
            reasoning_mode=agent.reasoning_mode,
            streams=agent.streams,
            register_streams=request.register_streams,
            publish_realtime=request.publish_realtime,
            packets_per_stream=request.packets_per_stream,
            reasoning_state_overrides=request.reasoning_state_overrides,
            reasoning_history=request.reasoning_history,
            action_template=action_template or ActionTemplate(),
            memory_type=agent.memory_type,
            window_center=request.window_center,
        )

    def status_from_governance(self, governance_action: str) -> AgentRunStatus:
        action = governance_action.upper()
        if action == "BLOCK":
            return AgentRunStatus.blocked
        if action == "ESCALATE":
            return AgentRunStatus.escalated
        if action == "MONITOR":
            return AgentRunStatus.monitored
        return AgentRunStatus.completed

    def record_run(self, result: AgentRunResult) -> AgentRunResult:
        self._runs.appendleft(result)
        return result

    def list_runs(self) -> list[AgentRunSummary]:
        return [
            AgentRunSummary(
                run_id=run.run_id,
                agent_id=run.agent_id,
                agent_name=run.agent_name,
                status=run.status,
                governance_action=run.governance_action,
                started_at=run.started_at,
                completed_at=run.completed_at,
            )
            for run in self._runs
        ]


def build_default_agents() -> list[AgentDefinition]:
    default_streams = [
        StreamSpec(source_id="camera_001", modality="vision", config={"fps": 30}),
        StreamSpec(source_id="mic_001", modality="audio", config={"sample_rate_hz": 16000}),
        StreamSpec(source_id="sensor_001", modality="sensor", config={"site": "factory-alpha"}),
        StreamSpec(source_id="log_001", modality="text", config={"channel": "ops-log"}),
    ]

    return [
        AgentDefinition(
            agent_id="ops_supervisor",
            name="Operations Supervisor",
            description="Supervises live plant conditions and flags multimodal anomalies for human review.",
            goal="Maintain safe operating conditions and escalate emerging multimodal anomalies.",
            reasoning_mode=ReasoningMode.proactive,
            memory_type=MemoryType.working,
            default_query="Assess current multimodal operating state and identify early risk signals.",
            streams=default_streams,
            tools=[
                ToolBinding(
                    tool_id="notify_supervisor",
                    name="Supervisor Notification",
                    description="Notify the shift supervisor with an operational summary.",
                    action_type="notify",
                    target="shift_supervisor",
                    parameters={"channel": "ops-supervision"},
                    criticality=0.35,
                )
            ],
            tags=["operations", "anomaly-detection", "supervision"],
        ),
        AgentDefinition(
            agent_id="incident_triage",
            name="Incident Triage",
            description="Correlates live multimodal signals with text and sensor context to triage operational incidents.",
            goal="Classify incidents quickly and route them through governed response paths.",
            reasoning_mode=ReasoningMode.causal,
            memory_type=MemoryType.working,
            default_query="Explain the likely cause of the active multimodal incident and recommend the next safe response.",
            streams=default_streams,
            tools=[
                ToolBinding(
                    tool_id="page_incident_channel",
                    name="Incident Broadcast",
                    description="Notify the incident response channel with a structured triage output.",
                    action_type="notify",
                    target="incident_channel",
                    parameters={"channel": "incident-response"},
                    requires_approval=True,
                    criticality=0.55,
                )
            ],
            tags=["incident-response", "causal-analysis", "triage"],
        ),
    ]


def build_run_result(
    agent: AgentDefinition,
    status: AgentRunStatus,
    governance_action: str,
    started_at,
    completed_at,
    pipeline_result,
) -> AgentRunResult:
    return AgentRunResult(
        run_id=f"agr_{uuid4().hex[:8]}",
        agent_id=agent.agent_id,
        agent_name=agent.name,
        status=status,
        governance_action=governance_action,
        started_at=started_at,
        completed_at=completed_at,
        pipeline_result=pipeline_result,
    )
