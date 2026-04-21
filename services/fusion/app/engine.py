from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from aether_core.models import FusedEvent, ModalityType, SpatialBounds, StreamPacket
from aether_core.vector import cosine_similarity, deterministic_embedding


@dataclass
class AlignmentMetrics:
    temporal_spread_ms: float
    average_confidence: float
    distinct_modalities: int
    quality_score: float


class MultiModalFusionEngine:
    def __init__(self, window_seconds: int = 5, temporal_tolerance_ms: int = 100) -> None:
        self.window_seconds = window_seconds
        self.temporal_tolerance_ms = temporal_tolerance_ms
        self.packet_buffer: list[StreamPacket] = []

    def ingest(self, packet: StreamPacket) -> None:
        self.packet_buffer.append(packet)
        cutoff = datetime.now(tz=UTC) - timedelta(seconds=self.window_seconds * 3)
        self.packet_buffer = [item for item in self.packet_buffer if item.timestamp >= cutoff]

    def _deduplicate_packets(self, packets: list[StreamPacket]) -> list[StreamPacket]:
        deduplicated: dict[str, StreamPacket] = {}
        for packet in packets:
            current = deduplicated.get(packet.perceptual_hash)
            if current is None or packet.confidence > current.confidence:
                deduplicated[packet.perceptual_hash] = packet
        return list(deduplicated.values())

    def _select_window(self, window_center: datetime) -> list[StreamPacket]:
        half_window = timedelta(seconds=self.window_seconds / 2)
        packets = [
            packet
            for packet in self.packet_buffer
            if abs((packet.timestamp - window_center).total_seconds()) <= half_window.total_seconds()
        ]
        return self._deduplicate_packets(packets)

    def _temporal_alignment(self, packets: list[StreamPacket], window_center: datetime) -> AlignmentMetrics:
        if not packets:
            return AlignmentMetrics(0.0, 0.0, 0, 0.0)
        spread = max(abs((packet.timestamp - window_center).total_seconds() * 1000) for packet in packets)
        average_confidence = sum(packet.confidence for packet in packets) / len(packets)
        modality_count = len({packet.modality for packet in packets})
        alignment_penalty = min(spread / max(self.temporal_tolerance_ms, 1), 1.0)
        quality_score = max(0.0, (average_confidence * 0.6) + (modality_count / 5.0 * 0.4) - (alignment_penalty * 0.3))
        return AlignmentMetrics(spread, average_confidence, modality_count, min(quality_score, 1.0))

    def _cross_attention_weights(self, packets: list[StreamPacket]) -> list[float]:
        if not packets:
            return []
        scores: list[float] = []
        for packet in packets:
            similarity_total = 0.0
            for other in packets:
                if other.packet_id == packet.packet_id:
                    continue
                similarity_total += cosine_similarity(packet.embedding, other.embedding)
            normalized = (similarity_total / max(len(packets) - 1, 1) + 1) / 2
            scores.append(max(normalized, 0.05))
        total = sum(scores) or 1.0
        return [score / total for score in scores]

    def _semantic_summary(self, packets: list[StreamPacket]) -> str:
        grouped: dict[ModalityType, list[str]] = defaultdict(list)
        for packet in packets:
            grouped[packet.modality].append(str(packet.raw_data))
        fragments = []
        for modality, items in grouped.items():
            fragments.append(f"{modality.value}: {items[0]}")
        return " | ".join(fragments)

    def _spatial_bounds(self, packets: list[StreamPacket]) -> SpatialBounds:
        sensor_packet = next((packet for packet in packets if packet.modality == ModalityType.sensor), None)
        if sensor_packet:
            coords = sensor_packet.metadata.get("location", [10.5, 20.3, 0.0])
            return SpatialBounds(center=coords, radius_m=5.0)
        return SpatialBounds(center=[0.0, 0.0, 0.0], radius_m=0.0)

    def fuse_window(self, window_center: datetime | None = None) -> FusedEvent:
        window_center = window_center or datetime.now(tz=UTC)
        packets = self._select_window(window_center)
        if not packets:
            raise ValueError("No packets available in the requested fusion window")
        alignment = self._temporal_alignment(packets, window_center)
        weights = self._cross_attention_weights(packets)
        fusion_vector = [0.0] * 768
        for weight, packet in zip(weights, packets, strict=False):
            for index, value in enumerate(packet.embedding):
                fusion_vector[index] += weight * value
        if all(value == 0.0 for value in fusion_vector):
            fusion_vector = deterministic_embedding(
                {"window_center": window_center.isoformat(), "packets": [packet.packet_id for packet in packets]}
            )
        return FusedEvent(
            timestamp=datetime.now(tz=UTC),
            window_center=window_center,
            modalities=sorted({packet.modality for packet in packets}, key=lambda item: item.value),
            fusion_vector=fusion_vector,
            semantic_summary=self._semantic_summary(packets),
            source_packets=[packet.packet_id for packet in packets],
            confidence=alignment.quality_score,
            spatial_bounds=self._spatial_bounds(packets),
            metadata={
                "temporal_spread_ms": alignment.temporal_spread_ms,
                "average_confidence": alignment.average_confidence,
                "distinct_modalities": alignment.distinct_modalities,
            },
        )

