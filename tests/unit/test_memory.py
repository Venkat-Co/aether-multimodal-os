from datetime import UTC, datetime

from aether_core.models import MemoryNode, MemoryType
from aether_core.vector import deterministic_embedding
from services.memory.app.graph import MemoryGraph


import pytest


@pytest.mark.asyncio
async def test_memory_query_and_causal_linking() -> None:
    graph = MemoryGraph()
    base_embedding = deterministic_embedding({"memory": "temperature spike"})
    parent = MemoryNode(
        memory_type=MemoryType.episodic,
        content={"description": "Sensor drift"},
        embedding=base_embedding,
        timestamp=datetime.now(tz=UTC),
    )
    child = MemoryNode(
        memory_type=MemoryType.working,
        content={"description": "Temperature exceeded threshold"},
        embedding=base_embedding,
        timestamp=datetime.now(tz=UTC),
    )

    await graph.store_memory(parent)
    await graph.store_memory(child)
    await graph.link_causal(parent.node_id, child.node_id, 0.9)
    results = await graph.query(base_embedding, top_k=1)
    chain = await graph.extract_causal_chain(child.node_id)

    assert results
    assert chain[0].node_id == child.node_id
    assert parent.node_id in child.causal_parents
