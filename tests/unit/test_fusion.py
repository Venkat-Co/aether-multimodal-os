from datetime import UTC, datetime

from aether_core.models import ModalityType, StreamPacket
from aether_core.vector import deterministic_embedding
from services.fusion.app.engine import MultiModalFusionEngine


def make_packet(modality: ModalityType, source_id: str) -> StreamPacket:
    now = datetime.now(tz=UTC)
    return StreamPacket(
        modality=modality,
        source_id=source_id,
        timestamp=now,
        raw_data={"source": source_id},
        embedding=deterministic_embedding({"source": source_id, "modality": modality.value, "ts": now.isoformat()}),
    )


def test_fusion_generates_multimodal_event() -> None:
    engine = MultiModalFusionEngine()
    engine.ingest(make_packet(ModalityType.vision, "camera_1"))
    engine.ingest(make_packet(ModalityType.audio, "mic_1"))
    engine.ingest(make_packet(ModalityType.sensor, "sensor_1"))

    fused = engine.fuse_window()

    assert fused.confidence > 0
    assert len(fused.fusion_vector) == 768
    assert set(fused.modalities) == {ModalityType.vision, ModalityType.audio, ModalityType.sensor}

