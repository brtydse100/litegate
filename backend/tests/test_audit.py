import json

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
