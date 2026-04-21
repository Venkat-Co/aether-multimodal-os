from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from math import sqrt
from typing import Any

try:
    import asyncpg
except Exception:  # pragma: no cover - optional persistence dependency
    asyncpg = None  # type: ignore[assignment]

try:
    from neo4j import AsyncGraphDatabase
except Exception:  # pragma: no cover - optional persistence dependency
    AsyncGraphDatabase = None  # type: ignore[assignment]

from aether_core.config import AetherSettings
from aether_core.models import MemoryNode, MemoryType
from aether_core.vector import cosine_similarity


def euclidean_distance(left: list[float], right: list[float]) -> float:
    return sqrt(sum((a - b) ** 2 for a, b in zip(left, right, strict=False)))


class InMemoryMemoryRepository:
    def __init__(self) -> None:
        self.nodes: dict[str, MemoryNode] = {}
        self.relationships: dict[str, dict[str, dict[str, float]]] = defaultdict(lambda: defaultdict(dict))
        self.update_log: list[dict[str, Any]] = []

    async def store_memory(self, node: MemoryNode) -> MemoryNode:
        self.nodes[node.node_id] = node
        self.update_log.append({"event": "store", "node_id": node.node_id, "timestamp": datetime.now(tz=UTC).isoformat()})
        return node

    async def query(
        self,
        query_embedding: list[float],
        time_range: dict[str, datetime] | None = None,
        location: dict[str, float] | None = None,
        memory_types: list[MemoryType] | None = None,
        top_k: int = 10,
    ) -> list[MemoryNode]:
        results: list[tuple[float, MemoryNode]] = []
        for node in self.nodes.values():
            if memory_types and node.memory_type not in memory_types:
                continue
            if time_range and not (time_range["start"] <= node.timestamp <= time_range["end"]):
                continue
            if location:
                target = [location["x"], location["y"], location["z"]]
                if euclidean_distance(node.location, target) > location["radius"]:
                    continue
            score = cosine_similarity(query_embedding, node.embedding)
            score += node.importance_score * 0.15
            recency_bonus = max(0.0, 1.0 - ((datetime.now(tz=UTC) - node.last_accessed).total_seconds() / 86400.0))
            score += recency_bonus * 0.05
            results.append((score, node))
        ranked = sorted(results, key=lambda item: item[0], reverse=True)[:top_k]
        for _, node in ranked:
            node.access_count += 1
            node.last_accessed = datetime.now(tz=UTC)
        return [node for _, node in ranked]

    async def link_causal(self, parent_id: str, child_id: str, strength: float = 0.5) -> None:
        parent = self.nodes[parent_id]
        child = self.nodes[child_id]
        if child_id not in parent.causal_children:
            parent.causal_children.append(child_id)
        if parent_id not in child.causal_parents:
            child.causal_parents.append(parent_id)
        self.relationships[parent_id]["CAUSED"][child_id] = strength
        self.update_log.append(
            {"event": "link", "parent_id": parent_id, "child_id": child_id, "strength": strength}
        )

    async def extract_causal_chain(self, node_id: str, depth: int = 5) -> list[MemoryNode]:
        visited: set[str] = set()
        ordered: list[MemoryNode] = []

        def visit(current_id: str, remaining_depth: int) -> None:
            if remaining_depth < 0 or current_id in visited or current_id not in self.nodes:
                return
            visited.add(current_id)
            ordered.append(self.nodes[current_id])
            for parent_id in self.nodes[current_id].causal_parents:
                visit(parent_id, remaining_depth - 1)

        visit(node_id, depth)
        return ordered

    async def consolidate(self) -> dict[str, int]:
        promoted = 0
        forgotten = 0
        now = datetime.now(tz=UTC)
        for node in list(self.nodes.values()):
            age = now - node.timestamp
            if node.memory_type == MemoryType.working and age >= timedelta(hours=1):
                node.memory_type = MemoryType.episodic
                promoted += 1
            if node.importance_score < 0.2 and node.access_count == 0 and age >= timedelta(hours=24):
                forgotten += 1
                del self.nodes[node.node_id]
        self.update_log.append({"event": "consolidate", "promoted": promoted, "forgotten": forgotten})
        return {"promoted": promoted, "forgotten": forgotten}


