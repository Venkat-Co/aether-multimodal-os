from __future__ import annotations

from typing import Any

import httpx

from aether_core.config import AetherSettings


class AetherServiceClients:
    def __init__(self, settings: AetherSettings) -> None:
        timeout = httpx.Timeout(10.0, connect=5.0)
        self.ingestion = httpx.AsyncClient(base_url=settings.ingestion_service_url, timeout=timeout)
        self.fusion = httpx.AsyncClient(base_url=settings.fusion_service_url, timeout=timeout)
        self.memory = httpx.AsyncClient(base_url=settings.memory_service_url, timeout=timeout)
        self.reasoning = httpx.AsyncClient(base_url=settings.reasoning_service_url, timeout=timeout)
        self.governance = httpx.AsyncClient(base_url=settings.governance_service_url, timeout=timeout)
        self.action = httpx.AsyncClient(base_url=settings.action_service_url, timeout=timeout)
        self.realtime = httpx.AsyncClient(base_url=settings.realtime_service_url, timeout=timeout)

    async def close(self) -> None:
        await self.ingestion.aclose()
        await self.fusion.aclose()
        await self.memory.aclose()
        await self.reasoning.aclose()
        await self.governance.aclose()
        await self.action.aclose()
        await self.realtime.aclose()

    async def register_stream(self, payload: dict[str, Any]) -> dict[str, Any]:
        response = await self.ingestion.post("/api/v1/streams", json=payload)
        response.raise_for_status()
        return response.json()

    async def emit_packet(self, source_id: str) -> dict[str, Any]:
        response = await self.ingestion.post(f"/api/v1/streams/{source_id}/emit")
        response.raise_for_status()
        return response.json()

    async def ingest_fusion_packet(self, packet: dict[str, Any]) -> None:
        response = await self.fusion.post("/api/v1/fusion/ingest", json=packet)
        response.raise_for_status()

    async def fuse_window(self, window_center: str) -> dict[str, Any]:
        response = await self.fusion.post("/api/v1/fusion/window", json={"window_center": window_center})
        response.raise_for_status()
        return response.json()

    async def fusion_buffer_state(self) -> dict[str, int]:
        response = await self.fusion.get("/api/v1/fusion/buffer")
        response.raise_for_status()
        return response.json()

    async def store_memory(self, payload: dict[str, Any]) -> dict[str, Any]:
        response = await self.memory.post("/api/v1/memory/store", json=payload)
        response.raise_for_status()
        return response.json()

    async def reason(self, payload: dict[str, Any]) -> dict[str, Any]:
        response = await self.reasoning.post("/api/v1/reason", json=payload)
        response.raise_for_status()
        return response.json()

    async def evaluate_governance(self, payload: dict[str, Any]) -> dict[str, Any]:
        response = await self.governance.post("/api/v1/governance/evaluate", json=payload)
        response.raise_for_status()
        return response.json()

    async def dispatch_action(self, payload: dict[str, Any]) -> dict[str, Any]:
        response = await self.action.post("/api/v1/actions/dispatch", json=payload)
        response.raise_for_status()
        return response.json()

    async def publish(self, topic: str, payload: dict[str, Any]) -> None:
        response = await self.realtime.post(f"/api/v1/realtime/publish/{topic}", json=payload)
        response.raise_for_status()
