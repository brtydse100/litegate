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


@pytest.fixture(autouse=True)
def isolated_organization_admin_cache(monkeypatch):
    """Native team-admin lookups are cached process-wide; isolate each test."""
    from app.services import organization_access

    monkeypatch.setattr(organization_access, "_admin_cache", {})


@pytest.fixture(autouse=True)
def isolated_report_and_pass_state(monkeypatch):
    """Overview status caching and verified budget passes are process-wide."""
    from app.services import budget_pass, organization_reports

    monkeypatch.setattr(organization_reports, "_status_cache", {})
    monkeypatch.setattr(budget_pass, "_generation", 1)
    monkeypatch.setattr(budget_pass, "_clean", 0)
