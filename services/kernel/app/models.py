from __future__ import annotations

from datetime import UTC, datetime
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

