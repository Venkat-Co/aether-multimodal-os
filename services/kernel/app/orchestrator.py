from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from aether_core.event_bus import EventBus
from aether_core.vector import deterministic_embedding

from .clients import AetherServiceClients
from .models import (
    AgentDefinition,
    AgentRunRequest,
    AgentRunResult,
    KernelPipelineRequest,
    KernelPipelineResult,
    TaskRunRequest,
    TaskRunResult,
    TaskTemplate,
    WorkflowRunRequest,
    WorkflowRunResult,
    WorkflowRunStatus,
    WorkflowTemplate,
)
from .registry import AgentRegistry, build_run_result


class KernelOrchestrator:
    def __init__(self, clients: AetherServiceClients, event_bus: EventBus, service_name: str) -> None:
        self.clients = clients
        self.event_bus = event_bus
        self.service_name = service_name

    async def _publish_bus_event(self, topic: str, payload: dict[str, Any]) -> None:
        try:
            await self.event_bus.publish(topic, payload, source=self.service_name)
        except Exception:
            return

    async def _await_fusion_buffer(self, minimum_packets: int, timeout_seconds: float = 2.0) -> None:
        deadline = asyncio.get_running_loop().time() + timeout_seconds
        while asyncio.get_running_loop().time() < deadline:
            try:
                state = await self.clients.fusion_buffer_state()
            except Exception:
                return
            if state.get("buffered_packets", 0) >= minimum_packets:
                return
            await asyncio.sleep(0.1)

    def _build_reasoning_state(
        self, packets: list[dict[str, Any]], fused_event: dict[str, Any], overrides: dict[str, Any]
    ) -> dict[str, Any]:
        state: dict[str, Any] = {
            "fusion_confidence": fused_event["confidence"],
            "modality_count": len(fused_event["modalities"]),
        }
        for packet in packets:
            raw_data = packet.get("raw_data", {})
            if isinstance(raw_data, dict):
                for key, value in raw_data.items():
                    if isinstance(value, (int, float)):
                        state[key] = value
        state.update(overrides)
        return state

    def _build_memory_payload(
        self, request: KernelPipelineRequest, fused_event: dict[str, Any], reasoning_state: dict[str, Any]
    ) -> dict[str, Any]:
        return {
            "memory_type": request.memory_type.value,
            "content": {
                "event_type": "fused_event",
                "description": fused_event["semantic_summary"],
                "query": request.query,
                "reasoning_state": reasoning_state,
            },
            "embedding": fused_event["fusion_vector"],
            "timestamp": fused_event["timestamp"],
            "location": fused_event["spatial_bounds"]["center"],
            "confidence": fused_event["confidence"],
            "importance_score": fused_event["confidence"],
        }

    def _build_governance_context(
        self, request: KernelPipelineRequest, reasoning_result: dict[str, Any], reasoning_state: dict[str, Any]
    ) -> dict[str, Any]:
        action_parameters = request.action_template.parameters
        return {
            "action": action_parameters.get("action", request.action_template.target),
            "amount": action_parameters.get("amount", 0),
            "reversibility": request.action_template.reversibility,
            "criticality": request.action_template.criticality,
            "data_type": action_parameters.get("data_type"),
            "intent": action_parameters.get("intent"),
            "capability": action_parameters.get("capability"),
            "sensor_confidence": reasoning_state.get("fusion_confidence", 1.0),
            "reasoning_mode": reasoning_result["mode"],
        }

    async def _publish_pipeline_state(
        self,
        packets: list[dict[str, Any]],
        fused_event: dict[str, Any],
        memory_node: dict[str, Any],
        reasoning_result: dict[str, Any],
        governance_decision: dict[str, Any],
        action_result: dict[str, Any] | None,
    ) -> None:
        async def emit(topic: str, payload: dict[str, Any]) -> None:
            try:
                await self.event_bus.publish(topic, payload, source=self.service_name)
                if not self.event_bus.distributed:
                    await self.clients.publish(topic, payload)
            except Exception:
                await self.clients.publish(topic, payload)

        if not self.event_bus.distributed:
            for packet in packets:
                await emit("streams", packet)
            await emit("fusion", fused_event)
            await emit("memory", memory_node)
        await emit("reasoning", reasoning_result)
        await emit("alerts", governance_decision)
        if action_result is not None:
            await emit(
                "dashboard",
                {
                    "status": action_result.get("status", "executed"),
                    "latest_action": action_result,
                },
            )

    async def run_pipeline(self, request: KernelPipelineRequest) -> KernelPipelineResult:
        registered_streams: list[dict[str, Any]] = []
        if request.register_streams:
            for stream in request.streams:
                await self._publish_bus_event(
                    "kernel.commands.stream.register",
                    {"source_id": stream.source_id, "modality": stream.modality.value},
                )
                registered_streams.append(await self.clients.register_stream(stream.model_dump(mode="json")))

        packets: list[dict[str, Any]] = []
        for stream in request.streams:
            for _ in range(request.packets_per_stream):
                packet = await self.clients.emit_packet(stream.source_id)
                packets.append(packet)
                if not self.event_bus.distributed:
                    await self.clients.ingest_fusion_packet(packet)
                await self._publish_bus_event(
                    "kernel.events.packet_emitted",
                    {"source_id": stream.source_id, "packet_id": packet["packet_id"]},
                )

        if self.event_bus.distributed:
            await self._await_fusion_buffer(len(packets))

        fused_event = await self.clients.fuse_window(request.window_center.isoformat())
        await self._publish_bus_event(
            "kernel.events.fused",
            {"event_id": fused_event["event_id"], "confidence": fused_event["confidence"]},
        )
        reasoning_state = self._build_reasoning_state(packets, fused_event, request.reasoning_state_overrides)
        memory_node = await self.clients.store_memory(
            self._build_memory_payload(request, fused_event, reasoning_state)
        )

        reasoning_result = await self.clients.reason(
            {
                "query": request.query,
                "current_state": reasoning_state,
                "mode": request.reasoning_mode.value,
                "history": request.reasoning_history,
                "horizon": 3,
            }
        )

        governance_context = self._build_governance_context(request, reasoning_result, reasoning_state)
        governance_decision = await self.clients.evaluate_governance(
            {
                "action_context": governance_context,
                "action_embedding": deterministic_embedding(
                    {"query": request.query, "governance_context": governance_context}
                ),
            }
        )

        action_result: dict[str, Any] | None = None
        if governance_decision["action_taken"] == "ALLOW":
            action_result = await self.clients.dispatch_action(
                {
                    "action_type": request.action_template.action_type,
                    "target": request.action_template.target,
                    "parameters": request.action_template.parameters,
                    "requires_approval": request.action_template.requires_approval,
                    "reversibility": request.action_template.reversibility,
                    "criticality": request.action_template.criticality,
                }
            )
            await self._publish_bus_event(
                "kernel.events.action_dispatched",
                {"status": action_result["status"], "target": request.action_template.target},
            )

        if request.publish_realtime:
            await self._publish_pipeline_state(
                packets,
                fused_event,
                memory_node,
                reasoning_result,
                governance_decision,
                action_result,
            )

        return KernelPipelineResult(
            registered_streams=registered_streams,
            packets=packets,
            fused_event=fused_event,
            memory_node=memory_node,
            reasoning_result=reasoning_result,
            governance_decision=governance_decision,
            action_result=action_result,
        )

    async def run_agent(
        self, registry: AgentRegistry, agent: AgentDefinition, request: AgentRunRequest
    ) -> AgentRunResult:
        started_at = datetime.now(tz=UTC)
        await self._publish_bus_event(
            "kernel.events.agent_run_started",
            {"agent_id": agent.agent_id, "agent_name": agent.name, "started_at": started_at.isoformat()},
        )

        pipeline_request = registry.build_pipeline_request(agent, request)
        pipeline_result = await self.run_pipeline(pipeline_request)
        completed_at = datetime.now(tz=UTC)
        governance_action = pipeline_result.governance_decision["action_taken"]
        status = registry.status_from_governance(governance_action)
        run_result = build_run_result(
            agent=agent,
            status=status,
            governance_action=governance_action,
            started_at=started_at,
            completed_at=completed_at,
            pipeline_result=pipeline_result,
        )
        registry.record_run(run_result)
        await self._publish_bus_event(
            "kernel.events.agent_run_completed",
            {
                "run_id": run_result.run_id,
                "agent_id": agent.agent_id,
                "status": run_result.status.value,
                "governance_action": governance_action,
            },
        )
        return run_result

    async def run_task(self, registry: AgentRegistry, task: TaskTemplate, request: TaskRunRequest) -> TaskRunResult:
        agent = registry.get_agent(task.agent_id)
        if agent is None:
            raise ValueError(f"Agent '{task.agent_id}' not found for task '{task.task_id}'")

        tool = registry.get_tool(request.tool_id or task.tool_id) if (request.tool_id or task.tool_id) else None
        execution = registry.start_task_execution(task, agent, tool)
        await self._publish_bus_event(
            "kernel.events.task_started",
            {
                "task_id": task.task_id,
                "execution_id": execution.execution_id,
                "agent_id": agent.agent_id,
                "tool_id": execution.tool_id,
            },
        )

        try:
            agent_request = registry.build_agent_run_request_from_task(task, request, tool)
            agent_run = await self.run_agent(registry, agent, agent_request)
            registry.complete_task_execution(
                execution,
                governance_action=agent_run.governance_action,
                detail=f"Task completed via agent {agent.name} with governance action {agent_run.governance_action}.",
                agent_run_id=agent_run.run_id,
            )
            await self._publish_bus_event(
                "kernel.events.task_completed",
                {
                    "task_id": task.task_id,
                    "execution_id": execution.execution_id,
                    "status": execution.status.value,
                    "governance_action": execution.governance_action,
                    "agent_run_id": agent_run.run_id,
                },
            )
            return TaskRunResult(task_execution=execution, agent_run=agent_run)
        except Exception as exc:
            registry.fail_task_execution(execution, detail=f"Task failed before completion: {exc}")
            await self._publish_bus_event(
                "kernel.events.task_failed",
                {
                    "task_id": task.task_id,
                    "execution_id": execution.execution_id,
                    "status": execution.status.value,
                    "detail": execution.detail,
                },
            )
            raise

    async def run_workflow(
        self, registry: AgentRegistry, workflow: WorkflowTemplate, request: WorkflowRunRequest
    ) -> WorkflowRunResult:
        execution = registry.start_workflow_execution(workflow)
        await self._publish_bus_event(
            "kernel.events.workflow_started",
            {
                "workflow_id": workflow.workflow_id,
                "execution_id": execution.execution_id,
                "task_count": len(workflow.task_ids),
            },
        )

        task_runs: list[TaskRunResult] = []
        last_governance_action: str | None = None

        for task_id in workflow.task_ids:
            task = registry.get_task(task_id)
            if task is None:
                registry.fail_workflow_execution(
                    execution,
                    detail=f"Workflow halted because task '{task_id}' was not found.",
                )
                await self._publish_bus_event(
                    "kernel.events.workflow_failed",
                    {
                        "workflow_id": workflow.workflow_id,
                        "execution_id": execution.execution_id,
                        "status": execution.status.value,
                        "detail": execution.detail,
                    },
                )
                raise ValueError(f"Task '{task_id}' not found for workflow '{workflow.workflow_id}'")

            task_request = TaskRunRequest(
                query=request.task_query_overrides.get(task.task_id),
                tool_id=request.task_tool_overrides.get(task.task_id),
                packets_per_stream=request.default_packets_per_stream,
                publish_realtime=request.publish_realtime,
                register_streams=request.register_streams,
                reasoning_state_overrides=request.task_reasoning_overrides.get(task.task_id, {}),
                window_center=request.window_center,
            )
            task_result = await self.run_task(registry, task, task_request)
            task_runs.append(task_result)
            last_governance_action = task_result.task_execution.governance_action
            task_status = task_result.task_execution.status
            workflow_status = registry.workflow_status_from_task_status(task_status)
            registry.transition_workflow_execution(
                execution,
                status=WorkflowRunStatus.running,
                detail=f"Task {task.task_id} completed with status {task_status.value}.",
                task_execution_id=task_result.task_execution.execution_id,
                governance_action=last_governance_action,
            )
            await self._publish_bus_event(
                "kernel.events.workflow_task_completed",
                {
                    "workflow_id": workflow.workflow_id,
                    "execution_id": execution.execution_id,
                    "task_id": task.task_id,
                    "task_execution_id": task_result.task_execution.execution_id,
                    "task_status": task_status.value,
                    "governance_action": last_governance_action,
                },
            )

            if workflow_status in workflow.stop_on_statuses:
                registry.complete_workflow_execution(
                    execution,
                    status=workflow_status,
                    detail=f"Workflow stopped after task {task.task_id} due to status {workflow_status.value}.",
                    task_execution_id=task_result.task_execution.execution_id,
                    governance_action=last_governance_action,
                )
                await self._publish_bus_event(
                    "kernel.events.workflow_completed",
                    {
                        "workflow_id": workflow.workflow_id,
                        "execution_id": execution.execution_id,
                        "status": execution.status.value,
                        "detail": execution.detail,
                    },
                )
                return WorkflowRunResult(workflow_execution=execution, task_runs=task_runs)

        final_status = registry.workflow_status_from_task_status(task_runs[-1].task_execution.status) if task_runs else WorkflowRunStatus.completed
        registry.complete_workflow_execution(
            execution,
            status=final_status,
            detail="Workflow completed all configured tasks.",
            task_execution_id=task_runs[-1].task_execution.execution_id if task_runs else None,
            governance_action=last_governance_action,
        )
        await self._publish_bus_event(
            "kernel.events.workflow_completed",
            {
                "workflow_id": workflow.workflow_id,
                "execution_id": execution.execution_id,
                "status": execution.status.value,
                "detail": execution.detail,
            },
        )
        return WorkflowRunResult(workflow_execution=execution, task_runs=task_runs)
