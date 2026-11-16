import os

# Safe defaults for modules imported during test collection. Individual config
# tests override these values when testing precedence and parsing.
os.environ.setdefault("LITELLM_MASTER_KEY", "sk-test")
os.environ.setdefault("JWT_SECRET", "test-secret-at-least-32-characters")

import pytest


@pytest.fixture(autouse=True)
def isolated_initialized_database(tmp_path, monkeypatch):
    """Direct API/store tests use the schema normally initialized by lifespan."""
    from app.services import local_users

    monkeypatch.setattr(local_users.settings, "local_users_db_path", str(tmp_path / "default.db"))
    local_users.init_db()
