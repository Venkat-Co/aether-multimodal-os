from __future__ import annotations

from collections import deque
from datetime import UTC, datetime
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
    TaskCreateRequest,
    TaskExecutionRecord,
    TaskExecutionSummary,
    TaskRunRequest,
    TaskRunStatus,
    TaskTemplate,
    ToolBinding,
    ToolCreateRequest,
    ToolDefinition,
    WorkflowCreateRequest,
    WorkflowExecutionRecord,
    WorkflowExecutionSummary,
    WorkflowRunRequest,
    WorkflowRunStatus,
    WorkflowTemplate,
)


def utc_now() -> datetime:
    return datetime.now(tz=UTC)


def tool_definition_from_binding(binding: ToolBinding, category: str = "operations", tags: list[str] | None = None) -> ToolDefinition:
    return ToolDefinition(
        tool_id=binding.tool_id,
        name=binding.name,
        description=binding.description,
        action_type=binding.action_type,
        target=binding.target,
        parameters=binding.parameters,
        requires_approval=binding.requires_approval,
        reversibility=binding.reversibility,
        criticality=binding.criticality,
        category=category,
        tags=tags or [],
    )


def tool_binding_from_definition(tool: ToolDefinition) -> ToolBinding:
    return ToolBinding(
        tool_id=tool.tool_id,
        name=tool.name,
        description=tool.description,
        action_type=tool.action_type,
        target=tool.target,
        parameters=tool.parameters,
        requires_approval=tool.requires_approval,
        reversibility=tool.reversibility,
        criticality=tool.criticality,
    )


