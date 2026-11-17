"""Startup owns schema writes; normal store operations never migrate it."""

import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.services import audit, key_secrets, local_users, organization_store, sso_identity


@pytest.fixture
def database_path(tmp_path, monkeypatch):
    path = tmp_path / "store" / "litegate.db"
    monkeypatch.setattr(local_users.settings, "local_users_db_path", str(path))
    return path


def test_ordinary_store_operations_do_not_run_schema_changes(database_path, monkeypatch):
    local_users.init_db()
    organization_store.init_db()
    sso_identity.initialize_identity_store()
    original_connect = local_users.connect
    statements = []

    def traced_connect():
        connection = original_connect()
        connection.set_trace_callback(statements.append)
        return connection

    monkeypatch.setattr(local_users, "connect", traced_connect)
    monkeypatch.setattr(organization_store, "connect", traced_connect)
    monkeypatch.setattr(key_secrets.settings, "save_api_keys_in_db", True)
    local_users.create_user("alice", "alice@example.com", "synthetic-password")
    assert local_users.authenticate("alice", "synthetic-password")
    assert local_users.has_users()
    assert len(local_users.list_users()) == 1
    organization_store.remember("alice", "alice@example.com", "sso", [])
    assert organization_store.get("alice")
    assert len(organization_store.list_identities()) == 1
    sso_identity.bind("provider", "subject", "alice@example.com", "alice")
    key_secrets.save("sk-synthetic", "alice")
    assert key_secrets.get("sk-synthetic", "alice") == "sk-synthetic"
    assert key_secrets.annotate([{"token": "sk-synthetic"}])[0]["secret_available"]
    audit.record(actor_id="alice", actor_email="alice@example.com", action="test", target="self")
    assert len(audit.list_events()) == 1
    assert local_users.healthcheck()["ok"]
    assert not [statement for statement in statements if statement.lstrip().upper().startswith(("CREATE", "ALTER", "DROP"))]


def test_connection_context_closes_after_commit_and_rollback(database_path):
    local_users.init_db()
    with local_users.connect() as committed:
        committed.execute("SELECT 1")
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        committed.execute("SELECT 1")
    with pytest.raises(ValueError):
        with local_users.connect() as rolled_back:
            raise ValueError("abort")
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        rolled_back.execute("SELECT 1")


def test_readiness_does_not_create_a_missing_database(database_path):
    assert local_users.healthcheck()["ok"] is False
    assert not database_path.exists()
    assert not database_path.parent.exists()


def test_readiness_does_not_initialize_an_empty_database(database_path):
    database_path.parent.mkdir()
    sqlite3.connect(database_path).close()
    assert local_users.healthcheck()["ok"] is False
    with sqlite3.connect(database_path) as empty:
        assert empty.execute("SELECT name FROM sqlite_master").fetchall() == []


def test_ordinary_reads_do_not_create_a_missing_database(database_path):
    with pytest.raises(sqlite3.OperationalError):
        local_users.list_users()
    assert not database_path.exists()
    assert not database_path.parent.exists()


def test_repeated_concurrent_startup_preserves_existing_rows(database_path, monkeypatch):
    local_users.init_db()
    user = local_users.create_user("existing", "existing@example.com", "synthetic-password")
    monkeypatch.setattr(key_secrets.settings, "save_api_keys_in_db", True)
    key_secrets.save("sk-synthetic", user["user_id"])
    organization_store.remember(user["user_id"], user["email"], "sso", ["original"])
    sso_identity.bind("provider", "subject", user["email"], user["user_id"])
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: local_users.init_db(), range(8)))
    assert local_users.get_user("existing") == user
    assert key_secrets.get("sk-synthetic", user["user_id"]) == "sk-synthetic"
    assert organization_store.get(user["user_id"])["groups"] == ["original"]
    assert sso_identity.lookup_binding("provider", "subject")["user_id"] == user["user_id"]


def test_simultaneous_first_startup_creates_complete_schema(database_path):
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: local_users.init_db(), range(8)))
    assert local_users.healthcheck()["ok"]
    assert organization_store.list_identities() == []
    with local_users.connect() as db:
        assert db.execute("SELECT * FROM sso_reservations").fetchall() == []
        assert db.execute("SELECT * FROM organization_owned_teams").fetchall() == []


