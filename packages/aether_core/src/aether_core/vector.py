from __future__ import annotations

import hashlib
import json
from math import sqrt
from typing import Any

from .models import EMBEDDING_DIMENSION


def deterministic_embedding(payload: Any, dimension: int = EMBEDDING_DIMENSION) -> list[float]:
    serialized = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    seed = hashlib.sha256(serialized).digest()
    values: list[float] = []
    state = seed
    while len(values) < dimension:
        state = hashlib.sha256(state).digest()
        values.extend(((byte / 127.5) - 1.0) for byte in state)
    return values[:dimension]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    numerator = sum(a * b for a, b in zip(left, right, strict=False))
    left_norm = sqrt(sum(a * a for a in left))
    right_norm = sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return numerator / (left_norm * right_norm)

