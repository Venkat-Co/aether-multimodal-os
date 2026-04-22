from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from aether_core.models import MemoryType, ModalityType, ReasoningMode


class StreamSpec(BaseModel):
    source_id: str
    modality: ModalityType
    config: dict[str, Any] = Field(default_factory=dict)


class ActionTemplate(BaseModel):
    action_type: str = "notify"
    target: str = "incident_channel"
    parameters: dict[str, Any] = Field(default_factory=dict)
    requires_approval: bool = False
    reversibility: str = "partial"
    criticality: float = 0.0


class ToolBinding(BaseModel):
    tool_id: str
    name: str
    description: str
    action_type: str = "notify"
    target: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    requires_approval: bool = False
    reversibility: str = "partial"
    criticality: float = 0.0


class ToolDefinition(BaseModel):
    tool_id: str
    name: str
    description: str
    action_type: str = "notify"
    target: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    requires_approval: bool = False
    reversibility: str = "partial"
    criticality: float = 0.0
    category: str = "operations"
    tags: list[str] = Field(default_factory=list)
    active: bool = True
    created_by: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))


class ToolCreateRequest(BaseModel):
    tool_id: str
    name: str
    description: str
    action_type: str = "notify"
    target: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    requires_approval: bool = False
    reversibility: str = "partial"
    criticality: float = 0.0
    category: str = "operations"
    tags: list[str] = Field(default_factory=list)
    active: bool = True
    created_by: str | None = None


class AgentRunStatus(str, Enum):
    completed = "completed"
    blocked = "blocked"
    escalated = "escalated"
    monitored = "monitored"
    failed = "failed"


class AgentDefinition(BaseModel):
    agent_id: str
    name: str
    description: str
    goal: str
    reasoning_mode: ReasoningMode = ReasoningMode.proactive
    memory_type: MemoryType = MemoryType.working
    default_query: str = "Assess current multimodal operating state"
    streams: list[StreamSpec] = Field(default_factory=list)
    tools: list[ToolBinding] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    active: bool = True
    created_by: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))


class AgentCreateRequest(BaseModel):
    agent_id: str
    name: str
    description: str
    goal: str
    reasoning_mode: ReasoningMode = ReasoningMode.proactive
    memory_type: MemoryType = MemoryType.working
    default_query: str = "Assess current multimodal operating state"
    streams: list[StreamSpec] = Field(default_factory=list)
    tools: list[ToolBinding] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    active: bool = True
    created_by: str | None = None


class AgentRunRequest(BaseModel):
    query: str | None = None
    packets_per_stream: int = 1
    publish_realtime: bool = True
    register_streams: bool = True
    reasoning_state_overrides: dict[str, Any] = Field(default_factory=dict)
    reasoning_history: list[dict[str, Any]] = Field(default_factory=list)
    action_template_override: ActionTemplate | None = None
    window_center: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))


class AgentRunResult(BaseModel):
    run_id: str
    agent_id: str
    agent_name: str
    status: AgentRunStatus
    started_at: datetime
    completed_at: datetime
    governance_action: str
    pipeline_result: "KernelPipelineResult"


class AgentRunSummary(BaseModel):
    run_id: str
    agent_id: str
    agent_name: str
    status: AgentRunStatus
    governance_action: str
    started_at: datetime
    completed_at: datetime


class TaskRunStatus(str, Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    blocked = "blocked"
    escalated = "escalated"
    monitored = "monitored"
    failed = "failed"


class TaskTemplate(BaseModel):
    task_id: str
    name: str
    description: str
    agent_id: str
    query: str
    tool_id: str | None = None
    packets_per_stream: int = 1
    publish_realtime: bool = True
    register_streams: bool = True
    reasoning_state_overrides: dict[str, Any] = Field(default_factory=dict)
    reasoning_history: list[dict[str, Any]] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    active: bool = True
    created_by: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))


class TaskCreateRequest(BaseModel):
    task_id: str
    name: str
    description: str
    agent_id: str
    query: str
    tool_id: str | None = None
    packets_per_stream: int = 1
    publish_realtime: bool = True
    register_streams: bool = True
    reasoning_state_overrides: dict[str, Any] = Field(default_factory=dict)
    reasoning_history: list[dict[str, Any]] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    active: bool = True
    created_by: str | None = None