class DurableMemoryRepository:
    def __init__(self, settings: AetherSettings) -> None:
        self.settings = settings
        self.pg_pool: Any | None = None
        self.neo4j_driver = None
        self.vector_enabled = False
        self.backend_status: dict[str, Any] = {
            "postgres": {"enabled": False, "detail": "not-initialized"},
            "neo4j": {"enabled": False, "detail": "not-initialized"},
        }

    async def initialize(self) -> None:
        await self._initialize_postgres()
        await self._initialize_neo4j()

    async def close(self) -> None:
        if self.pg_pool is not None:
            await self.pg_pool.close()
            self.pg_pool = None
        if self.neo4j_driver is not None:
            await self.neo4j_driver.close()
            self.neo4j_driver = None

    async def _initialize_postgres(self) -> None:
        if asyncpg is None:
            self.backend_status["postgres"] = {"enabled": False, "detail": "asyncpg is not installed"}
            return
        last_error: Exception | None = None
        for attempt in range(1, max(self.settings.startup_retry_attempts, 1) + 1):
            try:
                self.pg_pool = await asyncpg.create_pool(self.settings.postgres_dsn, min_size=1, max_size=5)
                async with self.pg_pool.acquire() as connection:
                    try:
                        await connection.execute("CREATE EXTENSION IF NOT EXISTS vector")
                        self.vector_enabled = True
                    except Exception as exc:
                        self.backend_status["postgres"]["detail"] = f"connected without pgvector: {exc}"

                    await connection.execute(
                        """
                        CREATE TABLE IF NOT EXISTS memory_nodes (
                            node_id TEXT PRIMARY KEY,
                            memory_type TEXT NOT NULL,
                            content JSONB NOT NULL,
                            embedding_json JSONB NOT NULL,
                            timestamp TIMESTAMPTZ NOT NULL,
                            location DOUBLE PRECISION[] NOT NULL,
                            confidence DOUBLE PRECISION NOT NULL,
                            importance_score DOUBLE PRECISION NOT NULL,
                            access_count INTEGER NOT NULL,
                            last_accessed TIMESTAMPTZ NOT NULL,
                            causal_parents TEXT[] NOT NULL,
                            causal_children TEXT[] NOT NULL,
                            related_nodes TEXT[] NOT NULL
                        )
                        """
                    )
                    await connection.execute(
                        "CREATE INDEX IF NOT EXISTS memory_nodes_timestamp_idx ON memory_nodes (timestamp DESC)"
                    )
                    await connection.execute(
                        "CREATE INDEX IF NOT EXISTS memory_nodes_type_idx ON memory_nodes (memory_type)"
                    )
                    if self.vector_enabled:
                        await connection.execute(
                            "ALTER TABLE memory_nodes ADD COLUMN IF NOT EXISTS embedding_vector vector(768)"
                        )
                        await connection.execute(
                            """
                            CREATE INDEX IF NOT EXISTS memory_nodes_embedding_hnsw
                            ON memory_nodes USING hnsw (embedding_vector vector_cosine_ops)
                            """
                        )
                self.backend_status["postgres"] = {"enabled": True, "detail": "connected"}
                return
            except Exception as exc:
                last_error = exc
                self.pg_pool = None
                if attempt < self.settings.startup_retry_attempts:
                    await asyncio.sleep(self.settings.startup_retry_delay_seconds)
        self.backend_status["postgres"] = {"enabled": False, "detail": str(last_error)}

    async def _initialize_neo4j(self) -> None:
        if AsyncGraphDatabase is None:
            self.backend_status["neo4j"] = {"enabled": False, "detail": "neo4j driver is not installed"}
            return
        last_error: Exception | None = None
        for attempt in range(1, max(self.settings.startup_retry_attempts, 1) + 1):
            try:
                self.neo4j_driver = AsyncGraphDatabase.driver(
                    self.settings.neo4j_uri,
                    auth=(self.settings.neo4j_user, self.settings.neo4j_password),
                )
                await self.neo4j_driver.verify_connectivity()
                async with self.neo4j_driver.session() as session:
                    await session.run(
                        "CREATE CONSTRAINT memory_node_id IF NOT EXISTS FOR (m:Memory) REQUIRE m.node_id IS UNIQUE"
                    )
                self.backend_status["neo4j"] = {"enabled": True, "detail": "connected"}
                return
            except Exception as exc:
                last_error = exc
                self.neo4j_driver = None
                if attempt < self.settings.startup_retry_attempts:
                    await asyncio.sleep(self.settings.startup_retry_delay_seconds)
        self.backend_status["neo4j"] = {"enabled": False, "detail": str(last_error)}

    def _vector_literal(self, embedding: list[float]) -> str:
        return "[" + ",".join(f"{value:.8f}" for value in embedding) + "]"

    async def store_memory(self, node: MemoryNode) -> None:
        if self.pg_pool is not None:
            await self._store_postgres(node)
        if self.neo4j_driver is not None:
            await self._store_neo4j(node)

    async def _store_postgres(self, node: MemoryNode) -> None:
        assert self.pg_pool is not None
        async with self.pg_pool.acquire() as connection:
            if self.vector_enabled:
                await connection.execute(
                    """
                    INSERT INTO memory_nodes (
                        node_id, memory_type, content, embedding_json, embedding_vector, timestamp,
                        location, confidence, importance_score, access_count, last_accessed,
                        causal_parents, causal_children, related_nodes
                    ) VALUES (
                        $1, $2, $3::jsonb, $4::jsonb, $5::vector, $6,
                        $7, $8, $9, $10, $11, $12, $13, $14
                    )
                    ON CONFLICT (node_id) DO UPDATE SET
                        memory_type = EXCLUDED.memory_type,
                        content = EXCLUDED.content,
                        embedding_json = EXCLUDED.embedding_json,
                        embedding_vector = EXCLUDED.embedding_vector,
                        timestamp = EXCLUDED.timestamp,
                        location = EXCLUDED.location,
                        confidence = EXCLUDED.confidence,
                        importance_score = EXCLUDED.importance_score,
                        access_count = EXCLUDED.access_count,
                        last_accessed = EXCLUDED.last_accessed,
                        causal_parents = EXCLUDED.causal_parents,
                        causal_children = EXCLUDED.causal_children,
                        related_nodes = EXCLUDED.related_nodes
                    """,
                    node.node_id,
                    node.memory_type.value,
                    json.dumps(node.content),
                    json.dumps(node.embedding),
                    self._vector_literal(node.embedding),
                    node.timestamp,
                    node.location,
                    node.confidence,
                    node.importance_score,
                    node.access_count,
                    node.last_accessed,
                    node.causal_parents,
                    node.causal_children,
                    node.related_nodes,
                )
            else:
                await connection.execute(
                    """
                    INSERT INTO memory_nodes (
                        node_id, memory_type, content, embedding_json, timestamp,
                        location, confidence, importance_score, access_count, last_accessed,
                        causal_parents, causal_children, related_nodes
                    ) VALUES (
                        $1, $2, $3::jsonb, $4::jsonb, $5,
                        $6, $7, $8, $9, $10, $11, $12, $13
                    )
                    ON CONFLICT (node_id) DO UPDATE SET
                        memory_type = EXCLUDED.memory_type,
                        content = EXCLUDED.content,
                        embedding_json = EXCLUDED.embedding_json,
                        timestamp = EXCLUDED.timestamp,
                        location = EXCLUDED.location,
                        confidence = EXCLUDED.confidence,
                        importance_score = EXCLUDED.importance_score,
                        access_count = EXCLUDED.access_count,
                        last_accessed = EXCLUDED.last_accessed,
                        causal_parents = EXCLUDED.causal_parents,
                        causal_children = EXCLUDED.causal_children,
                        related_nodes = EXCLUDED.related_nodes
                    """,
                    node.node_id,
                    node.memory_type.value,
                    json.dumps(node.content),
                    json.dumps(node.embedding),
                    node.timestamp,
                    node.location,
                    node.confidence,
                    node.importance_score,
                    node.access_count,
                    node.last_accessed,
                    node.causal_parents,
                    node.causal_children,
                    node.related_nodes,
                )

    async def _store_neo4j(self, node: MemoryNode) -> None:
        assert self.neo4j_driver is not None
        async with self.neo4j_driver.session() as session:
            await session.run(
                """
                MERGE (m:Memory {node_id: $node_id})
                SET m.memory_type = $memory_type,
                    m.content_json = $content_json,
                    m.embedding_json = $embedding_json,
                    m.timestamp = $timestamp,
                    m.location_json = $location_json,
                    m.confidence = $confidence,
                    m.importance_score = $importance_score,
                    m.access_count = $access_count,
                    m.last_accessed = $last_accessed,
                    m.causal_parents_json = $causal_parents_json,
                    m.causal_children_json = $causal_children_json,
                    m.related_nodes_json = $related_nodes_json
                """,
                node_id=node.node_id,
                memory_type=node.memory_type.value,
                content_json=json.dumps(node.content),
                embedding_json=json.dumps(node.embedding),
                timestamp=node.timestamp.isoformat(),
                location_json=json.dumps(node.location),
                confidence=node.confidence,
                importance_score=node.importance_score,
                access_count=node.access_count,
                last_accessed=node.last_accessed.isoformat(),
                causal_parents_json=json.dumps(node.causal_parents),
                causal_children_json=json.dumps(node.causal_children),
                related_nodes_json=json.dumps(node.related_nodes),
            )

    async def query(
        self,
        query_embedding: list[float],
        time_range: dict[str, datetime] | None = None,
        location: dict[str, float] | None = None,
        memory_types: list[MemoryType] | None = None,
        top_k: int = 10,
    ) -> list[MemoryNode] | None:
        if self.pg_pool is None:
            return None

        conditions: list[str] = []
        params: list[Any] = []
        index = 1
        if memory_types:
            conditions.append(f"memory_type = ANY(${index}::text[])")
            params.append([memory_type.value for memory_type in memory_types])
            index += 1
        if time_range:
            conditions.append(f"timestamp BETWEEN ${index} AND ${index + 1}")
            params.extend([time_range["start"], time_range["end"]])
            index += 2

        sql = """
            SELECT node_id, memory_type, content, embedding_json, timestamp, location, confidence,
                   importance_score, access_count, last_accessed, causal_parents, causal_children, related_nodes
            FROM memory_nodes
        """
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)

        candidate_limit = max(top_k * 20, 100)
        if self.vector_enabled:
            sql += f" ORDER BY embedding_vector <=> ${index}::vector LIMIT ${index + 1}"
            params.extend([self._vector_literal(query_embedding), candidate_limit])
        else:
            sql += f" ORDER BY timestamp DESC LIMIT ${index}"
            params.append(candidate_limit)

        async with self.pg_pool.acquire() as connection:
            rows = await connection.fetch(sql, *params)

        nodes = [self._row_to_node(row) for row in rows]
        if location:
            target = [location["x"], location["y"], location["z"]]
            nodes = [node for node in nodes if euclidean_distance(node.location, target) <= location["radius"]]

        if not self.vector_enabled:
            nodes = sorted(
                nodes,
                key=lambda node: cosine_similarity(query_embedding, node.embedding)
                + (node.importance_score * 0.15),
                reverse=True,
            )

        selected = nodes[:top_k]
        if selected:
            await self._touch_nodes([node.node_id for node in selected])
        return selected

    async def _touch_nodes(self, node_ids: list[str]) -> None:
        if self.pg_pool is None or not node_ids:
            return
        async with self.pg_pool.acquire() as connection:
            await connection.execute(
                """
                UPDATE memory_nodes
                SET access_count = access_count + 1, last_accessed = NOW()
                WHERE node_id = ANY($1::text[])
                """,
                node_ids,
            )

    def _row_to_node(self, row: Any) -> MemoryNode:
        return MemoryNode(
            node_id=row["node_id"],
            memory_type=MemoryType(row["memory_type"]),
            content=dict(row["content"]),
            embedding=[float(value) for value in row["embedding_json"]],
            timestamp=row["timestamp"],
            location=[float(value) for value in row["location"]],
            confidence=float(row["confidence"]),
            importance_score=float(row["importance_score"]),
            access_count=int(row["access_count"]),
            last_accessed=row["last_accessed"],
            causal_parents=list(row["causal_parents"]),
            causal_children=list(row["causal_children"]),
            related_nodes=list(row["related_nodes"]),
        )

    async def link_causal(self, parent_id: str, child_id: str, strength: float = 0.5) -> None:
        if self.pg_pool is not None:
            async with self.pg_pool.acquire() as connection:
                await connection.execute(
                    """
                    UPDATE memory_nodes
                    SET causal_children = CASE
                        WHEN NOT ($2 = ANY(causal_children)) THEN array_append(causal_children, $2)
                        ELSE causal_children
                    END
                    WHERE node_id = $1
                    """,
                    parent_id,
                    child_id,
                )
                await connection.execute(
                    """
                    UPDATE memory_nodes
                    SET causal_parents = CASE
                        WHEN NOT ($2 = ANY(causal_parents)) THEN array_append(causal_parents, $2)
                        ELSE causal_parents
                    END
                    WHERE node_id = $1
                    """,
                    child_id,
                    parent_id,
                )

        if self.neo4j_driver is not None:
            async with self.neo4j_driver.session() as session:
                await session.run(
                    """
                    MATCH (parent:Memory {node_id: $parent_id}), (child:Memory {node_id: $child_id})
                    MERGE (parent)-[r:CAUSED]->(child)
                    SET r.strength = $strength
                    """,
                    parent_id=parent_id,
                    child_id=child_id,
                    strength=strength,
                )

    async def extract_causal_chain(self, node_id: str, depth: int = 5) -> list[MemoryNode] | None:
        if self.neo4j_driver is None:
            return None
        safe_depth = max(0, min(depth, 10))
        query = f"""
            MATCH path = (start:Memory {{node_id: $node_id}})<-[:CAUSED*0..{safe_depth}]-(ancestor:Memory)
            UNWIND nodes(path) AS node
            RETURN DISTINCT node
        """
        async with self.neo4j_driver.session() as session:
            result = await session.run(query, node_id=node_id)
            records = await result.data()

        ordered: list[MemoryNode] = []
        for record in records:
            properties = dict(record["node"])
            ordered.append(
                MemoryNode(
                    node_id=properties["node_id"],
                    memory_type=MemoryType(properties["memory_type"]),
                    content=json.loads(properties.get("content_json", "{}")),
                    embedding=json.loads(properties.get("embedding_json", "[]")),
                    timestamp=datetime.fromisoformat(properties["timestamp"]),
                    location=json.loads(properties.get("location_json", "[0.0, 0.0, 0.0]")),
                    confidence=float(properties.get("confidence", 1.0)),
                    importance_score=float(properties.get("importance_score", 0.5)),
                    access_count=int(properties.get("access_count", 0)),
                    last_accessed=datetime.fromisoformat(properties.get("last_accessed", properties["timestamp"])),
                    causal_parents=json.loads(properties.get("causal_parents_json", "[]")),
                    causal_children=json.loads(properties.get("causal_children_json", "[]")),
                    related_nodes=json.loads(properties.get("related_nodes_json", "[]")),
                )
            )
        return ordered

    async def consolidate(self) -> dict[str, int]:
        promoted = 0
        forgotten = 0
        if self.pg_pool is not None:
            async with self.pg_pool.acquire() as connection:
                promoted_rows = await connection.fetch(
                    """
                    UPDATE memory_nodes
                    SET memory_type = 'episodic'
                    WHERE memory_type = 'working'
                      AND timestamp <= NOW() - INTERVAL '1 hour'
                    RETURNING node_id
                    """
                )
                forgotten_rows = await connection.fetch(
                    """
                    DELETE FROM memory_nodes
                    WHERE importance_score < 0.2
                      AND access_count = 0
                      AND timestamp <= NOW() - INTERVAL '24 hours'
                    RETURNING node_id
                    """
                )
                promoted = len(promoted_rows)
                forgotten = len(forgotten_rows)

            if self.neo4j_driver is not None:
                async with self.neo4j_driver.session() as session:
                    if promoted_rows:
                        await session.run(
                            """
                            MATCH (m:Memory)
                            WHERE m.node_id IN $node_ids
                            SET m.memory_type = 'episodic'
                            """,
                            node_ids=[row["node_id"] for row in promoted_rows],
                        )
                    if forgotten_rows:
                        await session.run(
                            """
                            MATCH (m:Memory)
                            WHERE m.node_id IN $node_ids
                            DETACH DELETE m
                            """,
                            node_ids=[row["node_id"] for row in forgotten_rows],
                        )
        return {"promoted": promoted, "forgotten": forgotten}