class AgentRegistry:
    def __init__(
        self,
        seed_agents: Iterable[AgentDefinition] | None = None,
        seed_tools: Iterable[ToolDefinition] | None = None,
        seed_tasks: Iterable[TaskTemplate] | None = None,
        seed_workflows: Iterable[WorkflowTemplate] | None = None,
    ) -> None:
        self._agents: dict[str, AgentDefinition] = {}
        self._tools: dict[str, ToolDefinition] = {}
        self._tasks: dict[str, TaskTemplate] = {}
        self._workflows: dict[str, WorkflowTemplate] = {}
        self._runs: deque[AgentRunResult] = deque(maxlen=50)
        self._task_runs: deque[TaskExecutionRecord] = deque(maxlen=100)
        self._workflow_runs: deque[WorkflowExecutionRecord] = deque(maxlen=50)

        for tool in seed_tools or []:
            self._tools[tool.tool_id] = tool

        for agent in seed_agents or []:
            self._agents[agent.agent_id] = agent
            for tool in agent.tools:
                self._tools.setdefault(tool.tool_id, tool_definition_from_binding(tool))

        for task in seed_tasks or []:
            self._tasks[task.task_id] = task

        for workflow in seed_workflows or []:
            self._workflows[workflow.workflow_id] = workflow

    def list_agents(self) -> list[AgentDefinition]:
        return sorted(self._agents.values(), key=lambda agent: agent.name.lower())

    def get_agent(self, agent_id: str) -> AgentDefinition | None:
        return self._agents.get(agent_id)

    def create_agent(self, request: AgentCreateRequest) -> AgentDefinition:
        agent = AgentDefinition(**request.model_dump())
        self._agents[agent.agent_id] = agent
        for tool in agent.tools:
            self._tools.setdefault(tool.tool_id, tool_definition_from_binding(tool))
        return agent

    def list_tools(self) -> list[ToolDefinition]:
        return sorted(self._tools.values(), key=lambda tool: tool.name.lower())

    def get_tool(self, tool_id: str) -> ToolDefinition | None:
        return self._tools.get(tool_id)

    def create_tool(self, request: ToolCreateRequest) -> ToolDefinition:
        tool = ToolDefinition(**request.model_dump())
        self._tools[tool.tool_id] = tool
        return tool

    def list_tasks(self) -> list[TaskTemplate]:
        return sorted(self._tasks.values(), key=lambda task: task.name.lower())

    def get_task(self, task_id: str) -> TaskTemplate | None:
        return self._tasks.get(task_id)

    def create_task(self, request: TaskCreateRequest) -> TaskTemplate:
        task = TaskTemplate(**request.model_dump())
        self._tasks[task.task_id] = task
        return task

    def list_workflows(self) -> list[WorkflowTemplate]:
        return sorted(self._workflows.values(), key=lambda workflow: workflow.name.lower())

    def get_workflow(self, workflow_id: str) -> WorkflowTemplate | None:
        return self._workflows.get(workflow_id)

    def create_workflow(self, request: WorkflowCreateRequest) -> WorkflowTemplate:
        workflow = WorkflowTemplate(**request.model_dump())
        self._workflows[workflow.workflow_id] = workflow
        return workflow

    def build_action_template_from_tool(self, tool: ToolDefinition | None) -> ActionTemplate | None:
        if tool is None:
            return None
        return ActionTemplate(
            action_type=tool.action_type,
            target=tool.target,
            parameters=tool.parameters,
            requires_approval=tool.requires_approval,
            reversibility=tool.reversibility,
            criticality=tool.criticality,
        )

    def build_pipeline_request(self, agent: AgentDefinition, request: AgentRunRequest) -> KernelPipelineRequest:
        action_template = request.action_template_override
        if action_template is None and agent.tools:
            action_template = self.build_action_template_from_tool(self.get_tool(agent.tools[0].tool_id))
            if action_template is None:
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

    def build_agent_run_request_from_task(
        self, task: TaskTemplate, request: TaskRunRequest, tool: ToolDefinition | None
    ) -> AgentRunRequest:
        return AgentRunRequest(
            query=request.query or task.query,
            packets_per_stream=request.packets_per_stream or task.packets_per_stream,
            publish_realtime=task.publish_realtime if request.publish_realtime is None else request.publish_realtime,
            register_streams=task.register_streams if request.register_streams is None else request.register_streams,
            reasoning_state_overrides={**task.reasoning_state_overrides, **request.reasoning_state_overrides},
            reasoning_history=[*task.reasoning_history, *request.reasoning_history],
            action_template_override=self.build_action_template_from_tool(tool),
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

    def task_status_from_governance(self, governance_action: str) -> TaskRunStatus:
        action = governance_action.upper()
        if action == "BLOCK":
            return TaskRunStatus.blocked
        if action == "ESCALATE":
            return TaskRunStatus.escalated
        if action == "MONITOR":
            return TaskRunStatus.monitored
        return TaskRunStatus.completed

    def workflow_status_from_task_status(self, task_status: TaskRunStatus) -> WorkflowRunStatus:
        if task_status == TaskRunStatus.blocked:
            return WorkflowRunStatus.blocked
        if task_status == TaskRunStatus.escalated:
            return WorkflowRunStatus.escalated
        if task_status == TaskRunStatus.monitored:
            return WorkflowRunStatus.monitored
        if task_status == TaskRunStatus.failed:
            return WorkflowRunStatus.failed
        return WorkflowRunStatus.completed

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

    def start_task_execution(
        self, task: TaskTemplate, agent: AgentDefinition, tool: ToolDefinition | None
    ) -> TaskExecutionRecord:
        execution = TaskExecutionRecord(
            execution_id=f"tskrun_{uuid4().hex[:8]}",
            task_id=task.task_id,
            task_name=task.name,
            agent_id=agent.agent_id,
            agent_name=agent.name,
            tool_id=tool.tool_id if tool else task.tool_id,
            status=TaskRunStatus.pending,
            started_at=utc_now(),
            detail="Task accepted into the orchestration queue.",
            state_history=[
                {
                    "status": TaskRunStatus.pending.value,
                    "timestamp": utc_now().isoformat(),
                    "detail": "Task accepted into the orchestration queue.",
                }
            ],
        )
        self._task_runs.appendleft(execution)
        return self.transition_task_execution(
            execution,
            status=TaskRunStatus.running,
            detail="Task is running through the governed agent runtime.",
        )

    def transition_task_execution(
        self,
        execution: TaskExecutionRecord,
        status: TaskRunStatus,
        detail: str,
        governance_action: str | None = None,
        completed: bool = False,
        agent_run_id: str | None = None,
    ) -> TaskExecutionRecord:
        execution.status = status
        execution.detail = detail
        execution.governance_action = governance_action or execution.governance_action
        execution.agent_run_id = agent_run_id or execution.agent_run_id
        if completed:
            execution.completed_at = utc_now()
        execution.state_history.append(
            {
                "status": status.value,
                "timestamp": utc_now().isoformat(),
                "detail": detail,
                "governance_action": execution.governance_action,
            }
        )
        return execution

    def complete_task_execution(
        self,
        execution: TaskExecutionRecord,
        governance_action: str,
        detail: str,
        agent_run_id: str | None = None,
    ) -> TaskExecutionRecord:
        return self.transition_task_execution(
            execution,
            status=self.task_status_from_governance(governance_action),
            detail=detail,
            governance_action=governance_action,
            completed=True,
            agent_run_id=agent_run_id,
        )

    def fail_task_execution(self, execution: TaskExecutionRecord, detail: str) -> TaskExecutionRecord:
        return self.transition_task_execution(
            execution,
            status=TaskRunStatus.failed,
            detail=detail,
            completed=True,
        )

    def list_task_runs(self) -> list[TaskExecutionSummary]:
        return [
            TaskExecutionSummary(
                execution_id=run.execution_id,
                task_id=run.task_id,
                task_name=run.task_name,
                agent_id=run.agent_id,
                agent_name=run.agent_name,
                tool_id=run.tool_id,
                status=run.status,
                governance_action=run.governance_action,
                started_at=run.started_at,
                completed_at=run.completed_at,
                detail=run.detail,
                agent_run_id=run.agent_run_id,
            )
            for run in self._task_runs
        ]

    def start_workflow_execution(self, workflow: WorkflowTemplate) -> WorkflowExecutionRecord:
        execution = WorkflowExecutionRecord(
            execution_id=f"wkfrun_{uuid4().hex[:8]}",
            workflow_id=workflow.workflow_id,
            workflow_name=workflow.name,
            status=WorkflowRunStatus.pending,
            started_at=utc_now(),
            detail="Workflow accepted into the orchestration queue.",
            state_history=[
                {
                    "status": WorkflowRunStatus.pending.value,
                    "timestamp": utc_now().isoformat(),
                    "detail": "Workflow accepted into the orchestration queue.",
                }
            ],
        )
        self._workflow_runs.appendleft(execution)
        return self.transition_workflow_execution(
            execution,
            status=WorkflowRunStatus.running,
            detail="Workflow is coordinating governed task execution.",
        )

    def transition_workflow_execution(
        self,
        execution: WorkflowExecutionRecord,
        status: WorkflowRunStatus,
        detail: str,
        completed: bool = False,
        task_execution_id: str | None = None,
        governance_action: str | None = None,
    ) -> WorkflowExecutionRecord:
        execution.status = status
        execution.detail = detail
        if task_execution_id is not None and task_execution_id not in execution.task_execution_ids:
            execution.task_execution_ids.append(task_execution_id)
        if governance_action is not None:
            execution.governance_actions.append(governance_action)
        if completed:
            execution.completed_at = utc_now()
        execution.state_history.append(
            {
                "status": status.value,
                "timestamp": utc_now().isoformat(),
                "detail": detail,
                "task_execution_id": task_execution_id,
                "governance_action": governance_action,
            }
        )
        return execution

    def complete_workflow_execution(
        self,
        execution: WorkflowExecutionRecord,
        status: WorkflowRunStatus,
        detail: str,
        task_execution_id: str | None = None,
        governance_action: str | None = None,
    ) -> WorkflowExecutionRecord:
        return self.transition_workflow_execution(
            execution,
            status=status,
            detail=detail,
            completed=True,
            task_execution_id=task_execution_id,
            governance_action=governance_action,
        )

    def fail_workflow_execution(
        self, execution: WorkflowExecutionRecord, detail: str, task_execution_id: str | None = None
    ) -> WorkflowExecutionRecord:
        return self.transition_workflow_execution(
            execution,
            status=WorkflowRunStatus.failed,
            detail=detail,
            completed=True,
            task_execution_id=task_execution_id,
        )

    def list_workflow_runs(self) -> list[WorkflowExecutionSummary]:
        return [
            WorkflowExecutionSummary(
                execution_id=run.execution_id,
                workflow_id=run.workflow_id,
                workflow_name=run.workflow_name,
                status=run.status,
                started_at=run.started_at,
                completed_at=run.completed_at,
                detail=run.detail,
                task_execution_ids=run.task_execution_ids,
                governance_actions=run.governance_actions,
            )
            for run in self._workflow_runs
        ]


def build_default_tools() -> list[ToolDefinition]:
    return [
        ToolDefinition(
            tool_id="notify_supervisor",
            name="Supervisor Notification",
            description="Notify the shift supervisor with an operational summary.",
            action_type="notify",
            target="shift_supervisor",
            parameters={"channel": "ops-supervision"},
            criticality=0.35,
            category="notification",
            tags=["operations", "supervision"],
        ),
        ToolDefinition(
            tool_id="page_incident_channel",
            name="Incident Broadcast",
            description="Notify the incident response channel with a structured triage output.",
            action_type="notify",
            target="incident_channel",
            parameters={"channel": "incident-response"},
            requires_approval=True,
            criticality=0.55,
            category="notification",
            tags=["incident-response", "triage"],
        ),
        ToolDefinition(
            tool_id="queue_human_review",
            name="Human Review Queue",
            description="Escalate a task into a supervised human review queue.",
            action_type="human",
            target="review_queue",
            parameters={"queue": "mission-critical-review"},
            requires_approval=True,
            criticality=0.7,
            category="human-loop",
            tags=["review", "escalation"],
        ),
    ]


def build_default_agents() -> list[AgentDefinition]:
    default_streams = [
        StreamSpec(source_id="camera_001", modality="vision", config={"fps": 30}),
        StreamSpec(source_id="mic_001", modality="audio", config={"sample_rate_hz": 16000}),
        StreamSpec(source_id="sensor_001", modality="sensor", config={"site": "factory-alpha"}),
        StreamSpec(source_id="log_001", modality="text", config={"channel": "ops-log"}),
    ]
    tools = {tool.tool_id: tool for tool in build_default_tools()}

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
            tools=[tool_binding_from_definition(tools["notify_supervisor"])],
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
            tools=[tool_binding_from_definition(tools["page_incident_channel"])],
            tags=["incident-response", "causal-analysis", "triage"],
        ),
    ]