class TaskRunRequest(BaseModel):
    query: str | None = None
    tool_id: str | None = None
    packets_per_stream: int | None = None
    publish_realtime: bool | None = None
    register_streams: bool | None = None
    reasoning_state_overrides: dict[str, Any] = Field(default_factory=dict)
    reasoning_history: list[dict[str, Any]] = Field(default_factory=list)
    window_center: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))


class TaskExecutionRecord(BaseModel):
    execution_id: str
    task_id: str
    task_name: str
    agent_id: str
    agent_name: str
    tool_id: str | None = None
    status: TaskRunStatus
    governance_action: str | None = None
    started_at: datetime
    completed_at: datetime | None = None
    detail: str
    state_history: list[dict[str, Any]] = Field(default_factory=list)
    agent_run_id: str | None = None


class TaskExecutionSummary(BaseModel):
    execution_id: str
    task_id: str
    task_name: str
    agent_id: str
    agent_name: str
    tool_id: str | None = None
    status: TaskRunStatus
    governance_action: str | None = None
    started_at: datetime
    completed_at: datetime | None = None
    detail: str
    agent_run_id: str | None = None


class TaskRunResult(BaseModel):
    task_execution: TaskExecutionRecord
    agent_run: AgentRunResult | None = None


class WorkflowRunStatus(str, Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    blocked = "blocked"
    escalated = "escalated"
    monitored = "monitored"
    failed = "failed"


class WorkflowStep(BaseModel):
    step_id: str
    task_id: str
    depends_on: list[str] = Field(default_factory=list)
    description: str | None = None


class WorkflowTemplate(BaseModel):
    workflow_id: str
    name: str
    description: str
    task_ids: list[str] = Field(default_factory=list)
    steps: list[WorkflowStep] = Field(default_factory=list)
    stop_on_statuses: list[WorkflowRunStatus] = Field(
        default_factory=lambda: [WorkflowRunStatus.blocked, WorkflowRunStatus.escalated, WorkflowRunStatus.failed]
    )
    tags: list[str] = Field(default_factory=list)
    active: bool = True
    created_by: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))


class WorkflowCreateRequest(BaseModel):
    workflow_id: str
    name: str
    description: str
    task_ids: list[str] = Field(default_factory=list)
    steps: list[WorkflowStep] = Field(default_factory=list)
    stop_on_statuses: list[WorkflowRunStatus] = Field(
        default_factory=lambda: [WorkflowRunStatus.blocked, WorkflowRunStatus.escalated, WorkflowRunStatus.failed]
    )
    tags: list[str] = Field(default_factory=list)
    active: bool = True
    created_by: str | None = None


class WorkflowRunRequest(BaseModel):
    publish_realtime: bool | None = None
    register_streams: bool | None = None
    default_packets_per_stream: int | None = None
    task_query_overrides: dict[str, str] = Field(default_factory=dict)
    task_tool_overrides: dict[str, str] = Field(default_factory=dict)
    task_reasoning_overrides: dict[str, dict[str, Any]] = Field(default_factory=dict)
    window_center: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))


class WorkflowExecutionRecord(BaseModel):
    execution_id: str
    workflow_id: str
    workflow_name: str
    status: WorkflowRunStatus
    started_at: datetime
    completed_at: datetime | None = None
    detail: str
    step_count: int = 0
    task_execution_ids: list[str] = Field(default_factory=list)
    governance_actions: list[str] = Field(default_factory=list)
    completed_step_ids: list[str] = Field(default_factory=list)
    step_results: list[dict[str, Any]] = Field(default_factory=list)
    state_history: list[dict[str, Any]] = Field(default_factory=list)


class WorkflowExecutionSummary(BaseModel):
    execution_id: str
    workflow_id: str
    workflow_name: str
    status: WorkflowRunStatus
    started_at: datetime
    completed_at: datetime | None = None
    detail: str
    step_count: int = 0
    task_execution_ids: list[str] = Field(default_factory=list)
    governance_actions: list[str] = Field(default_factory=list)
    completed_step_ids: list[str] = Field(default_factory=list)


