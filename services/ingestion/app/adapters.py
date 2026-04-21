from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any

from aether_core.models import ModalityType, StreamHealth, StreamPacket
from aether_core.vector import deterministic_embedding


class StreamAdapter(ABC):
    @abstractmethod
    async def connect(self, source_config: dict[str, Any]) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def read_packet(self) -> StreamPacket:
        raise NotImplementedError

    @abstractmethod
    async def health_check(self) -> StreamHealth:
        raise NotImplementedError

    @property
    @abstractmethod
    def modality(self) -> ModalityType:
        raise NotImplementedError


class BaseSyntheticStreamAdapter(StreamAdapter):
    modality_value: ModalityType

    def __init__(self, source_id: str) -> None:
        self.source_id = source_id
        self.connected = False
        self.config: dict[str, Any] = {}
        self.packet_counter = 0

    @property
    def modality(self) -> ModalityType:
        return self.modality_value

    async def connect(self, source_config: dict[str, Any]) -> bool:
        self.config = source_config
        self.connected = True
        return True

    async def read_packet(self) -> StreamPacket:
        if not self.connected:
            raise RuntimeError(f"{self.source_id} is not connected")
        self.packet_counter += 1
        payload = self._build_payload()
        now = datetime.now(tz=UTC)
        return StreamPacket(
            modality=self.modality,
            source_id=self.source_id,
            timestamp=now,
            raw_data=payload,
            metadata=self._build_metadata(),
            embedding=deterministic_embedding({"source": self.source_id, "payload": payload, "ts": now.isoformat()}),
            confidence=0.95,
        )

    async def health_check(self) -> StreamHealth:
        return StreamHealth(
            source_id=self.source_id,
            healthy=self.connected,
            latency_ms=float(self.config.get("latency_ms", 25.0)),
            dropped_packets=0,
            detail=f"{self.modality.value} adapter healthy",
        )

    @abstractmethod
    def _build_payload(self) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def _build_metadata(self) -> dict[str, Any]:
        raise NotImplementedError


class VideoStreamAdapter(BaseSyntheticStreamAdapter):
    modality_value = ModalityType.vision

    def _build_payload(self) -> dict[str, Any]:
        return {
            "frame_index": self.packet_counter,
            "objects": ["operator", "assembly_line", "temperature_gauge"],
            "resolution": self.config.get("resolution", "3840x2160"),
        }

    def _build_metadata(self) -> dict[str, Any]:
        return {
            "fps": self.config.get("fps", 30),
            "codec": self.config.get("codec", "h265"),
            "transport": self.config.get("transport", "rtsp"),
        }


class AudioStreamAdapter(BaseSyntheticStreamAdapter):
    modality_value = ModalityType.audio

    def _build_payload(self) -> dict[str, Any]:
        return {
            "sample_index": self.packet_counter,
            "transcript": "operator reports abnormal vibration increasing near line three",
            "speaker": self.config.get("speaker", "operator_001"),
        }

    def _build_metadata(self) -> dict[str, Any]:
        return {
            "sample_rate_hz": self.config.get("sample_rate_hz", 16000),
            "encoding": self.config.get("encoding", "pcm16"),
            "diarization": True,
        }


class TextStreamAdapter(BaseSyntheticStreamAdapter):
    modality_value = ModalityType.text

    def _build_payload(self) -> dict[str, Any]:
        return {
            "message": "maintenance log indicates recurring thermal anomaly near assembly line 3",
            "channel": self.config.get("channel", "kafka"),
        }

    def _build_metadata(self) -> dict[str, Any]:
        return {"encoding": "utf-8", "source_type": self.config.get("source_type", "log")}


class SensorStreamAdapter(BaseSyntheticStreamAdapter):
    modality_value = ModalityType.sensor

    def _build_payload(self) -> dict[str, Any]:
        return {
            "temperature_c": 87.5 + (self.packet_counter % 5),
            "vibration_g": 1.2 + (self.packet_counter * 0.05),
            "pressure_kpa": 210.0,
        }

    def _build_metadata(self) -> dict[str, Any]:
        return {
            "protocol": self.config.get("protocol", "mqtt"),
            "schema": "structured-json",
            "site": self.config.get("site", "factory-alpha"),
        }


class RoboticStreamAdapter(BaseSyntheticStreamAdapter):
    modality_value = ModalityType.robotic

    def _build_payload(self) -> dict[str, Any]:
        return {
            "joint_states": [0.4, -1.2, 0.8, 0.1],
            "battery_pct": 92,
            "camera_status": "nominal",
        }

    def _build_metadata(self) -> dict[str, Any]:
        return {"bridge": self.config.get("bridge", "ros2"), "frame": "robot_base"}


ADAPTERS: dict[ModalityType, type[StreamAdapter]] = {
    ModalityType.vision: VideoStreamAdapter,
    ModalityType.audio: AudioStreamAdapter,
    ModalityType.text: TextStreamAdapter,
    ModalityType.sensor: SensorStreamAdapter,
    ModalityType.robotic: RoboticStreamAdapter,
}


class StreamRegistry:
    def __init__(self) -> None:
        self._adapters: dict[str, StreamAdapter] = {}
        self._packets: dict[str, list[StreamPacket]] = {}
        self._lock = asyncio.Lock()

    async def register(self, source_id: str, modality: ModalityType, config: dict[str, Any]) -> StreamAdapter:
        async with self._lock:
            adapter_cls = ADAPTERS[modality]
            adapter = adapter_cls(source_id)  # type: ignore[call-arg]
            await adapter.connect(config)
            self._adapters[source_id] = adapter
            self._packets[source_id] = []
            return adapter

    async def emit(self, source_id: str) -> StreamPacket:
        adapter = self._adapters[source_id]
        packet = await adapter.read_packet()
        self._packets[source_id].append(packet)
        self._packets[source_id] = self._packets[source_id][-100:]
        return packet

    async def health(self, source_id: str) -> StreamHealth:
        return await self._adapters[source_id].health_check()

    def list_streams(self) -> list[dict[str, Any]]:
        return [
            {"source_id": source_id, "modality": adapter.modality.value}
            for source_id, adapter in self._adapters.items()
        ]

    def recent_packets(self, source_id: str) -> list[StreamPacket]:
        return self._packets.get(source_id, [])