def test_failed_migration_rolls_back_tables_rows_and_schema_version(database_path, monkeypatch):
    from app.services import database

    local_users.init_db()
    original_version = len(database.MIGRATIONS)

    def interrupted(db):
        db.execute("CREATE TABLE partial_migration (value TEXT)")
        db.execute("INSERT INTO organization_owned_teams VALUES ('unexpected', 'now')")
        raise sqlite3.OperationalError("synthetic interrupted migration")

    with monkeypatch.context() as patch:
        patch.setattr(database, "MIGRATIONS", (*database.MIGRATIONS, interrupted))
        with pytest.raises(sqlite3.OperationalError, match="interrupted"):
            database.initialize()
    with local_users.connect() as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == original_version
        assert db.execute("SELECT name FROM sqlite_master WHERE name='partial_migration'").fetchone() is None
        assert db.execute("SELECT * FROM organization_owned_teams").fetchall() == []
    assert local_users.healthcheck()["ok"]


def test_startup_lock_failure_is_bounded_and_preserves_database(database_path):
    from app.services import database

    local_users.init_db()
    with local_users.connect() as holder:
        holder.execute("BEGIN IMMEDIATE")
        started = time.monotonic()
        with pytest.raises(sqlite3.OperationalError, match="locked"):
            database.initialize(timeout=0.05)
        assert time.monotonic() - started < 1
    local_users.init_db()
    assert local_users.healthcheck()["ok"]


def test_newer_database_schema_is_not_downgraded(database_path):
    from app.services import database

    local_users.init_db()
    version = len(database.MIGRATIONS) + 1
    with local_users.connect() as db:
        db.execute(f"PRAGMA user_version={version}")
    with pytest.raises(sqlite3.DatabaseError, match="newer"):
        local_users.init_db()
    assert local_users.healthcheck()["ok"] is False
    with local_users.connect() as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == version


def test_preversioning_upgrade_preserves_reservations_and_saved_keys(database_path, monkeypatch):
    from app.services import database

    database_path.parent.mkdir()
    with sqlite3.connect(database_path) as legacy:
        legacy.execute("CREATE TABLE stored_api_keys (key_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL, key_secret TEXT NOT NULL)")
        legacy.execute("INSERT INTO stored_api_keys VALUES ('old-hash', 'canonical', 'synthetic-secret')")
        legacy.execute("""CREATE TABLE sso_reservations (
            provider TEXT NOT NULL, email TEXT NOT NULL, user_id TEXT NOT NULL UNIQUE,
            ownership_token TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'intent',
            candidate_id TEXT NOT NULL DEFAULT '', PRIMARY KEY(provider, email))""")
        legacy.execute("INSERT INTO sso_reservations VALUES ('provider', 'alice@example.com', 'canonical', 'owner', 'pending', 'candidate')")
    database.initialize()
    monkeypatch.setattr(key_secrets.settings, "save_api_keys_in_db", True)
    assert key_secrets.get("old-hash", "canonical") == "synthetic-secret"
    assert sso_identity.reservation("provider", "alice@example.com") == {
        "provider": "provider",
        "email": "alice@example.com",
        "user_id": "canonical",
        "ownership_token": "owner",
        "status": "pending",
        "candidate_id": "candidate",
    }
    assert local_users.healthcheck()["ok"]


def test_participant_migration_counts_previously_signed_in_users_only(database_path, monkeypatch):
    from app.services import budget_enforcement, database

    # Simulate an install upgraded from the release before participants existed.
    with monkeypatch.context() as patch:
        patch.setattr(database, "MIGRATIONS", database.MIGRATIONS[:-1])
        database.initialize()
    organization_store.remember("signed-in", "a@example.invalid", "sso", [])
    organization_store.remember("local-user", "b@example.invalid", "local", [])
    organization_store.remember("discovered", "c@example.invalid", "configured_email", [])
    database.initialize()
    assert budget_enforcement.participants() == {"signed-in", "local-user"}