class WorkflowRunResult(BaseModel):
    workflow_execution: WorkflowExecutionRecord
    task_runs: list[TaskRunResult] = Field(default_factory=list)


class ReviewQueueStatus(str, Enum):
    pending = "pending"
    resolved = "resolved"


class ReviewQueueItem(BaseModel):
    review_id: str
    status: ReviewQueueStatus = ReviewQueueStatus.pending
    source_kind: str
    source_id: str
    source_name: str
    run_id: str
    title: str
    summary: str
    trigger_status: str
    governance_action: str | None = None
    risk_level: str = "medium"
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
    resolved_at: datetime | None = None
    resolution: str | None = None
    resolution_notes: str | None = None
    reviewed_by: str | None = None
    reviewed_by_role: str | None = None
    review_source: str | None = None


class ReviewResolveRequest(BaseModel):
    resolution: str = "approved"
    resolution_notes: str | None = None
    reviewed_by: str | None = None
    reviewed_by_role: str | None = None
    review_source: str | None = None
    rerun_source: bool = False
    publish_realtime: bool = True


class ReviewReplaySummary(BaseModel):
    source_kind: str
    source_id: str
    run_id: str
    status: str


class ReviewResolveResult(BaseModel):
    review: ReviewQueueItem
    replay: ReviewReplaySummary | None = None


class OperatorSessionRequest(BaseModel):
    operator_name: str
    operator_role: str = "mission_controller"
    review_source: str = "dashboard"


class OperatorSession(BaseModel):
    session_token: str
    operator_name: str
    operator_role: str
    review_source: str
    permissions: list[str] = Field(default_factory=list)
    trusted: bool = True
    issued_at: datetime
    expires_at: datetime


class KernelPipelineRequest(BaseModel):
    query: str = "Assess current multimodal operating state"
    reasoning_mode: ReasoningMode = ReasoningMode.proactive
    streams: list[StreamSpec] = Field(
        default_factory=lambda: [
            StreamSpec(source_id="camera_001", modality=ModalityType.vision, config={"fps": 30}),
            StreamSpec(source_id="mic_001", modality=ModalityType.audio, config={"sample_rate_hz": 16000}),
            StreamSpec(source_id="sensor_001", modality=ModalityType.sensor, config={"site": "factory-alpha"}),
            StreamSpec(source_id="log_001", modality=ModalityType.text, config={"channel": "ops-log"}),
        ]
    )
    register_streams: bool = True
    publish_realtime: bool = True
    packets_per_stream: int = 1
    reasoning_state_overrides: dict[str, Any] = Field(default_factory=dict)
    reasoning_history: list[dict[str, Any]] = Field(default_factory=list)
    action_template: ActionTemplate = Field(default_factory=ActionTemplate)
    memory_type: MemoryType = MemoryType.working
    window_center: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))


class KernelPipelineResult(BaseModel):
    registered_streams: list[dict[str, Any]]
    packets: list[dict[str, Any]]
    fused_event: dict[str, Any]
    memory_node: dict[str, Any]
    reasoning_result: dict[str, Any]
    governance_decision: dict[str, Any]
    action_result: dict[str, Any] | None = None


class ControlPlaneStateSnapshot(BaseModel):
    schema_version: int = 1
    agents: list[AgentDefinition] = Field(default_factory=list)
    tools: list[ToolDefinition] = Field(default_factory=list)
    tasks: list[TaskTemplate] = Field(default_factory=list)
    workflows: list[WorkflowTemplate] = Field(default_factory=list)
    agent_runs: list[AgentRunResult] = Field(default_factory=list)
    task_runs: list[TaskExecutionRecord] = Field(default_factory=list)
    workflow_runs: list[WorkflowExecutionRecord] = Field(default_factory=list)
    reviews: list[ReviewQueueItem] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))


AgentRunResult.model_rebuild()
TaskRunResult.model_rebuild()
WorkflowRunResult.model_rebuild()
