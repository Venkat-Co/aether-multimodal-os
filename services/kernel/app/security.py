from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from aether_core.config import AetherSettings

from .models import OperatorSession, OperatorSessionRequest, ReviewQueueItem, ReviewResolveRequest

PRIVILEGED_ROLES = {"mission_controller", "admin", "system"}
KNOWN_ROLES = {"observer", "analyst", "operator", "shift_lead", *PRIVILEGED_ROLES}
PERMISSION_MAP: dict[str, list[str]] = {
    "observer": ["reviews.view"],
    "analyst": ["reviews.view", "reviews.reject.low_medium"],
    "operator": ["reviews.view", "reviews.resolve.low_medium"],
    "shift_lead": ["reviews.view", "reviews.resolve.high", "reviews.rerun.high"],
    "mission_controller": ["reviews.view", "reviews.resolve.critical", "reviews.rerun.critical", "control_plane.manage"],
    "admin": ["reviews.view", "reviews.resolve.critical", "reviews.rerun.critical", "control_plane.manage"],
    "system": ["reviews.view", "reviews.resolve.critical", "reviews.rerun.critical", "control_plane.manage"],
}


def normalize_token(value: str | None, fallback: str = "observer") -> str:
    if value is None:
        return fallback
    normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
    return normalized or fallback


def permissions_for_role(role: str) -> list[str]:
    normalized = normalize_token(role)
    return list(PERMISSION_MAP.get(normalized, PERMISSION_MAP["observer"]))


def _urlsafe_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _urlsafe_decode(data: str) -> bytes:
    padding = "=" * ((4 - len(data) % 4) % 4)
    return base64.urlsafe_b64decode(f"{data}{padding}")


@dataclass(slots=True)
class OperatorIdentity:
    operator_name: str
    operator_role: str
    review_source: str
    permissions: list[str]
    trusted: bool


class OperatorSessionManager:
    def __init__(self, settings: AetherSettings) -> None:
        self.settings = settings

    def create_session(self, request: OperatorSessionRequest) -> OperatorSession:
        role = normalize_token(request.operator_role)
        source = normalize_token(request.review_source, fallback="dashboard")
        now = datetime.now(tz=UTC)
        expires_at = now + timedelta(seconds=self.settings.operator_session_ttl_seconds)
        payload = {
            "sub": request.operator_name.strip(),
            "role": role,
            "source": source,
            "permissions": permissions_for_role(role),
            "iat": now.isoformat(),
            "exp": expires_at.isoformat(),
        }
        payload_json = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        signature = hmac.new(self.settings.api_token.encode("utf-8"), payload_json, hashlib.sha256).digest()
        token = f"{_urlsafe_encode(payload_json)}.{_urlsafe_encode(signature)}"
        return OperatorSession(
            session_token=token,
            operator_name=payload["sub"],
            operator_role=role,
            review_source=source,
            permissions=payload["permissions"],
            issued_at=now,
            expires_at=expires_at,
        )

    def verify_session(self, token: str) -> OperatorIdentity:
        try:
            encoded_payload, encoded_signature = token.split(".", 1)
        except ValueError as exc:  # pragma: no cover - defensive
            raise PermissionError("Malformed operator session token") from exc

        payload_bytes = _urlsafe_decode(encoded_payload)
        signature = _urlsafe_decode(encoded_signature)
        expected_signature = hmac.new(
            self.settings.api_token.encode("utf-8"),
            payload_bytes,
            hashlib.sha256,
        ).digest()

        if not hmac.compare_digest(signature, expected_signature):
            raise PermissionError("Operator session signature is invalid")

        payload = json.loads(payload_bytes.decode("utf-8"))
        expires_at = datetime.fromisoformat(payload["exp"])
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at <= datetime.now(tz=UTC):
            raise PermissionError("Operator session has expired")

        role = normalize_token(payload.get("role"))
        return OperatorIdentity(
            operator_name=payload["sub"],
            operator_role=role,
            review_source=normalize_token(payload.get("source"), fallback="dashboard"),
            permissions=permissions_for_role(role),
            trusted=True,
        )

    def resolve_identity(
        self,
        *,
        session_token: str | None,
        operator_name: str | None,
        operator_role: str | None,
        review_source: str | None,
    ) -> OperatorIdentity | None:
        if session_token:
            return self.verify_session(session_token)

        if operator_name is None:
            return None

        role = normalize_token(operator_role)
        return OperatorIdentity(
            operator_name=operator_name,
            operator_role=role,
            review_source=normalize_token(review_source, fallback="dashboard"),
            permissions=permissions_for_role(role),
            trusted=False,
        )


def authorize_review_resolution(
    review: ReviewQueueItem,
    request: ReviewResolveRequest,
    identity: OperatorIdentity,
) -> None:
    role = normalize_token(identity.operator_role)
    risk_level = normalize_token(review.risk_level, fallback="medium")
    resolution = normalize_token(request.resolution, fallback="approved")

    if role in PRIVILEGED_ROLES:
        return

    if role == "shift_lead":
        if risk_level == "critical":
            raise PermissionError("Role 'shift_lead' cannot resolve critical reviews")
        return

    if role == "operator":
        if request.rerun_source:
            raise PermissionError("Role 'operator' cannot replay review sources")
        if risk_level not in {"low", "medium"}:
            raise PermissionError("Role 'operator' can only resolve low or medium risk reviews")
        return

    if role == "analyst":
        if request.rerun_source:
            raise PermissionError("Role 'analyst' cannot replay review sources")
        if resolution != "rejected":
            raise PermissionError("Role 'analyst' can only reject review items")
        if risk_level not in {"low", "medium"}:
            raise PermissionError("Role 'analyst' can only reject low or medium risk reviews")
        return

    raise PermissionError(f"Role '{role}' is not permitted to resolve review items")
