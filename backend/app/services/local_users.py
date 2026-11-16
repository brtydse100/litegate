"""Small persistent local-account store using only Python's standard library."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.config import settings
from app.services import database

_HASH_NAME = "sha256"
_ITERATIONS = 310_000


def _db_path() -> Path:
    return database.path()


def connect() -> sqlite3.Connection:
    return database.connect()


def init_db() -> None:
    """Compatibility entry point for explicit application startup and test setup."""
    database.initialize()


def healthcheck() -> dict:
    return database.healthcheck()


def _password_hash(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(_HASH_NAME, password.encode("utf-8"), salt, _ITERATIONS)
    return f"pbkdf2_{_HASH_NAME}${_ITERATIONS}${salt.hex()}${digest.hex()}"


def _password_matches(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt_hex, expected_hex = encoded.split("$", 3)
        if algorithm != f"pbkdf2_{_HASH_NAME}":
            return False
        actual = hashlib.pbkdf2_hmac(
            _HASH_NAME,
            password.encode("utf-8"),
            bytes.fromhex(salt_hex),
            int(iterations),
        )
        return hmac.compare_digest(actual.hex(), expected_hex)
    except (ValueError, TypeError):
        return False


_DUMMY_PASSWORD_HASH = _password_hash(secrets.token_urlsafe(32))


def _public(row: sqlite3.Row) -> dict:
    return {
        "username": row["username"],
        "user_id": row["user_id"],
        "email": row["email"],
        "role": row["role"],
        "active": bool(row["active"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def has_users() -> bool:
    with connect() as db:
        return bool(db.execute("SELECT 1 FROM local_users LIMIT 1").fetchone())


def list_users() -> list[dict]:
    with connect() as db:
        rows = db.execute("SELECT * FROM local_users ORDER BY active DESC, username COLLATE NOCASE").fetchall()
    return [_public(row) for row in rows]


def get_user(username: str) -> Optional[dict]:
    with connect() as db:
        row = db.execute("SELECT * FROM local_users WHERE username = ?", (username,)).fetchone()
    return _public(row) if row else None


def authenticate(username: str, password: str) -> Optional[dict]:
    with connect() as db:
        row = db.execute("SELECT * FROM local_users WHERE username = ?", (username,)).fetchone()
    password_matches = _password_matches(password, row["password_hash"] if row else _DUMMY_PASSWORD_HASH)
    if not row or not row["active"] or not password_matches:
        return None
    return _public(row)


def create_user(username: str, email: str, password: str, role: str = "user") -> dict:
    if username.casefold() == (settings.local_auth_username or "").casefold():
        raise ValueError("This username is reserved for the bootstrap administrator")
    now = datetime.now(timezone.utc).isoformat()
    user_id = f"local:{username.lower()}"
    try:
        with connect() as db:
            db.execute(
                """INSERT INTO local_users
                   (username, user_id, email, password_hash, role, active, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, 1, ?, ?)""",
                (username, user_id, email, _password_hash(password), role, now, now),
            )
    except sqlite3.IntegrityError as exc:
        raise ValueError("A local user with that username already exists") from exc
    return get_user(username)  # type: ignore[return-value]


def update_user(
    username: str,
    *,
    email: Optional[str] = None,
    password: Optional[str] = None,
    role: Optional[str] = None,
    active: Optional[bool] = None,
) -> Optional[dict]:
    changes: list[str] = []
    values: list[object] = []
    if email is not None:
        changes.append("email = ?")
        values.append(email)
    if password is not None:
        changes.append("password_hash = ?")
        values.append(_password_hash(password))
    if role is not None:
        changes.append("role = ?")
        values.append(role)
    if active is not None:
        changes.append("active = ?")
        values.append(int(active))
    if not changes:
        return get_user(username)
    changes.append("updated_at = ?")
    values.extend([datetime.now(timezone.utc).isoformat(), username])
    with connect() as db:
        result = db.execute(
            f"UPDATE local_users SET {', '.join(changes)} WHERE username = ?",
            values,
        )
    return get_user(username) if result.rowcount else None
