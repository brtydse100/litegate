import json
from datetime import UTC, datetime, timedelta

from app.services import audit, local_users


def test_audit_history_redacts_secrets_and_summarizes_keys(tmp_path, monkeypatch):
    monkeypatch.setattr(local_users.settings, "local_users_db_path", str(tmp_path / "audit.db"))

    audit.record(
        actor_id="local:admin",
        actor_email="admin@example.com",
        action="keys.bulk_update",
        target="installation-keys",
        details={"keys": ["secret-1", "secret-2"], "password": "never-store-this"},
    )

    events = audit.list_events()
    assert len(events) == 1
    assert events[0]["details"] == {"key_count": 2, "password": "[redacted]"}
    raw = json.dumps(events)
    assert "secret-1" not in raw
    assert "never-store-this" not in raw


def test_local_database_healthcheck_is_writable(tmp_path, monkeypatch):
    monkeypatch.setattr(local_users.settings, "local_users_db_path", str(tmp_path / "health.db"))
    assert local_users.healthcheck() == {"ok": True, "detail": "Writable"}


def test_record_prunes_expired_audit_events_in_bounded_batches(tmp_path, monkeypatch):
    monkeypatch.setattr(local_users.settings, "local_users_db_path", str(tmp_path / "audit.db"))
    monkeypatch.setattr(local_users.settings, "audit_retention_days", 30)
    monkeypatch.setattr(local_users.settings, "audit_cleanup_batch_size", 2)
    local_users.init_db()
    expired_at = (datetime.now(UTC) - timedelta(days=31)).isoformat()
    current_at = (datetime.now(UTC) - timedelta(days=29)).isoformat()
    with local_users.connect() as db:
        for index in range(3):
            db.execute(
                """INSERT INTO audit_events
                   (occurred_at, actor_id, actor_email, action, target, outcome, details_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (expired_at, f"local:expired-{index}", "admin@example.com", "test", "target", "success", "{}"),
            )
        db.execute(
            """INSERT INTO audit_events
               (occurred_at, actor_id, actor_email, action, target, outcome, details_json)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (current_at, "local:current", "admin@example.com", "test", "target", "success", "{}"),
        )

    audit.record(actor_id="local:admin", actor_email="admin@example.com", action="test", target="target")

    with local_users.connect() as db:
        remaining_expired = db.execute("SELECT COUNT(*) FROM audit_events WHERE occurred_at = ?", (expired_at,)).fetchone()[0]
    assert remaining_expired == 1
    assert [event["actor_id"] for event in audit.list_events()][:2] == ["local:admin", "local:current"]
