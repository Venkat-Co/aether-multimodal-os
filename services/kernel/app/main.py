from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from aether_core.config import get_settings
from aether_core.event_bus import InMemoryEventBus, build_event_bus, connect_event_bus_with_retry
from aether_core.observability import configure_logging, instrument_fastapi, mount_metrics

from .clients import AetherServiceClients
from .models import (
    AgentCreateRequest,
    AgentDefinition,
    AgentRunRequest,
    AgentRunResult,
    AgentRunSummary,
    KernelPipelineRequest,
    KernelPipelineResult,
    ReviewQueueItem,
    ReviewResolveRequest,
    ReviewResolveResult,
    TaskCreateRequest,
    TaskExecutionSummary,
    TaskRunRequest,
    TaskRunResult,
    TaskTemplate,
    ToolCreateRequest,
    ToolDefinition,
    WorkflowCreateRequest,
    WorkflowExecutionSummary,
    WorkflowRunRequest,
    WorkflowRunResult,
    WorkflowTemplate,
)
from .orchestrator import KernelOrchestrator
from .persistence import KernelPersistenceStore
from .registry import AgentRegistry, build_default_agents, build_default_tasks, build_default_tools, build_default_workflows

settings = get_settings("aether-kernel")
logger = configure_logging(settings.service_name, settings.log_level)

clients = AetherServiceClients(settings)
event_bus = build_event_bus(settings)
persistence = KernelPersistenceStore(settings)
orchestrator = KernelOrchestrator(clients, event_bus, settings.service_name, persistence=persistence)
registry = AgentRegistry(
    seed_agents=build_default_agents(),
    seed_tools=build_default_tools(),
    seed_tasks=build_default_tasks(),
    seed_workflows=build_default_workflows(),
)


async def persist_runtime_state() -> None:
    try:
        persisted = await persistence.save_snapshot(registry.export_state())
    except Exception as exc:
        logger.warning("Kernel control plane persistence failed", extra={"detail": str(exc)})
        return
    if not persisted:
        logger.info("Kernel control plane persistence unavailable; continuing with in-memory registry")


async def publish_runtime_snapshot() -> None:
    await clients.publish(
        "dashboard",
        {
            "agents": [agent.model_dump(mode="json") for agent in registry.list_agents()],
            "agent_runs": [run.model_dump(mode="json") for run in registry.list_runs()],
            "tools": [tool.model_dump(mode="json") for tool in registry.list_tools()],
            "tasks": [task.model_dump(mode="json") for task in registry.list_tasks()],
            "task_runs": [run.model_dump(mode="json") for run in registry.list_task_runs()],
            "workflows": [workflow.model_dump(mode="json") for workflow in registry.list_workflows()],
            "workflow_runs": [run.model_dump(mode="json") for run in registry.list_workflow_runs()],
            "reviews": [review.model_dump(mode="json") for review in registry.list_reviews()],
        },
    )


@asynccontextmanager
async def lifespan(_: FastAPI):
    global event_bus
    await persistence.initialize()
    try:
        snapshot = await persistence.load_snapshot()
    except Exception as exc:
        snapshot = None
        logger.warning("Failed to load kernel control plane snapshot", extra={"detail": str(exc)})
    if snapshot is not None:
        registry.hydrate_state(snapshot, merge=True)
        logger.info(
            "Hydrated kernel control plane snapshot",
            extra={
                "agents": len(snapshot.agents),
                "tasks": len(snapshot.tasks),
                "workflows": len(snapshot.workflows),
                "reviews": len(snapshot.reviews),
            },
        )
    await persist_runtime_state()
    try:
        await connect_event_bus_with_retry(
            event_bus,
            attempts=settings.startup_retry_attempts,
            delay_seconds=settings.startup_retry_delay_seconds,
        )
    except Exception as exc:
        logger.warning("Falling back to in-memory kernel event bus", extra={"detail": str(exc)})
        event_bus = InMemoryEventBus()
        await event_bus.connect()
        orchestrator.event_bus = event_bus
    try:
        await publish_runtime_snapshot()
    except Exception:
        logger.info("Realtime dashboard unavailable during kernel runtime snapshot publish")
    yield
    await event_bus.close()
    await clients.close()
    await persistence.close()


