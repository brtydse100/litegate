"""Persisted SSO identity governs operations across stale sessions and upgrades."""

from contextlib import asynccontextmanager
import json
from unittest.mock import AsyncMock
import httpx
import pytest
from fastapi import HTTPException
from app.config import settings
from app.models import CurrentUser
from app.routers import auth
from app.services import litellm, organization_store as store, organization_sync as sync
from tests.test_hierarchy_email import hierarchy


@pytest.fixture
def identity(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "organization_hierarchy", hierarchy())
    monkeypatch.setattr(settings, "local_users_db_path", str(tmp_path / "lifecycle.db"))
    sync._locks.clear()
    store.remember("subject", "alice@example.com", "sso", [])
    return hierarchy().resolve("subject", [], email="alice@example.com", source="sso")


@pytest.mark.asyncio
async def test_key_creation_uses_persisted_email_and_policy(monkeypatch, identity):
    async def synchronized(record):
        assert record["email"] == "alice@example.com"
        assert sync.resolve_identity(record) == identity
        return identity

    monkeypatch.setattr(sync, "synchronize", synchronized)
    monkeypatch.setattr(litellm, "list_user_keys", AsyncMock(return_value=[]))
    generated = AsyncMock(return_value={"key": "test-only-key"})
    monkeypatch.setattr(sync.upstream, "generate_key", generated)
    monkeypatch.setattr(sync.key_policy, "normalize_individual_caps", AsyncMock())
    await sync.generate_key("subject", "stale@example.com", None)
    assert generated.await_args.args == ("subject", "alice@example.com", identity.team_id)
    assert generated.await_args.kwargs["max_budget"] == 100


@pytest.mark.asyncio
async def test_admin_guard_and_personal_policy_use_stored_identity(monkeypatch, identity):
    key = {"user_id": "subject", "team_id": identity.team_id, "max_budget": 100, "budget_duration": "30d", "spend": 17}
    monkeypatch.setattr(litellm, "get_key_info", AsyncMock(return_value=key))
    with pytest.raises(HTTPException) as error:
        await sync.guard_key("test-key", {}, use_key_budget_only=True)
    assert error.value.status_code == 409
    policy = await sync.personal_policy(CurrentUser(user_id="subject", email="stale@example.com", auth_source="sso"), [key])
    assert policy["path"][-1] == "squad1"
    assert policy["spend"] == 17
    assert policy["sync_error"] is None


@pytest.mark.asyncio
async def test_first_authenticated_login_creates_actual_subject_without_key(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "local_users_db_path", str(tmp_path / "first.db"))
    monkeypatch.setattr(settings, "organization_hierarchy", hierarchy())
    monkeypatch.setattr(settings, "generic_authorization_endpoint", "")
    monkeypatch.setattr(settings, "oidc_group_team_mapping", {})
    monkeypatch.setattr(settings, "oidc_require_team_mapping", False)
    monkeypatch.setattr(settings, "sso_default_team_id", "")
    monkeypatch.setattr(settings, "inherit_litellm_admin", False)
    monkeypatch.setattr(auth.oidc_svc, "exchange_code", AsyncMock(return_value={"id_token": "token"}))
    monkeypatch.setattr(auth.oidc_svc, "verify_id_token", AsyncMock(return_value={"sub": "new-subject", "email": "Alice@Example.com"}))
    monkeypatch.setattr(sync, "synchronize_user", AsyncMock(return_value=None))
    writes = []

    def handler(request):
        if request.method == "GET":
            assert request.url.path == "/user/info"
            return httpx.Response(404)
        assert request.url.path == "/user/new"
        writes.append(json.loads(request.content))
        return httpx.Response(200, json={"user_id": "new-subject"})

    @asynccontextmanager
    async def connection():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            yield client

    monkeypatch.setattr(litellm, "_client", connection)
    state = auth.oidc_svc.generate_state("oidc")
    assert (await auth.callback("code", state, state_cookie=state)).status_code == 307
    assert writes == [{"user_id": "new-subject", "user_email": "alice@example.com", "auto_create_key": False}]
    assert store.get("new-subject")["auth_source"] == "sso"
    from app.services import local_users

    with local_users.connect() as db:
        assert db.execute("SELECT name FROM sqlite_master WHERE name='sso_reservations'").fetchone() is None
