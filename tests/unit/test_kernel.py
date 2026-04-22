import pytest

from aether_core.event_bus import InMemoryEventBus
from services.kernel.app.models import (
    AgentCreateRequest,
    AgentRunRequest,
    KernelPipelineRequest,
    StreamSpec,
    TaskCreateRequest,
    TaskRunRequest,
    ToolBinding,
)
from services.kernel.app.orchestrator import KernelOrchestrator
from services.kernel.app.registry import AgentRegistry, build_default_agents, build_default_tasks, build_default_tools


class FakeClients:
    def __init__(self) -> None:
        self.published: list[tuple[str, dict]] = []
        self.ingest_calls = 0
        self.buffer_checks = 0

    async def register_stream(self, payload):
        return {"status": "registered", **payload}

    async def emit_packet(self, source_id):
        modality_map = {
            "camera_001": "vision",
            "mic_001": "audio",
            "sensor_001": "sensor",
            "log_001": "text",
        }
        raw_map = {
            "camera_001": {"frame_index": 1},
            "mic_001": {"sample_index": 1},
            "sensor_001": {"temperature_c": 88.5, "vibration_g": 1.4},
            "log_001": {"message": "thermal anomaly detected"},
        }
        return {
            "packet_id": f"pkt_{source_id}",
            "source_id": source_id,
            "modality": modality_map[source_id],
            "timestamp": "2026-04-21T12:00:00Z",
            "raw_data": raw_map[source_id],
            "embedding": [0.1] * 768,
            "confidence": 0.95,
            "metadata": {},
            "perceptual_hash": source_id[:8],
        }

    async def ingest_fusion_packet(self, packet):
        self.ingest_calls += 1
        return None

    async def fuse_window(self, window_center):
        return {
            "event_id": "evt_001",
            "timestamp": window_center,
            "window_center": window_center,
            "modalities": ["vision", "audio", "sensor", "text"],
            "fusion_vector": [0.2] * 768,
            "semantic_summary": "temperature spike with operator concern",
            "source_packets": ["pkt_camera_001", "pkt_mic_001"],
            "confidence": 0.92,
            "spatial_bounds": {"center": [10.5, 20.3, 0.0], "radius_m": 5.0},
        }

    async def store_memory(self, payload):
        return {"node_id": "mem_001", **payload}

    async def reason(self, payload):
        return {
            "reasoning_id": "rsn_001",
            "mode": payload["mode"],
            "summary": "proactive trigger fired",
            "action_plan": [{"type": "notify"}],
            "predictions": [],
            "causes": [],
            "confidence": 0.88,
        }

    async def evaluate_governance(self, payload):
        return {
            "decision_id": "gov_001",
            "rule_id": "DEFAULT_ALLOW",
            "action_taken": "ALLOW",
            "risk_level": "LOW",
            "reasoning": "no blocking rule matched",
            "confidence": 0.8,
        }

    async def dispatch_action(self, payload):
        return {"status": "executed", "result": {"target": payload["target"]}}

    async def publish(self, topic, payload):
        self.published.append((topic, payload))

    async def fusion_buffer_state(self):
        self.buffer_checks += 1
        return {"buffered_packets": 4}


class DistributedInMemoryEventBus(InMemoryEventBus):
    distributed = True


@pytest.mark.asyncio
async def test_kernel_orchestrates_end_to_end_pipeline() -> None:
    clients = FakeClients()
    bus = InMemoryEventBus()
    await bus.connect()
    orchestrator = KernelOrchestrator(clients, bus, "aether-kernel")  # type: ignore[arg-type]

    result = await orchestrator.run_pipeline(KernelPipelineRequest())

    assert len(result.registered_streams) == 4
    assert len(result.packets) == 4
    assert result.fused_event["event_id"] == "evt_001"
    assert result.memory_node["node_id"] == "mem_001"
    assert result.reasoning_result["mode"] == "proactive"
    assert result.governance_decision["action_taken"] == "ALLOW"
    assert result.action_result is not None
    assert any(topic == "fusion" for topic, _ in clients.published)
    await bus.close()


