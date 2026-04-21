from __future__ import annotations

import asyncio
from dataclasses import dataclass
from time import monotonic


@dataclass
class CircuitState:
    failures: int = 0
    opened_at: float | None = None


class CircuitBreaker:
    def __init__(self, failure_threshold: int = 5, recovery_timeout_s: float = 30.0) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_timeout_s = recovery_timeout_s
        self.state = CircuitState()
        self._lock = asyncio.Lock()

    async def allow(self) -> bool:
        async with self._lock:
            if self.state.opened_at is None:
                return True
            if monotonic() - self.state.opened_at >= self.recovery_timeout_s:
                self.state.failures = 0
                self.state.opened_at = None
                return True
            return False

    async def record_success(self) -> None:
        async with self._lock:
            self.state.failures = 0
            self.state.opened_at = None

    async def record_failure(self) -> None:
        async with self._lock:
            self.state.failures += 1
            if self.state.failures >= self.failure_threshold:
                self.state.opened_at = monotonic()

