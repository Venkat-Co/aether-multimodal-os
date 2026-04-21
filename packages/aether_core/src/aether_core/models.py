from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


EMBEDDING_DIMENSION = 768


def utc_now() -> datetime:
    return datetime.now(tz=UTC)


class ModalityType(str, Enum):
    vision = "vision"
    audio = "audio"
    text = "text"
    sensor = "sensor"
    robotic = "robotic"


class MemoryType(str, Enum):
    episodic = "episodic"
    semantic = "semantic"
    procedural = "procedural"
    working = "working"


class ReasoningMode(str, Enum):
    reactive = "reactive"
    proactive = "proactive"
    predictive = "predictive"
    causal = "causal"


class RiskLevel(str, Enum):
    low = "LOW"
    medium = "MEDIUM"
    high = "HIGH"
    critical = "CRITICAL"


class GovernanceAction(str, Enum):
    allow = "ALLOW"
    block = "BLOCK"
    escalate = "ESCALATE"
    monitor = "MONITOR"


class ActionType(str, Enum):
    api = "api"
    robotic = "robotic"
    human = "human"
    notify = "notify"
    rollback = "rollback"


class StreamHealth(BaseModel):
    source_id: str
    healthy: bool
    latency_ms: float = 0.0
    dropped_packets: int = 0
    detail: str | None = None


class EventEnvelope(BaseModel):
    event_id: str = Field(default_factory=lambda: f"evtbus_{uuid4().hex[:12]}")
    topic: str
    source: str
    payload: dict[str, Any]
    headers: dict[str, str] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=utc_now)


class StreamPacket(BaseModel):
    packet_id: str = Field(default_factory=lambda: str(uuid4()))
    modality: ModalityType
    timestamp: datetime = Field(default_factory=utc_now)
    source_id: str
    raw_data: dict[str, Any] = Field(default_factory=dict)
    embedding: list[float] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    confidence: float = 0.95
    perceptual_hash: str = Field(default_factory=lambda: uuid4().hex[:8])

    @field_validator("embedding")
    @classmethod
    def validate_embedding(cls, value: list[float]) -> list[float]:
        if value and len(value) != EMBEDDING_DIMENSION:
            raise ValueError(f"Embedding must be {EMBEDDING_DIMENSION}-dimensional")
        return value


class SpatialBounds(BaseModel):
    center: list[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0])
    radius_m: float = 0.0


class FusedEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: f"evt_{uuid4().hex[:8]}")
    timestamp: datetime = Field(default_factory=utc_now)
    window_center: datetime = Field(default_factory=utc_now)
    modalities: list[ModalityType]
    fusion_vector: list[float]
    semantic_summary: str
    source_packets: list[str]
    confidence: float
    spatial_bounds: SpatialBounds = Field(default_factory=SpatialBounds)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("fusion_vector")
    @classmethod
    def validate_fusion_vector(cls, value: list[float]) -> list[float]:
        if len(value) != EMBEDDING_DIMENSION:
            raise ValueError(f"Fusion vector must be {EMBEDDING_DIMENSION}-dimensional")
        return value


class MemoryNode(BaseModel):
    node_id: str = Field(default_factory=lambda: f"mem_{uuid4().hex[:8]}")
    memory_type: MemoryType
    content: dict[str, Any]
    embedding: list[float]
    timestamp: datetime = Field(default_factory=utc_now)
    location: list[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0])
    confidence: float = 1.0
    importance_score: float = 0.5
    access_count: int = 0
    last_accessed: datetime = Field(default_factory=utc_now)
    causal_parents: list[str] = Field(default_factory=list)
    causal_children: list[str] = Field(default_factory=list)
    related_nodes: list[str] = Field(default_factory=list)

    @field_validator("embedding")
    @classmethod
    def validate_node_embedding(cls, value: list[float]) -> list[float]:
        if len(value) != EMBEDDING_DIMENSION:
            raise ValueError(f"Memory embedding must be {EMBEDDING_DIMENSION}-dimensional")
        return value


class CauseCandidate(BaseModel):
    cause_id: str
    description: str
    score: float
    confidence_interval: list[float] = Field(default_factory=lambda: [0.0, 0.0])


class Prediction(BaseModel):
    horizon_step: int
    predicted_state: dict[str, Any]
    lower_bound: float
    upper_bound: float
    confidence: float


class ReasoningRequest(BaseModel):
    query: str
    current_state: dict[str, Any] = Field(default_factory=dict)
    mode: ReasoningMode
    history: list[dict[str, Any]] = Field(default_factory=list)
    horizon: int = 3


class ReasoningResult(BaseModel):
    reasoning_id: str = Field(default_factory=lambda: f"rsn_{uuid4().hex[:8]}")
    mode: ReasoningMode
    summary: str
    causes: list[CauseCandidate] = Field(default_factory=list)
    predictions: list[Prediction] = Field(default_factory=list)
    action_plan: list[dict[str, Any]] = Field(default_factory=list)
    confidence: float = 0.75
    timestamp: datetime = Field(default_factory=utc_now)


class GovernanceRule(BaseModel):
    rule_id: str
    name: str
    condition: dict[str, Any]
    action: GovernanceAction
    risk_level: RiskLevel
    description: str


class GovernanceDecision(BaseModel):
    decision_id: str = Field(default_factory=lambda: f"gov_{utc_now().strftime('%Y%m%d%H%M%S')}_{uuid4().hex[:8]}")
    timestamp: datetime = Field(default_factory=utc_now)
    rule_id: str
    action_taken: GovernanceAction
    risk_level: RiskLevel
    context_hash: str
    reasoning: str
    confidence: float
    approved: bool = False
    override_reason: str | None = None
    audit_trail: list[dict[str, Any]] = Field(default_factory=list)


class ActionRequest(BaseModel):
    action_type: ActionType
    target: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    requires_approval: bool = False
    idempotency_key: str = Field(default_factory=lambda: uuid4().hex)
    reversibility: str = "partial"
    criticality: float = 0.0


class ActionResult(BaseModel):
    action_id: str = Field(default_factory=lambda: f"act_{uuid4().hex[:8]}")
    status: str
    target: str
    action_type: ActionType
    idempotency_key: str
    detail: str
    rollback_reference: str | None = None
    timestamp: datetime = Field(default_factory=utc_now)
