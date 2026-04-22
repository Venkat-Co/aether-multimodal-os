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
    ReviewQueueItem,
    ReviewReplaySummary,
    ReviewResolveRequest,
    ReviewResolveResult,
    TaskRunRequest,
    TaskRunResult,
    TaskTemplate,
    WorkflowRunRequest,
    WorkflowRunResult,
    WorkflowRunStatus,
    WorkflowStep,
    WorkflowTemplate,
)
from .persistence import KernelPersistenceStore
from .registry import AgentRegistry, build_run_result


class KernelOrchestrator:
    def __init__(
        self,
        clients: AetherServiceClients,
        event_bus: EventBus,
        service_name: str,
        persistence: KernelPersistenceStore | None = None,
    ) -> None:
        self.clients = clients
        self.event_bus = event_bus
        self.service_name = service_name
        self.persistence = persistence

    async def _persist_registry(self, registry: AgentRegistry) -> None:
        if self.persistence is None:
            return
        try:
            await self.persistence.save_snapshot(registry.export_state())
        except Exception:
            return

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

    async def _publish_review_item(self, review_item: ReviewQueueItem) -> None:
        payload = review_item.model_dump(mode="json")
        try:
            await self.event_bus.publish("reviews", payload, source=self.service_name)
            if not self.event_bus.distributed:
                await self.clients.publish("reviews", payload)
        except Exception:
            await self.clients.publish("reviews", payload)

    @staticmethod
    def _should_queue_review(status: str) -> bool:
        return status in {"blocked", "escalated", "failed"}

    async def _run_review_replay(
        self, registry: AgentRegistry, review_item: ReviewQueueItem, request: ReviewResolveRequest
    ) -> ReviewReplaySummary:
        if review_item.source_kind == "agent":
            agent = registry.get_agent(review_item.source_id)
            if agent is None:
                raise ValueError(f"Agent '{review_item.source_id}' not found for review replay")
            payload = dict(review_item.metadata.get("agent_request", {}))
            payload["publish_realtime"] = request.publish_realtime
            replay_request = AgentRunRequest.model_validate(payload)
            replay_result = await self.run_agent(registry, agent, replay_request)
            return ReviewReplaySummary(
                source_kind="agent",
                source_id=agent.agent_id,
                run_id=replay_result.run_id,
                status=replay_result.status.value,
            )

        if review_item.source_kind == "task":
            task = registry.get_task(review_item.source_id)
            if task is None:
                raise ValueError(f"Task '{review_item.source_id}' not found for review replay")
            payload = dict(review_item.metadata.get("task_request", {}))
            payload["publish_realtime"] = request.publish_realtime
            replay_request = TaskRunRequest.model_validate(payload)
            replay_result = await self.run_task(registry, task, replay_request)
            return ReviewReplaySummary(
                source_kind="task",
                source_id=task.task_id,
                run_id=replay_result.task_execution.execution_id,
                status=replay_result.task_execution.status.value,
            )

        if review_item.source_kind == "workflow":
            workflow = registry.get_workflow(review_item.source_id)
            if workflow is None:
                raise ValueError(f"Workflow '{review_item.source_id}' not found for review replay")
            payload = dict(review_item.metadata.get("workflow_request", {}))
            payload["publish_realtime"] = request.publish_realtime
            replay_request = WorkflowRunRequest.model_validate(payload)
            replay_result = await self.run_workflow(registry, workflow, replay_request)
            return ReviewReplaySummary(
                source_kind="workflow",
                source_id=workflow.workflow_id,
                run_id=replay_result.workflow_execution.execution_id,
                status=replay_result.workflow_execution.status.value,
            )

        raise ValueError(f"Review replay is not supported for source kind '{review_item.source_kind}'")

    async def resolve_review(
        self, registry: AgentRegistry, review_id: str, request: ReviewResolveRequest
    ) -> ReviewResolveResult:
        review_item = registry.get_review(review_id)
        if review_item is None:
            raise ValueError(f"Review item '{review_id}' not found")

        replay: ReviewReplaySummary | None = None
        if request.rerun_source:
            replay = await self._run_review_replay(registry, review_item, request)

        resolved_review = registry.resolve_review(review_id, request)
        if resolved_review is None:
            raise ValueError(f"Review item '{review_id}' not found")

        if replay is not None:
            resolved_review.metadata["replay"] = replay.model_dump(mode="json")
            resolved_review.updated_at = datetime.now(tz=UTC)

        await self._persist_registry(registry)
        await self._publish_review_item(resolved_review)
        await self._publish_bus_event(
            "kernel.events.review_resolved",
            {
                "review_id": resolved_review.review_id,
                "resolution": resolved_review.resolution,
                "reviewed_by": resolved_review.reviewed_by,
                "reviewed_by_role": resolved_review.reviewed_by_role,
                "review_source": resolved_review.review_source,
                "rerun_source": request.rerun_source,
                "replay_run_id": replay.run_id if replay is not None else None,
            },
        )
        return ReviewResolveResult(review=resolved_review, replay=replay)

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
        self, registry: AgentRegistry, agent: AgentDefinition, request: AgentRunRequest, queue_review: bool = True
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
        if queue_review and self._should_queue_review(run_result.status.value):
            decision = run_result.pipeline_result.governance_decision
            review_item = registry.queue_review(
                source_kind="agent",
                source_id=agent.agent_id,
                source_name=agent.name,
                run_id=run_result.run_id,
                title=f"{agent.name} requires operator review",
                summary=decision.get("reasoning", "Governed agent run requires human oversight."),
                trigger_status=run_result.status.value,
                governance_action=run_result.governance_action,
                risk_level=str(decision.get("risk_level", "medium")),
                metadata={
                    "decision_id": decision.get("decision_id"),
                    "query": pipeline_request.query,
                    "reasoning_mode": pipeline_request.reasoning_mode.value,
                    "agent_request": request.model_dump(mode="json"),
                },
            )
            await self._publish_review_item(review_item)
        await self._persist_registry(registry)
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

    async def run_task(
        self, registry: AgentRegistry, task: TaskTemplate, request: TaskRunRequest, queue_review: bool = True
    ) -> TaskRunResult:
        agent = registry.get_agent(task.agent_id)
        if agent is None:
            raise ValueError(f"Agent '{task.agent_id}' not found for task '{task.task_id}'")

        tool = registry.get_tool(request.tool_id or task.tool_id) if (request.tool_id or task.tool_id) else None
        execution = registry.start_task_execution(task, agent, tool)
        await self._persist_registry(registry)
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
            agent_run = await self.run_agent(registry, agent, agent_request, queue_review=False)
            registry.complete_task_execution(
                execution,
                governance_action=agent_run.governance_action,
                detail=f"Task completed via agent {agent.name} with governance action {agent_run.governance_action}.",
                agent_run_id=agent_run.run_id,
            )
            if queue_review and self._should_queue_review(execution.status.value):
                decision = agent_run.pipeline_result.governance_decision
                review_item = registry.queue_review(
                    source_kind="task",
                    source_id=task.task_id,
                    source_name=task.name,
                    run_id=execution.execution_id,
                    title=f"{task.name} requires operator review",
                    summary=execution.detail,
                    trigger_status=execution.status.value,
                    governance_action=execution.governance_action,
                    risk_level=str(decision.get("risk_level", "medium")),
                    metadata={
                        "agent_id": agent.agent_id,
                        "agent_run_id": agent_run.run_id,
                        "decision_id": decision.get("decision_id"),
                        "task_request": request.model_dump(mode="json"),
                    },
                )
                await self._publish_review_item(review_item)
            await self._persist_registry(registry)
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
            if queue_review and self._should_queue_review(execution.status.value):
                review_item = registry.queue_review(
                    source_kind="task",
                    source_id=task.task_id,
                    source_name=task.name,
                    run_id=execution.execution_id,
                    title=f"{task.name} failed and requires operator review",
                    summary=execution.detail,
                    trigger_status=execution.status.value,
                    governance_action=execution.governance_action,
                    risk_level="high",
                    metadata={
                        "agent_id": agent.agent_id,
                        "task_request": request.model_dump(mode="json"),
                    },
                )
                await self._publish_review_item(review_item)
            await self._persist_registry(registry)
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
        steps = registry.workflow_steps(workflow)
        execution = registry.start_workflow_execution(workflow)
        await self._persist_registry(registry)
        await self._publish_bus_event(
            "kernel.events.workflow_started",
            {
                "workflow_id": workflow.workflow_id,
                "execution_id": execution.execution_id,
                "task_count": len(steps),
            },
        )

        task_runs: list[TaskRunResult] = []
        last_governance_action: str | None = None
        completed_step_ids: set[str] = set()
        remaining_steps = {step.step_id: step for step in steps}

        async def execute_step(step: WorkflowStep) -> tuple[WorkflowStep, TaskRunResult]:
            task = registry.get_task(step.task_id)
            if task is None:
                raise ValueError(f"Task '{step.task_id}' not found for workflow '{workflow.workflow_id}'")

            task_request = TaskRunRequest(
                query=request.task_query_overrides.get(task.task_id),
                tool_id=request.task_tool_overrides.get(task.task_id),
                packets_per_stream=request.default_packets_per_stream,
                publish_realtime=request.publish_realtime,
                register_streams=request.register_streams,
                reasoning_state_overrides=request.task_reasoning_overrides.get(task.task_id, {}),
                window_center=request.window_center,
            )
            task_result = await self.run_task(registry, task, task_request, queue_review=False)
            return step, task_result

        while remaining_steps:
            ready_steps = [
                step
                for step in remaining_steps.values()
                if all(dependency in completed_step_ids for dependency in step.depends_on)
            ]

            if not ready_steps:
                registry.fail_workflow_execution(
                    execution,
                    detail="Workflow halted because no dependency-ready steps were available.",
                )
                review_item = registry.queue_review(
                    source_kind="workflow",
                    source_id=workflow.workflow_id,
                    source_name=workflow.name,
                    run_id=execution.execution_id,
                    title=f"{workflow.name} failed and requires operator review",
                    summary=execution.detail,
                    trigger_status=execution.status.value,
                    governance_action=execution.governance_action,
                    risk_level="high",
                    metadata={
                        "completed_steps": execution.completed_step_ids,
                        "step_count": execution.step_count,
                        "workflow_request": request.model_dump(mode="json"),
                    },
                )
                await self._publish_review_item(review_item)
                await self._persist_registry(registry)
                await self._publish_bus_event(
                    "kernel.events.workflow_failed",
                    {
                        "workflow_id": workflow.workflow_id,
                        "execution_id": execution.execution_id,
                        "status": execution.status.value,
                        "detail": execution.detail,
                    },
                )
                raise ValueError(f"Workflow '{workflow.workflow_id}' has unresolved or cyclic step dependencies")

            results = await asyncio.gather(
                *(execute_step(step) for step in ready_steps),
                return_exceptions=True,
            )

            stop_triggered = False
            terminal_status = WorkflowRunStatus.completed
            terminal_detail = "Workflow completed all configured steps."
            terminal_task_execution_id: str | None = None
            terminal_step_id: str | None = None
            terminal_governance_action: str | None = None

            for result in results:
                if isinstance(result, Exception):
                    registry.fail_workflow_execution(
                        execution,
                        detail=f"Workflow failed during parallel step execution: {result}",
                    )
                    review_item = registry.queue_review(
                        source_kind="workflow",
                        source_id=workflow.workflow_id,
                        source_name=workflow.name,
                        run_id=execution.execution_id,
                        title=f"{workflow.name} failed and requires operator review",
                        summary=execution.detail,
                        trigger_status=execution.status.value,
                        governance_action=execution.governance_action,
                        risk_level="high",
                        metadata={
                            "completed_steps": execution.completed_step_ids,
                            "step_count": execution.step_count,
                            "workflow_request": request.model_dump(mode="json"),
                        },
                    )
                    await self._publish_review_item(review_item)
                    await self._persist_registry(registry)
                    await self._publish_bus_event(
                        "kernel.events.workflow_failed",
                        {
                            "workflow_id": workflow.workflow_id,
                            "execution_id": execution.execution_id,
                            "status": execution.status.value,
                            "detail": execution.detail,
                        },
                    )
                    raise result

                step, task_result = result
                task_runs.append(task_result)
                completed_step_ids.add(step.step_id)
                remaining_steps.pop(step.step_id, None)

                last_governance_action = task_result.task_execution.governance_action
                task_status = task_result.task_execution.status
                workflow_status = registry.workflow_status_from_task_status(task_status)
                step_result = {
                    "step_id": step.step_id,
                    "task_id": step.task_id,
                    "task_execution_id": task_result.task_execution.execution_id,
                    "status": task_status.value,
                    "governance_action": last_governance_action or "",
                }
                registry.transition_workflow_execution(
                    execution,
                    status=WorkflowRunStatus.running,
                    detail=f"Step {step.step_id} completed with task status {task_status.value}.",
                    task_execution_id=task_result.task_execution.execution_id,
                    governance_action=last_governance_action,
                    completed_step_id=step.step_id,
                    step_result=step_result,
                )
                await self._publish_bus_event(
                    "kernel.events.workflow_step_completed",
                    {
                        "workflow_id": workflow.workflow_id,
                        "execution_id": execution.execution_id,
                        "step_id": step.step_id,
                        "task_id": step.task_id,
                        "task_execution_id": task_result.task_execution.execution_id,
                        "task_status": task_status.value,
                        "governance_action": last_governance_action,
                    },
                )
                await self._persist_registry(registry)

                if workflow_status in workflow.stop_on_statuses:
                    stop_triggered = True
                    terminal_status = workflow_status
                    terminal_detail = f"Workflow stopped after step {step.step_id} due to status {workflow_status.value}."
                    terminal_task_execution_id = task_result.task_execution.execution_id
                    terminal_step_id = step.step_id
                    terminal_governance_action = last_governance_action

            if stop_triggered:
                registry.complete_workflow_execution(
                    execution,
                    status=terminal_status,
                    detail=terminal_detail,
                    task_execution_id=terminal_task_execution_id,
                    governance_action=terminal_governance_action,
                    completed_step_id=terminal_step_id,
                )
                if self._should_queue_review(execution.status.value):
                    risk_level = "medium"
                    if task_runs and task_runs[-1].agent_run is not None:
                        risk_level = str(
                            task_runs[-1].agent_run.pipeline_result.governance_decision.get("risk_level", "medium")
                        )
                    review_item = registry.queue_review(
                        source_kind="workflow",
                        source_id=workflow.workflow_id,
                        source_name=workflow.name,
                        run_id=execution.execution_id,
                        title=f"{workflow.name} requires operator review",
                        summary=execution.detail,
                        trigger_status=execution.status.value,
                        governance_action=terminal_governance_action,
                        risk_level=risk_level,
                        metadata={
                            "completed_steps": execution.completed_step_ids,
                            "step_count": execution.step_count,
                            "workflow_request": request.model_dump(mode="json"),
                        },
                    )
                    await self._publish_review_item(review_item)
                await self._persist_registry(registry)
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

        final_status = (
            registry.workflow_status_from_task_status(task_runs[-1].task_execution.status)
            if task_runs
            else WorkflowRunStatus.completed
        )
        registry.complete_workflow_execution(
            execution,
            status=final_status,
            detail="Workflow completed all configured steps.",
            task_execution_id=task_runs[-1].task_execution.execution_id if task_runs else None,
            governance_action=last_governance_action,
            completed_step_id=steps[-1].step_id if steps else None,
        )
        if self._should_queue_review(execution.status.value):
            risk_level = "medium"
            if task_runs and task_runs[-1].agent_run is not None:
                risk_level = str(task_runs[-1].agent_run.pipeline_result.governance_decision.get("risk_level", "medium"))
            review_item = registry.queue_review(
                source_kind="workflow",
                source_id=workflow.workflow_id,
                source_name=workflow.name,
                run_id=execution.execution_id,
                title=f"{workflow.name} requires operator review",
                summary=execution.detail,
                trigger_status=execution.status.value,
                governance_action=last_governance_action,
                risk_level=risk_level,
                metadata={
                    "completed_steps": execution.completed_step_ids,
                    "step_count": execution.step_count,
                    "workflow_request": request.model_dump(mode="json"),
                },
            )
            await self._publish_review_item(review_item)
        await self._persist_registry(registry)
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
