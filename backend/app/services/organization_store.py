"""Verified identity mappings and synchronization status in the existing SQLite store."""

import json
from datetime import datetime, timezone

from app.services.local_users import connect
from app.services import database


def init_db() -> None:
    database.initialize()


def remember(user_id: str, email: str, auth_source: str, groups: list[str]) -> None:
    with connect() as db:
        db.execute(
            """INSERT INTO organization_identities
            (user_id, email, auth_source, groups_json, updated_at) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET email=excluded.email,
            auth_source=excluded.auth_source, groups_json=excluded.groups_json,
            updated_at=excluded.updated_at""",
            (user_id, email, auth_source, json.dumps(groups), datetime.now(timezone.utc).isoformat()),
        )


def get(user_id: str) -> dict | None:
    with connect() as db:
        row = db.execute("SELECT * FROM organization_identities WHERE user_id=?", (user_id,)).fetchone()
    return decode(row) if row else None


def decode(row) -> dict:
    value = dict(row)
    value["groups"] = json.loads(value.pop("groups_json"))
    value["policy"] = json.loads(value.pop("policy_json") or "null")
    return value


def list_identities() -> list[dict]:
    with connect() as db:
        return [decode(row) for row in db.execute("SELECT * FROM organization_identities ORDER BY user_id")]


def synced(user_id: str, team_id: str, policy: dict) -> None:
    with connect() as db:
        db.execute(
            "UPDATE organization_identities SET team_id=?, policy_json=?, sync_error=NULL WHERE user_id=?",
            (team_id, json.dumps(policy, sort_keys=True), user_id),
        )


def bind_team(user_id: str, team_id: str) -> None:
    """Retain the root before an upstream mutation whose result may be uncertain."""
    with connect() as db:
        db.execute("UPDATE organization_identities SET team_id=? WHERE user_id=?", (team_id, user_id))


def failed(user_id: str, message: str) -> None:
    with connect() as db:
        db.execute("UPDATE organization_identities SET sync_error=? WHERE user_id=?", (message[:300], user_id))


def validated(user_id: str) -> None:
    """Clear a discovery failure only after fresh remote assignment validation."""
    with connect() as db:
        db.execute("UPDATE organization_identities SET sync_error=NULL WHERE user_id=?", (user_id,))