app = FastAPI(title="AETHER Kernel Service", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
instrument_fastapi(app, settings)
mount_metrics(app)


@app.get("/healthz")
async def healthcheck() -> dict[str, str]:
    return {"status": "ok", "service": settings.service_name}


@app.get("/api/v1/kernel/backends")
async def kernel_backends() -> dict[str, object]:
    return persistence.backend_status


@app.post("/api/v1/kernel/pipeline/run", response_model=KernelPipelineResult)
async def run_pipeline(request: KernelPipelineRequest) -> KernelPipelineResult:
    result = await orchestrator.run_pipeline(request)
    logger.info(
        "Completed kernel pipeline",
        extra={
            "registered_streams": len(result.registered_streams),
            "packet_count": len(result.packets),
            "decision": result.governance_decision["action_taken"],
        },
    )
    return result


@app.post("/api/v1/kernel/pipeline/demo", response_model=KernelPipelineResult)
async def run_demo() -> KernelPipelineResult:
    return await orchestrator.run_pipeline(KernelPipelineRequest())


@app.get("/api/v1/kernel/tools", response_model=list[ToolDefinition])
async def list_tools() -> list[ToolDefinition]:
    return registry.list_tools()


@app.get("/api/v1/kernel/tools/{tool_id}", response_model=ToolDefinition)
async def get_tool(tool_id: str) -> ToolDefinition:
    tool = registry.get_tool(tool_id)
    if tool is None:
        raise HTTPException(status_code=404, detail=f"Tool '{tool_id}' not found")
    return tool


@app.post("/api/v1/kernel/tools", response_model=ToolDefinition)
async def create_tool(request: ToolCreateRequest) -> ToolDefinition:
    tool = registry.create_tool(request)
    await persist_runtime_state()
    logger.info("Registered kernel tool", extra={"tool_id": tool.tool_id, "name": tool.name})
    try:
        await publish_runtime_snapshot()
    except Exception:
        logger.info("Realtime dashboard unavailable during tool registration publish", extra={"tool_id": tool.tool_id})
    return tool


@app.get("/api/v1/kernel/agents", response_model=list[AgentDefinition])
async def list_agents() -> list[AgentDefinition]:
    return registry.list_agents()


@app.get("/api/v1/kernel/agents/runs", response_model=list[AgentRunSummary])
async def list_agent_runs() -> list[AgentRunSummary]:
    return registry.list_runs()


@app.get("/api/v1/kernel/reviews", response_model=list[ReviewQueueItem])
async def list_reviews() -> list[ReviewQueueItem]:
    return registry.list_reviews()


@app.get("/api/v1/kernel/reviews/{review_id}", response_model=ReviewQueueItem)
async def get_review(review_id: str) -> ReviewQueueItem:
    review = registry.get_review(review_id)
    if review is None:
        raise HTTPException(status_code=404, detail=f"Review item '{review_id}' not found")
    return review


@app.post("/api/v1/kernel/reviews/{review_id}/resolve", response_model=ReviewResolveResult)
async def resolve_review(review_id: str, request: ReviewResolveRequest) -> ReviewResolveResult:
    try:
        result = await orchestrator.resolve_review(registry, review_id, request)
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail.lower() else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc

    logger.info(
        "Resolved review queue item",
        extra={
            "review_id": result.review.review_id,
            "resolution": result.review.resolution,
            "rerun_source": request.rerun_source,
            "replay_run_id": result.replay.run_id if result.replay is not None else None,
        },
    )
    try:
        await publish_runtime_snapshot()
    except Exception:
        logger.info(
            "Realtime dashboard unavailable during review resolution publish",
            extra={"review_id": result.review.review_id},
        )
    return result


@app.post("/api/v1/kernel/agents", response_model=AgentDefinition)
async def create_agent(request: AgentCreateRequest) -> AgentDefinition:
    agent = registry.create_agent(request)
    await persist_runtime_state()
    logger.info("Registered kernel agent", extra={"agent_id": agent.agent_id, "name": agent.name})
    try:
        await publish_runtime_snapshot()
    except Exception:
        logger.info("Realtime dashboard unavailable during agent registration publish", extra={"agent_id": agent.agent_id})
    return agent


@app.get("/api/v1/kernel/agents/{agent_id}", response_model=AgentDefinition)
async def get_agent(agent_id: str) -> AgentDefinition:
    agent = registry.get_agent(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")
    return agent


@app.post("/api/v1/kernel/agents/{agent_id}/runs", response_model=AgentRunResult)
async def run_agent(agent_id: str, request: AgentRunRequest) -> AgentRunResult:
    agent = registry.get_agent(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")
    result = await orchestrator.run_agent(registry, agent, request)
    logger.info(
        "Completed agent run",
        extra={
            "agent_id": result.agent_id,
            "run_id": result.run_id,
            "status": result.status.value,
            "governance_action": result.governance_action,
        },
    )
    try:
        await publish_runtime_snapshot()
    except Exception:
        logger.info("Realtime dashboard unavailable during agent run publish", extra={"agent_id": result.agent_id})
    return result


@app.get("/api/v1/kernel/tasks", response_model=list[TaskTemplate])
async def list_tasks() -> list[TaskTemplate]:
    return registry.list_tasks()


@app.get("/api/v1/kernel/tasks/runs", response_model=list[TaskExecutionSummary])
async def list_task_runs() -> list[TaskExecutionSummary]:
    return registry.list_task_runs()


@app.post("/api/v1/kernel/tasks", response_model=TaskTemplate)
async def create_task(request: TaskCreateRequest) -> TaskTemplate:
    if registry.get_agent(request.agent_id) is None:
        raise HTTPException(status_code=404, detail=f"Agent '{request.agent_id}' not found")
    if request.tool_id is not None and registry.get_tool(request.tool_id) is None:
        raise HTTPException(status_code=404, detail=f"Tool '{request.tool_id}' not found")
    task = registry.create_task(request)
    await persist_runtime_state()
    logger.info("Registered kernel task", extra={"task_id": task.task_id, "agent_id": task.agent_id})
    try:
        await publish_runtime_snapshot()
    except Exception:
        logger.info("Realtime dashboard unavailable during task registration publish", extra={"task_id": task.task_id})
    return task


@app.get("/api/v1/kernel/tasks/{task_id}", response_model=TaskTemplate)
async def get_task(task_id: str) -> TaskTemplate:
    task = registry.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")
    return task


@app.post("/api/v1/kernel/tasks/{task_id}/runs", response_model=TaskRunResult)
async def run_task(task_id: str, request: TaskRunRequest) -> TaskRunResult:
    task = registry.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")
    result = await orchestrator.run_task(registry, task, request)
    logger.info(
        "Completed task run",
        extra={
            "task_id": result.task_execution.task_id,
            "execution_id": result.task_execution.execution_id,
            "status": result.task_execution.status.value,
            "governance_action": result.task_execution.governance_action,
        },
    )
    try:
        await publish_runtime_snapshot()
    except Exception:
        logger.info("Realtime dashboard unavailable during task run publish", extra={"task_id": task.task_id})
    return result


@app.get("/api/v1/kernel/workflows", response_model=list[WorkflowTemplate])
async def list_workflows() -> list[WorkflowTemplate]:
    return registry.list_workflows()


@app.get("/api/v1/kernel/workflows/runs", response_model=list[WorkflowExecutionSummary])
async def list_workflow_runs() -> list[WorkflowExecutionSummary]:
    return registry.list_workflow_runs()


@app.post("/api/v1/kernel/workflows", response_model=WorkflowTemplate)
async def create_workflow(request: WorkflowCreateRequest) -> WorkflowTemplate:
    referenced_task_ids = [step.task_id for step in request.steps] if request.steps else request.task_ids
    if not referenced_task_ids:
        raise HTTPException(status_code=400, detail="Workflow must reference at least one task")

    missing_tasks = [task_id for task_id in referenced_task_ids if registry.get_task(task_id) is None]
    if missing_tasks:
        raise HTTPException(status_code=404, detail=f"Tasks not found for workflow: {', '.join(missing_tasks)}")
    try:
        workflow = registry.create_workflow(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await persist_runtime_state()
    logger.info("Registered kernel workflow", extra={"workflow_id": workflow.workflow_id, "name": workflow.name})
    try:
        await publish_runtime_snapshot()
    except Exception:
        logger.info("Realtime dashboard unavailable during workflow registration publish", extra={"workflow_id": workflow.workflow_id})
    return workflow


@app.get("/api/v1/kernel/workflows/{workflow_id}", response_model=WorkflowTemplate)
async def get_workflow(workflow_id: str) -> WorkflowTemplate:
    workflow = registry.get_workflow(workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail=f"Workflow '{workflow_id}' not found")
    return workflow


@app.post("/api/v1/kernel/workflows/{workflow_id}/runs", response_model=WorkflowRunResult)
async def run_workflow(workflow_id: str, request: WorkflowRunRequest) -> WorkflowRunResult:
    workflow = registry.get_workflow(workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail=f"Workflow '{workflow_id}' not found")
    result = await orchestrator.run_workflow(registry, workflow, request)
    logger.info(
        "Completed workflow run",
        extra={
            "workflow_id": result.workflow_execution.workflow_id,
            "execution_id": result.workflow_execution.execution_id,
            "status": result.workflow_execution.status.value,
        },
    )
    try:
        await publish_runtime_snapshot()
    except Exception:
        logger.info("Realtime dashboard unavailable during workflow run publish", extra={"workflow_id": workflow.workflow_id})
    return result