@pytest.mark.asyncio
async def test_kernel_uses_bus_driven_fusion_when_distributed() -> None:
    clients = FakeClients()
    bus = DistributedInMemoryEventBus()
    await bus.connect()
    orchestrator = KernelOrchestrator(clients, bus, "aether-kernel")  # type: ignore[arg-type]

    result = await orchestrator.run_pipeline(KernelPipelineRequest())

    assert result.fused_event["event_id"] == "evt_001"
    assert clients.ingest_calls == 0
    assert clients.buffer_checks >= 1
    await bus.close()


@pytest.mark.asyncio
async def test_kernel_runs_seeded_agent_through_pipeline() -> None:
    clients = FakeClients()
    bus = InMemoryEventBus()
    registry = AgentRegistry(
        seed_agents=build_default_agents(),
        seed_tools=build_default_tools(),
        seed_tasks=build_default_tasks(),
    )
    await bus.connect()
    orchestrator = KernelOrchestrator(clients, bus, "aether-kernel")  # type: ignore[arg-type]

    agent = registry.get_agent("ops_supervisor")
    assert agent is not None

    result = await orchestrator.run_agent(registry, agent, AgentRunRequest())

    assert result.agent_id == "ops_supervisor"
    assert result.status.value == "completed"
    assert result.governance_action == "ALLOW"
    assert result.pipeline_result.action_result is not None
    assert len(registry.list_runs()) == 1
    await bus.close()


def test_agent_registry_builds_pipeline_request_from_definition() -> None:
    registry = AgentRegistry()
    agent = registry.create_agent(
        AgentCreateRequest(
            agent_id="safety_watch",
            name="Safety Watch",
            description="Monitors safety signals.",
            goal="Detect risk early and notify safety operations.",
            default_query="Assess live safety conditions.",
            streams=[
                StreamSpec(source_id="camera_001", modality="vision"),
                StreamSpec(source_id="sensor_001", modality="sensor"),
            ],
            tools=[
                ToolBinding(
                    tool_id="notify_safety",
                    name="Safety Notification",
                    description="Notify safety operations.",
                    target="safety_operations",
                    parameters={"channel": "safety"},
                    criticality=0.4,
                )
            ],
            tags=["safety"],
        )
    )

    request = registry.build_pipeline_request(
        agent,
        AgentRunRequest(query="Explain the current safety state.", packets_per_stream=2),
    )

    assert request.query == "Explain the current safety state."
    assert request.packets_per_stream == 2
    assert request.streams[0].source_id == "camera_001"
    assert request.action_template.target == "safety_operations"


def test_task_registry_builds_agent_request_from_task_template() -> None:
    registry = AgentRegistry(
        seed_agents=build_default_agents(),
        seed_tools=build_default_tools(),
    )
    task = registry.create_task(
        TaskCreateRequest(
            task_id="check_safety_lane",
            name="Check Safety Lane",
            description="Inspect live safety signals.",
            agent_id="ops_supervisor",
            query="Assess safety lane conditions and escalate risk patterns.",
            tool_id="notify_supervisor",
            packets_per_stream=2,
            tags=["safety"],
        )
    )

    tool = registry.get_tool("notify_supervisor")
    request = registry.build_agent_run_request_from_task(
        task,
        TaskRunRequest(query="Explain the current safety deviation."),
        tool,
    )

    assert request.query == "Explain the current safety deviation."
    assert request.packets_per_stream == 2
    assert request.action_template_override is not None
    assert request.action_template_override.target == "shift_supervisor"


@pytest.mark.asyncio
async def test_kernel_runs_seeded_task_through_task_state_machine() -> None:
    clients = FakeClients()
    bus = InMemoryEventBus()
    registry = AgentRegistry(
        seed_agents=build_default_agents(),
        seed_tools=build_default_tools(),
        seed_tasks=build_default_tasks(),
    )
    await bus.connect()
    orchestrator = KernelOrchestrator(clients, bus, "aether-kernel")  # type: ignore[arg-type]

    task = registry.get_task("watch_line_three")
    assert task is not None

    result = await orchestrator.run_task(registry, task, TaskRunRequest())

    assert result.task_execution.task_id == "watch_line_three"
    assert result.task_execution.status.value == "completed"
    assert result.task_execution.governance_action == "ALLOW"
    assert result.agent_run is not None
    assert result.agent_run.agent_id == "ops_supervisor"
    assert len(result.task_execution.state_history) >= 3
    assert registry.list_task_runs()[0].execution_id == result.task_execution.execution_id
    await bus.close()
