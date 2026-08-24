"""Persistent, secret-safe administrator audit history."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from app.services import local_users

_SENSITIVE_FIELDS = {"password", "token", "key", "api_key", "client_secret", "jwt_secret"}


def _safe_details(details: dict | None) -> dict:
    safe: dict = {}
    for name, value in (details or {}).items():
        normalized = name.casefold()
        if normalized in _SENSITIVE_FIELDS or "password" in normalized or "secret" in normalized:
            safe[name] = "[redacted]"
        elif name == "keys" and isinstance(value, list):
            safe["key_count"] = len(value)
        else:
            safe[name] = _safe_value(value)
    return safe


def _safe_value(value: object) -> object:
    if isinstance(value, dict):
        return _safe_details(value)
    if isinstance(value, (list, tuple, set)):
        return [_safe_value(item) for item in value]
    return value


def record(
    *,
    actor_id: str,
    actor_email: str,
    action: str,
    target: str,
    outcome: str = "success",
    details: dict | None = None,
) -> None:
    local_users.init_db()
    payload = json.dumps(_safe_details(details), separators=(",", ":"), default=str)
    with local_users.connect() as db:
        db.execute(
            """INSERT INTO audit_events
               (occurred_at, actor_id, actor_email, action, target, outcome, details_json)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                datetime.now(UTC).isoformat(),
                actor_id,
                actor_email,
                action,
                target,
                outcome,
                payload,
            ),
        )


def list_events(limit: int = 100) -> list[dict]:
    local_users.init_db()
    with local_users.connect() as db:
        rows = db.execute(
            """SELECT id, occurred_at, actor_id, actor_email, action, target, outcome, details_json
               FROM audit_events ORDER BY id DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    return [
        {
            "id": row["id"],
            "occurred_at": row["occurred_at"],
            "actor_id": row["actor_id"],
            "actor_email": row["actor_email"],
            "action": row["action"],
            "target": row["target"],
            "outcome": row["outcome"],
            "details": json.loads(row["details_json"]),
        }
        for row in rows
    ]
