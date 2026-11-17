"""Versioned, transactional startup migrations for LiteGate's shared SQLite store."""

from __future__ import annotations

import logging
import sqlite3
import time
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)


class Connection(sqlite3.Connection):
    """Keep SQLite's transaction context behavior and always release its handle."""

    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            self.close()


def path() -> Path:
    configured = Path(settings.local_users_db_path)
    return configured if configured.is_absolute() else Path(__file__).resolve().parents[2] / configured


def connect(*, create: bool = False, read_only: bool = False, timeout: float = 5) -> sqlite3.Connection:
    """Open a short-lived handle; only explicit initialization may create a file."""
    # Windows resolve() can switch to a \\?\ path during concurrent file creation.
    # absolute() keeps a stable SQLite-compatible file URI throughout startup.
    target = path().absolute()
    if create:
        target.parent.mkdir(parents=True, exist_ok=True)
    mode = "rwc" if create else "ro" if read_only else "rw"
    connection = sqlite3.connect(target.as_uri() + f"?mode={mode}", uri=True, timeout=timeout, factory=Connection)
    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
    except BaseException:
        connection.close()
        raise
    return connection


def _existing_stores(db: sqlite3.Connection) -> None:
    # IF NOT EXISTS adopts pre-versioning databases without rewriting their rows.
    statements = (
        """CREATE TABLE IF NOT EXISTS local_users (
            username TEXT PRIMARY KEY COLLATE NOCASE,
            user_id TEXT NOT NULL UNIQUE, email TEXT NOT NULL COLLATE NOCASE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user' CHECK(role IN ('user', 'admin')),
            active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""",
        """CREATE TABLE IF NOT EXISTS audit_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT, occurred_at TEXT NOT NULL,
            actor_id TEXT NOT NULL, actor_email TEXT NOT NULL, action TEXT NOT NULL,
            target TEXT NOT NULL, outcome TEXT NOT NULL CHECK(outcome IN ('success', 'failure')),
            details_json TEXT NOT NULL DEFAULT '{}')""",
        "CREATE INDEX IF NOT EXISTS idx_audit_events_occurred_at ON audit_events(occurred_at DESC)",
        """CREATE TABLE IF NOT EXISTS stored_api_keys (
            key_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL, key_secret TEXT NOT NULL)""",
        """CREATE TABLE IF NOT EXISTS organization_identities (
            user_id TEXT PRIMARY KEY, email TEXT NOT NULL, auth_source TEXT NOT NULL,
            groups_json TEXT NOT NULL, team_id TEXT, policy_json TEXT,
            sync_error TEXT, updated_at TEXT NOT NULL)""",
        """CREATE TABLE IF NOT EXISTS sso_reservations (
            provider TEXT NOT NULL, email TEXT NOT NULL, user_id TEXT NOT NULL UNIQUE,
            ownership_token TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'intent'
                CHECK(status IN ('intent', 'reserved', 'pending', 'superseded')),
            candidate_id TEXT NOT NULL DEFAULT '', PRIMARY KEY(provider, email))""",
        """CREATE TABLE IF NOT EXISTS sso_bindings (
            provider TEXT NOT NULL, subject TEXT NOT NULL, email TEXT NOT NULL,
            user_id TEXT NOT NULL UNIQUE, PRIMARY KEY(provider, subject), UNIQUE(provider, email))""",
        """CREATE TABLE IF NOT EXISTS organization_owned_teams (
            team_id TEXT PRIMARY KEY, created_at TEXT NOT NULL)""",
    )
    for statement in statements:
        db.execute(statement)


def _analytics_store(db: sqlite3.Connection) -> None:
    from app.services import analytics_store

    analytics_store.create_tables(db)


def _budget_store(db: sqlite3.Connection) -> None:
    from app.services import budget_store

    budget_store.create_tables(db)


def _analytics_failures(db: sqlite3.Connection) -> None:
    from app.services import analytics_store

    analytics_store.create_failure_table(db)


def _organization_participants(db: sqlite3.Connection) -> None:
    from app.services import budget_enforcement

    budget_enforcement.create_table(db)
    # Users who already signed in count toward equal budget splits.
    db.execute(
        """INSERT OR IGNORE INTO organization_participants
        SELECT user_id, updated_at FROM organization_identities WHERE auth_source IN ('sso', 'local')"""
    )


# Append migrations in order; each callable receives the same reserved transaction.
MIGRATIONS = (_existing_stores, _analytics_store, _budget_store, _analytics_failures, _organization_participants)


def _enable_wal(db: sqlite3.Connection, deadline: float) -> None:
    # Changing journal mode can return BUSY immediately, bypassing busy_timeout.
    while True:
        try:
            db.execute(f"PRAGMA busy_timeout={max(0, int((deadline - time.monotonic()) * 1000))}")
            db.execute("PRAGMA journal_mode=WAL")
            return
        except sqlite3.OperationalError as exc:
            remaining = deadline - time.monotonic()
            if getattr(exc, "sqlite_errorcode", 0) & 0xFF not in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED) or remaining <= 0:
                raise
            time.sleep(min(0.01, remaining))


def initialize(*, timeout: float = 5) -> None:
    """Reserve one bounded write transaction and atomically advance the schema."""
    try:
        deadline = time.monotonic() + timeout
        with connect(create=True, timeout=timeout) as db:
            _enable_wal(db, deadline)
            db.execute(f"PRAGMA busy_timeout={max(0, int((deadline - time.monotonic()) * 1000))}")
            db.execute("BEGIN IMMEDIATE")
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version > len(MIGRATIONS):
                raise sqlite3.DatabaseError("Local database schema is newer than this LiteGate version")
            for index in range(version, len(MIGRATIONS)):
                MIGRATIONS[index](db)
                db.execute(f"PRAGMA user_version={index + 1}")
    except (OSError, sqlite3.Error):
        logger.exception("Local database startup initialization failed")
        raise


def healthcheck() -> dict:
    """Probe existing schema and write access without creating or migrating it."""
    try:
        with connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("PRAGMA user_version").fetchone()[0] != len(MIGRATIONS):
                raise sqlite3.DatabaseError("Local database schema is not initialized")
            db.execute("SELECT username FROM local_users LIMIT 1")
            db.execute("SELECT id FROM audit_events LIMIT 1")
            db.rollback()
        return {"ok": True, "detail": "Writable"}
    except (OSError, sqlite3.Error):
        return {"ok": False, "detail": "Local account database is not writable"}