def build_default_tasks() -> list[TaskTemplate]:
    return [
        TaskTemplate(
            task_id="watch_line_three",
            name="Watch Line Three",
            description="Continuously assess multimodal signals for early signs of instability on assembly line three.",
            agent_id="ops_supervisor",
            query="Assess assembly line three for multimodal instability and escalate early risk patterns.",
            tool_id="notify_supervisor",
            tags=["operations", "monitoring"],
        ),
        TaskTemplate(
            task_id="triage_active_incident",
            name="Triage Active Incident",
            description="Correlate current multimodal evidence and produce a safe incident routing decision.",
            agent_id="incident_triage",
            query="Explain the likely cause of the active incident and determine the safest governed next action.",
            tool_id="page_incident_channel",
            tags=["incident-response", "triage"],
        ),
    ]


def build_default_workflows() -> list[WorkflowTemplate]:
    return [
        WorkflowTemplate(
            workflow_id="supervise_and_triage_incident",
            name="Supervise And Triage Incident",
            description="Detect early operational instability, then route the active incident through a governed triage pass.",
            task_ids=["watch_line_three", "triage_active_incident"],
            stop_on_statuses=[
                WorkflowRunStatus.monitored,
                WorkflowRunStatus.blocked,
                WorkflowRunStatus.escalated,
                WorkflowRunStatus.failed,
            ],
            tags=["operations", "incident-response", "workflow"],
        )
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
