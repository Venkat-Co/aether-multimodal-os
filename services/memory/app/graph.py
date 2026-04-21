from __future__ import annotations

from typing import Any

from aether_core.config import AetherSettings
from aether_core.models import MemoryNode, MemoryType

from .repository import DurableMemoryRepository, InMemoryMemoryRepository


class MemoryGraph:
    def __init__(self, settings: AetherSettings | None = None) -> None:
        self.memory_store = InMemoryMemoryRepository()
        self.durable_store = DurableMemoryRepository(settings) if settings is not None else None

    @property
    def update_log(self) -> list[dict[str, Any]]:
        return self.memory_store.update_log

    async def initialize(self) -> None:
        if self.durable_store is not None:
            await self.durable_store.initialize()

    async def close(self) -> None:
        if self.durable_store is not None:
            await self.durable_store.close()

    def backend_status(self) -> dict[str, Any]:
        if self.durable_store is None:
            return {
                "mode": "in-memory",
                "postgres": {"enabled": False, "detail": "disabled"},
                "neo4j": {"enabled": False, "detail": "disabled"},
            }
        return {"mode": "hybrid", **self.durable_store.backend_status}

    async def store_memory(self, node: MemoryNode) -> MemoryNode:
        await self.memory_store.store_memory(node)
        if self.durable_store is not None:
            await self.durable_store.store_memory(node)
        return node

    async def query(
        self,
        query_embedding: list[float],
        time_range: dict[str, datetime] | None = None,
        location: dict[str, float] | None = None,
        memory_types: list[MemoryType] | None = None,
        top_k: int = 10,
    ) -> list[MemoryNode]:
        if self.durable_store is not None:
            persistent_results = await self.durable_store.query(
                query_embedding=query_embedding,
                time_range=time_range,
                location=location,
                memory_types=memory_types,
                top_k=top_k,
            )
            if persistent_results is not None:
                return persistent_results
        return await self.memory_store.query(query_embedding, time_range, location, memory_types, top_k)

    async def link_causal(self, parent_id: str, child_id: str, strength: float = 0.5) -> None:
        await self.memory_store.link_causal(parent_id, child_id, strength)
        if self.durable_store is not None:
            await self.durable_store.link_causal(parent_id, child_id, strength)

    async def extract_causal_chain(self, node_id: str, depth: int = 5) -> list[MemoryNode]:
        if self.durable_store is not None:
            persistent_chain = await self.durable_store.extract_causal_chain(node_id, depth)
            if persistent_chain is not None:
                return persistent_chain
        return await self.memory_store.extract_causal_chain(node_id, depth)

    async def consolidate(self) -> dict[str, int]:
        in_memory = await self.memory_store.consolidate()
        if self.durable_store is not None:
            durable = await self.durable_store.consolidate()
            return {"promoted": max(in_memory["promoted"], durable["promoted"]), "forgotten": max(in_memory["forgotten"], durable["forgotten"])}
        return in_memory
