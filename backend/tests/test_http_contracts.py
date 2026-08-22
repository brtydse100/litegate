"""Black-box HTTP contracts for security- and compatibility-sensitive flows.

These tests exercise the ASGI application at its public boundary. They avoid
calling router functions directly so refactors can change private helpers while
the observable product behavior stays fixed.
"""

from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, urlencode, urlparse

import httpx
import pytest

from app.main import app
from app.rate_limit import _key_ops, _login_failures
from app.routers import auth


def _client(*, address: str = "192.0.2.10") -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app, client=(address, 12345))
    return httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
        follow_redirects=False,
    )


@pytest.fixture(autouse=True)
def clear_login_throttle():
    _login_failures.clear()
    _key_ops.clear()


@pytest.mark.asyncio
async def test_password_session_contract_is_httponly_usable_and_revocable(monkeypatch):
    monkeypatch.setattr(auth.settings, "local_auth_username", "admin")
    monkeypatch.setattr(auth.settings, "local_auth_password", "strong-test-password")
    monkeypatch.setattr(auth.settings, "local_users_enabled", False)

    with patch.object(auth.llm, "ensure_user_exists", new=AsyncMock(return_value={})):
        async with _client() as client:
            login = await client.post(
                "/api/auth/local",
                data={"username": "admin", "password": "strong-test-password"},
            )

            assert login.status_code == 200
            assert login.json() == {"authenticated": True}
            assert "token" not in login.text.casefold()
            session_header = login.headers["set-cookie"]
            assert session_header.startswith("litegate_session=")
            assert "HttpOnly" in session_header
            assert "SameSite=lax" in session_header

            me = await client.get("/api/auth/me")
            assert me.status_code == 200
            assert me.json() == {
                "user_id": "local:admin",
                "email": "admin@local",
                "role": "admin",
                "auth_source": "local",
                "team_ids": [],
            }

            logout = await client.post(
                "/api/auth/logout",
                headers={"Origin": "http://testserver"},
            )
            assert logout.status_code == 200
            assert (await client.get("/api/auth/me")).status_code == 401


@pytest.mark.asyncio
async def test_password_failures_are_throttled_at_the_http_boundary(monkeypatch):
    monkeypatch.setattr(auth.settings, "local_auth_username", "admin")
    monkeypatch.setattr(auth.settings, "local_auth_password", "strong-test-password")
    monkeypatch.setattr(auth.settings, "local_users_enabled", False)

    async with _client(address="192.0.2.20") as client:
        for _ in range(8):
            response = await client.post(
                "/api/auth/local",
                data={"username": "admin", "password": "wrong-password"},
            )
            assert response.status_code == 401

        blocked = await client.post(
            "/api/auth/local",
            data={"username": "admin", "password": "strong-test-password"},
        )

    assert blocked.status_code == 429
    assert int(blocked.headers["retry-after"]) > 0


@pytest.mark.asyncio
async def test_oidc_contract_binds_browser_state_and_keeps_session_out_of_url(monkeypatch):
    monkeypatch.setattr(auth.settings, "oidc_issuer_url", "https://idp.example")
    monkeypatch.setattr(auth.settings, "root_url", "http://testserver")
    monkeypatch.setattr(auth.settings, "admin_groups", "Engineering")
    monkeypatch.setattr(auth.settings, "oidc_group_team_mapping", {"Engineering": "team-eng"})
    monkeypatch.setattr(auth.settings, "oidc_require_team_mapping", True)

    async def authorization_url(state: str) -> str:
        return "https://idp.example/authorize?" + urlencode({"state": state})

    claims = {
        "sub": "oidc-user",
        "email": "oidc@example.com",
        "groups": ["engineering"],
    }
    with (
        patch.object(auth.oidc_svc, "get_authorization_url", side_effect=authorization_url),
        patch.object(auth.oidc_svc, "exchange_code", new=AsyncMock(return_value={"id_token": "id-token"})),
        patch.object(auth.oidc_svc, "verify_id_token", new=AsyncMock(return_value=claims)) as verify,
        patch.object(auth.llm, "ensure_user_exists", new=AsyncMock(return_value={"user_id": "oidc-user"})),
        patch.object(auth.llm, "sync_user_team_memberships", new=AsyncMock()) as sync,
    ):
        async with _client() as client:
            start = await client.get("/api/auth/login")
            assert start.status_code in {302, 307}
            state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]
            assert state
            assert client.cookies.get("litegate_oidc_state") == state
            assert "HttpOnly" in start.headers["set-cookie"]

            callback = await client.get(
                "/api/auth/callback",
                params={"code": "authorization-code", "state": state},
            )
            assert callback.status_code in {302, 307}
            assert callback.headers["location"] == "http://testserver/auth/callback"
            assert "token=" not in callback.headers["location"]
            assert client.cookies.get("litegate_session")
            assert client.cookies.get("litegate_oidc_state") is None

            me = await client.get("/api/auth/me")
            assert me.status_code == 200
            assert me.json()["team_ids"] == ["team-eng"]
            assert me.json()["role"] == "admin"

    expected_nonce = verify.await_args.kwargs["expected_nonce"]
    assert isinstance(expected_nonce, str) and len(expected_nonce) >= 16
    sync.assert_awaited_once_with("oidc-user", "oidc@example.com", ["team-eng"])


@pytest.mark.asyncio
async def test_key_deletion_contract_keeps_secret_in_json_body():
    token = auth._make_jwt("user-1", "user@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    with (
        patch("app.routers.keys.llm.list_user_keys", new=AsyncMock(return_value=[{"token": "sk-owned"}])),
        patch("app.routers.keys.llm.delete_key", new=AsyncMock()) as delete,
    ):
        async with _client() as client:
            response = await client.request(
                "DELETE",
                "/api/keys",
                json={"key": "sk-owned"},
                headers=headers,
            )

    assert response.status_code == 200
    assert response.request.url.path == "/api/keys"
    assert "sk-owned" not in str(response.request.url)
    delete.assert_awaited_once_with("sk-owned")


@pytest.mark.asyncio
async def test_non_admin_bulk_edit_is_denied_before_litellm_is_called():
    token = auth._make_jwt("user-1", "user@example.com")
    with patch("app.routers.api_v1.llm.update_key", new=AsyncMock()) as update:
        async with _client() as client:
            response = await client.patch(
                "/api/v1/keys/bulk",
                json={"keys": ["sk-owned"], "settings": {"rpm_limit": 25}},
                headers={"Authorization": f"Bearer {token}"},
            )

    assert response.status_code == 403
    update.assert_not_awaited()


@pytest.mark.asyncio
async def test_non_admin_team_management_is_denied_before_litellm_is_called():
    token = auth._make_jwt("user-1", "user@example.com")
    with patch("app.routers.api_v1.llm.list_teams", new=AsyncMock()) as list_teams:
        async with _client() as client:
            response = await client.get(
                "/api/v1/teams",
                headers={"Authorization": f"Bearer {token}"},
            )

    assert response.status_code == 403
    list_teams.assert_not_awaited()
