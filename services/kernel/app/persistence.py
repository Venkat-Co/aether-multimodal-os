from __future__ import annotations

import asyncio
import json
from typing import Any

try:
    import asyncpg
except Exception:  # pragma: no cover - optional persistence dependency
    asyncpg = None  # type: ignore[assignment]

from aether_core.config import AetherSettings

from .models import ControlPlaneStateSnapshot


class KernelPersistenceStore:
    def __init__(self, settings: AetherSettings) -> None:
        self.settings = settings
        self.pg_pool: Any | None = None
        self.snapshot_id = f"{settings.service_name}-control-plane"
        self.backend_status: dict[str, Any] = {
            "postgres": {"enabled": False, "detail": "not-initialized"},
            "snapshot_id": self.snapshot_id,
        }

    async def initialize(self) -> None:
        if asyncpg is None:
            self.backend_status["postgres"] = {"enabled": False, "detail": "asyncpg is not installed"}
            return

        last_error: Exception | None = None
        for attempt in range(1, max(self.settings.startup_retry_attempts, 1) + 1):
            try:
                self.pg_pool = await asyncpg.create_pool(self.settings.postgres_dsn, min_size=1, max_size=4)
                async with self.pg_pool.acquire() as connection:
                    await connection.execute(
                        """
                        CREATE TABLE IF NOT EXISTS kernel_control_plane_snapshots (
                            snapshot_id TEXT PRIMARY KEY,
                            schema_version INTEGER NOT NULL,
                            payload JSONB NOT NULL,
                            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                        )
                        """
                    )
                    await connection.execute(
                        """
                        CREATE INDEX IF NOT EXISTS kernel_control_plane_snapshots_updated_idx
                        ON kernel_control_plane_snapshots (updated_at DESC)
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

    async def close(self) -> None:
        if self.pg_pool is not None:
            await self.pg_pool.close()
            self.pg_pool = None

    async def load_snapshot(self) -> ControlPlaneStateSnapshot | None:
        if self.pg_pool is None:
            return None

        async with self.pg_pool.acquire() as connection:
            row = await connection.fetchrow(
                """
                SELECT schema_version, payload, updated_at
                FROM kernel_control_plane_snapshots
                WHERE snapshot_id = $1
                """,
                self.snapshot_id,
            )

        if row is None:
            return None

        raw_payload = row["payload"]
        if isinstance(raw_payload, str):
            payload = json.loads(raw_payload)
        else:
            payload = dict(raw_payload)
        payload["schema_version"] = row["schema_version"]
        payload["updated_at"] = row["updated_at"]
        return ControlPlaneStateSnapshot.model_validate(payload)

    async def save_snapshot(self, snapshot: ControlPlaneStateSnapshot) -> bool:
        if self.pg_pool is None:
            return False

        payload = snapshot.model_dump(mode="json")
        schema_version = payload.pop("schema_version", snapshot.schema_version)
        updated_at = snapshot.updated_at

        async with self.pg_pool.acquire() as connection:
            await connection.execute(
                """
                INSERT INTO kernel_control_plane_snapshots (snapshot_id, schema_version, payload, updated_at)
                VALUES ($1, $2, $3::jsonb, $4)
                ON CONFLICT (snapshot_id) DO UPDATE SET
                    schema_version = EXCLUDED.schema_version,
                    payload = EXCLUDED.payload,
                    updated_at = EXCLUDED.updated_at
                """,
                self.snapshot_id,
                schema_version,
                json.dumps(payload),
                updated_at,
            )
        return True
