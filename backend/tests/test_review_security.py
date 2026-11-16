"""Public authentication and audit regressions from the repository review."""

from unittest.mock import AsyncMock

import httpx
import pytest

from app.config import settings
from app.main import app
from app.rate_limit import _key_ops, _login_failures
from app.routers import auth
from app.services import audit, litellm, local_users


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "local_users_db_path", str(tmp_path / "review.db"))
    from app.services import database as database_service

    database_service.initialize()
    monkeypatch.setattr(settings, "local_auth_username", "bootstrap")
    monkeypatch.setattr(settings, "local_auth_password", "bootstrap-review-password")
    monkeypatch.setattr(settings, "local_users_enabled", True)
    monkeypatch.setattr(litellm, "ensure_user_exists", AsyncMock(return_value={}))
    _key_ops.clear()
    _login_failures.clear()


def client(**kwargs):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test", **kwargs)


def collision(monkeypatch):
    with monkeypatch.context() as previous:
        previous.setattr(settings, "local_auth_username", None)
        local_users.create_user("Bootstrap", "ordinary@example.com", "ordinary-review-password", "user")


@pytest.mark.asyncio
async def test_existing_database_collision_cannot_authenticate_as_bootstrap(monkeypatch):
    collision(monkeypatch)
    async with client() as browser:
        response = await browser.post("/api/auth/local", data={"username": "Bootstrap", "password": "ordinary-review-password"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_old_collision_sessions_fail_closed(monkeypatch):
    collision(monkeypatch)
    token = auth._make_jwt("local:bootstrap", "ordinary@example.com", "admin", "local")
    async with client(headers={"Authorization": f"Bearer {token}"}) as browser:
        assert (await browser.get("/api/auth/me")).status_code == 401
        assert (await browser.get("/api/v1/users")).status_code == 401


@pytest.mark.asyncio
async def test_bootstrap_login_is_distinct_and_configuration_change_revokes_it(monkeypatch):
    collision(monkeypatch)
    async with client() as browser:
        response = await browser.post("/api/auth/local", data={"username": "bootstrap", "password": "bootstrap-review-password"})
        assert response.status_code == 200
        me = (await browser.get("/api/auth/me")).json()
        assert me["role"] == "admin" and me["auth_source"] == "bootstrap"
        monkeypatch.setattr(settings, "local_auth_username", "different")
        assert (await browser.get("/api/auth/me")).status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize("prefix", ["/api/users", "/api/v1/users"])
async def test_bootstrap_username_reserved_on_both_account_routes(prefix):
    token = auth._make_jwt("operator", "operator@example.com", "admin")
    async with client(headers={"Authorization": f"Bearer {token}"}) as browser:
        response = await browser.post(prefix, json={"username": "BOOTSTRAP", "email": "other@example.com", "password": "ordinary-password"})
    assert response.status_code == 409
    assert local_users.get_user("bootstrap") is None


@pytest.mark.asyncio
@pytest.mark.parametrize("prefix", ["/api/users", "/api/v1/users"])
async def test_account_mutations_are_audited_on_both_route_families(prefix):
    token = auth._make_jwt("operator", "operator@example.com", "admin")
    async with client(headers={"Authorization": f"Bearer {token}"}) as browser:
        created = await browser.post(prefix, json={"username": "reviewer", "email": "person@example.com", "password": "ordinary-password"})
        assert created.status_code == 201
        updated = await browser.patch(f"{prefix}/reviewer", json={"role": "admin"})
        assert updated.status_code == 200
    events = audit.list_events()
    assert [event["action"] for event in events] == ["local_user.update", "local_user.create"]
    assert all(event["actor_id"] == "operator" and event["target"] == "local:reviewer" for event in events)
    assert "ordinary-password" not in str(events)
