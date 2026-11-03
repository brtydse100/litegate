"""Durable SSO ownership intent; LiteLLM remains the user and membership store."""

import hashlib
import json
import secrets
import sqlite3

from app.config import settings
from app.services import local_users


class IdentityConflict(ValueError):
    """An identity cannot claim or replace an existing canonical account."""


def provider_authority() -> str:
    if settings.generic_sso_enabled:
        authority = ["generic", settings.generic_userinfo_endpoint, settings.generic_client_id]
    else:
        authority = ["oidc", settings.oidc_issuer_url.rstrip("/"), settings.oidc_client_id]
    return json.dumps(authority, separators=(",", ":"))


def initialize_identity_store() -> None:
    with local_users.connect() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS sso_reservations (
            provider TEXT NOT NULL, email TEXT NOT NULL, user_id TEXT NOT NULL UNIQUE,
            ownership_token TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'intent'
                CHECK(status IN ('intent', 'reserved', 'pending', 'superseded')),
            candidate_id TEXT NOT NULL DEFAULT '', PRIMARY KEY(provider, email))""")
        db.execute("""CREATE TABLE IF NOT EXISTS sso_bindings (
            provider TEXT NOT NULL, subject TEXT NOT NULL, email TEXT NOT NULL,
            user_id TEXT NOT NULL UNIQUE, PRIMARY KEY(provider, subject), UNIQUE(provider, email))""")


def _existing_row(query: str, params: tuple) -> dict | None:
    """Probe existing bookkeeping without creating a database on legacy logins."""
    path = local_users._db_path()
    if not path.exists():
        return None
    with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='sso_bindings'").fetchone():
            return None
        row = db.execute(query, params).fetchone()
        return dict(row) if row else None


def lookup_binding(provider: str, subject: str) -> dict | None:
    return _existing_row("SELECT * FROM sso_bindings WHERE provider=? AND subject=?", (provider, subject))


def binding_for_email(provider: str, email: str) -> dict | None:
    return _existing_row("SELECT * FROM sso_bindings WHERE provider=? AND email=?", (provider, email.strip().casefold()))


def reservation(provider: str, email: str) -> dict | None:
    return _existing_row("SELECT * FROM sso_reservations WHERE provider=? AND email=?", (provider, email.strip().casefold()))


def reserve(provider: str, email: str) -> dict:
    initialize_identity_store()
    email = email.strip().casefold()
    digest = hashlib.sha256(json.dumps([provider, email], separators=(",", ":")).encode()).hexdigest()
    with local_users.connect() as db:
        db.execute(
            "INSERT OR IGNORE INTO sso_reservations(provider,email,user_id,ownership_token) VALUES (?,?,?,?)",
            (provider, email, f"litegate-org:{digest}", secrets.token_urlsafe(32)),
        )
        row = db.execute("SELECT * FROM sso_reservations WHERE provider=? AND email=?", (provider, email)).fetchone()
        return dict(row)


def mark_reservation(provider: str, email: str, status: str, candidate_id: str = "") -> None:
    with local_users.connect() as db:
        db.execute(
            "UPDATE sso_reservations SET status=?, candidate_id=? WHERE provider=? AND email=? AND status!='superseded'",
            (status, candidate_id, provider, email.strip().casefold()),
        )


def bind(provider: str, subject: str, email: str, user_id: str) -> None:
    initialize_identity_store()
    email = email.strip().casefold()
    try:
        with local_users.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute("SELECT * FROM sso_bindings WHERE provider=? AND subject=?", (provider, subject)).fetchone()
            if existing:
                if existing["user_id"] != user_id:
                    raise IdentityConflict("The authenticated identity already has a different canonical user")
                return
            db.execute("INSERT INTO sso_bindings VALUES (?,?,?,?)", (provider, subject, email, user_id))
            db.execute(
                """UPDATE sso_reservations SET status=CASE WHEN user_id=? THEN 'reserved' ELSE 'superseded' END
                   WHERE provider=? AND email=?""",
                (user_id, provider, email),
            )
    except sqlite3.IntegrityError as exc:
        raise IdentityConflict("The email or canonical user is already bound to another SSO identity") from exc


def local_conflict(email: str, user_id: str = "") -> bool:
    if user_id.startswith("local:"):
        return True
    path = local_users._db_path()
    if not path.exists():
        return False
    with local_users.connect() as db:
        exists = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='local_users'").fetchone()
        if not exists:
            return False
        return any(
            row["user_id"] == user_id or row["email"].strip().casefold() == email.strip().casefold()
            for row in db.execute("SELECT user_id, email FROM local_users")
        )
