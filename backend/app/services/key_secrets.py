"""Optional recoverable key storage in LiteGate's existing SQLite database."""

import hashlib

from app.config import settings
from app.services import local_users


def key_hash(identifier: str) -> str:
    return hashlib.sha256(identifier.encode()).hexdigest() if identifier.startswith("sk-") else identifier


def save(secret: str, user_id: str) -> None:
    if not settings.save_api_keys_in_db:
        return
    local_users.init_db()
    with local_users.connect() as db:
        db.execute(
            "INSERT OR REPLACE INTO stored_api_keys (key_hash, user_id, key_secret) VALUES (?, ?, ?)",
            (key_hash(secret), user_id, secret),
        )


def remove(identifier: str) -> None:
    if not local_users._db_path().exists():
        return
    with local_users.connect() as db:
        if db.execute("SELECT 1 FROM sqlite_master WHERE name = 'stored_api_keys'").fetchone():
            db.execute("DELETE FROM stored_api_keys WHERE key_hash = ?", (key_hash(identifier),))


def get(identifier: str, user_id: str) -> str | None:
    if not settings.save_api_keys_in_db:
        return None
    local_users.init_db()
    with local_users.connect() as db:
        row = db.execute(
            "SELECT key_secret FROM stored_api_keys WHERE key_hash = ? AND user_id = ?",
            (key_hash(identifier), user_id),
        ).fetchone()
    return row["key_secret"] if row else None


def annotate(keys: list[dict]) -> list[dict]:
    if not settings.save_api_keys_in_db or not keys:
        return keys
    local_users.init_db()
    identifiers = [key_hash(key.get("token") or key.get("api_key") or key.get("key") or "") for key in keys]
    available: set[str] = set()
    with local_users.connect() as db:
        for offset in range(0, len(identifiers), 500):
            batch = identifiers[offset : offset + 500]
            placeholders = ",".join("?" for _ in batch)
            available.update(row["key_hash"] for row in db.execute(f"SELECT key_hash FROM stored_api_keys WHERE key_hash IN ({placeholders})", batch))
    return [{**key, "secret_available": identifier in available} for key, identifier in zip(keys, identifiers)]
