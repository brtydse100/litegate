from app.services import local_users


def test_local_user_lifecycle(tmp_path, monkeypatch):
    monkeypatch.setattr(local_users.settings, "local_users_db_path", str(tmp_path / "users.db"))

    created = local_users.create_user("alice", "alice@example.com", "correct-horse-123", "user")
    assert created["user_id"] == "local:alice"
    assert created["active"] is True
    assert local_users.authenticate("alice", "wrong-password") is None
    assert local_users.authenticate("ALICE", "correct-horse-123")["email"] == "alice@example.com"

    updated = local_users.update_user("alice", role="admin", active=False)
    assert updated["role"] == "admin"
    assert updated["active"] is False
    assert local_users.authenticate("alice", "correct-horse-123") is None


def test_local_password_is_not_stored_as_plaintext(tmp_path, monkeypatch):
    db_path = tmp_path / "users.db"
    monkeypatch.setattr(local_users.settings, "local_users_db_path", str(db_path))
    local_users.create_user("bob", "bob@example.com", "never-store-this", "user")

    assert b"never-store-this" not in db_path.read_bytes()


def test_duplicate_username_is_case_insensitive(tmp_path, monkeypatch):
    monkeypatch.setattr(local_users.settings, "local_users_db_path", str(tmp_path / "users.db"))
    local_users.create_user("CaseUser", "one@example.com", "long-password-1", "user")

    try:
        local_users.create_user("caseuser", "two@example.com", "long-password-2", "user")
        assert False, "Expected duplicate username to fail"
    except ValueError as exc:
        assert "already exists" in str(exc)
