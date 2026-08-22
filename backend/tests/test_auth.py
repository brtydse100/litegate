from unittest.mock import AsyncMock, patch
from http.cookies import SimpleCookie

import jwt
import pytest
from fastapi import HTTPException
from jwt import InvalidTokenError
from starlette.requests import Request

from app.dependencies import decode_portal_token, get_current_user
from app.config import settings
from app.routers import auth


def _response_cookie(response, name: str) -> str:
    cookies = SimpleCookie()
    for header_name, value in response.raw_headers:
        if header_name == b"set-cookie":
            cookies.load(value.decode("latin-1"))
    return cookies[name].value


def test_portal_token_round_trip():
    token = jwt.encode(
        {
            "sub": "user-1",
            "email": "user@example.com",
            "role": "admin",
            "auth_source": "sso",
            "team_ids": ["team-primary", "team-secondary"],
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    user = decode_portal_token(token)
    assert user.user_id == "user-1"
    assert user.is_admin is True
    assert user.team_ids == ["team-primary", "team-secondary"]


def test_portal_token_requires_subject():
    token = jwt.encode({"email": "nobody@example.com"}, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    with pytest.raises(InvalidTokenError):
        decode_portal_token(token)


def test_session_cookie_authenticates_without_authorization_header():
    token = auth._make_jwt("cookie-user", "cookie@example.com")
    user = get_current_user(credentials=None, session_cookie=token)
    assert user.user_id == "cookie-user"
    assert user.email == "cookie@example.com"


@pytest.mark.asyncio
async def test_sso_callback_syncs_mapped_teams_and_embeds_them_in_token(monkeypatch):
    state = auth.oidc_svc.generate_state()
    monkeypatch.setattr(auth.settings, "oidc_groups_claim", "groups")
    monkeypatch.setattr(auth.settings, "admin_groups", "ENGINEERING")
    monkeypatch.setattr(
        auth.settings,
        "oidc_group_team_mapping",
        {"Engineering": ["team-primary", "team-shared"]},
    )
    monkeypatch.setattr(auth.settings, "oidc_require_team_mapping", True)

    with (
        patch.object(auth.oidc_svc, "validate_state", return_value=True),
        patch.object(auth.oidc_svc, "exchange_code", new=AsyncMock(return_value={"id_token": "id"})),
        patch.object(
            auth.oidc_svc,
            "verify_id_token",
            new=AsyncMock(
                return_value={
                    "sub": "oidc-user",
                    "email": "user@example.com",
                    "groups": ["engineering"],
                }
            ),
        ),
        patch.object(auth.llm, "ensure_user_exists", new=AsyncMock(return_value={"user_id": "oidc-user"})),
        patch.object(auth.llm, "sync_user_team_memberships", new=AsyncMock()) as sync,
    ):
        response = await auth.callback("code", state, state_cookie=state)

    sync.assert_awaited_once_with(
        "oidc-user", "user@example.com", ["team-primary", "team-shared"]
    )
    assert "#token=" not in response.headers["location"]
    token = _response_cookie(response, "litegate_session")
    user = decode_portal_token(token)
    assert user.is_admin is True
    assert user.team_ids == ["team-primary", "team-shared"]


@pytest.mark.asyncio
async def test_sso_callback_rejects_user_without_required_team_mapping(monkeypatch):
    state = auth.oidc_svc.generate_state()
    monkeypatch.setattr(auth.settings, "oidc_group_team_mapping", {"Engineering": "team-eng"})
    monkeypatch.setattr(auth.settings, "oidc_require_team_mapping", True)

    with (
        patch.object(auth.oidc_svc, "validate_state", return_value=True),
        patch.object(auth.oidc_svc, "exchange_code", new=AsyncMock(return_value={"id_token": "id"})),
        patch.object(
            auth.oidc_svc,
            "verify_id_token",
            new=AsyncMock(return_value={"sub": "user", "groups": ["Finance"]}),
        ),
        patch.object(auth.llm, "ensure_user_exists", new=AsyncMock()) as ensure,
    ):
        with pytest.raises(HTTPException) as exc:
            await auth.callback("code", state, state_cookie=state)

    assert exc.value.status_code == 403
    ensure.assert_not_awaited()


@pytest.mark.asyncio
async def test_sso_callback_fails_closed_when_mapped_user_cannot_be_provisioned(monkeypatch):
    state = auth.oidc_svc.generate_state()
    monkeypatch.setattr(auth.settings, "oidc_group_team_mapping", {"Engineering": "team-eng"})
    monkeypatch.setattr(auth.settings, "oidc_require_team_mapping", False)

    with (
        patch.object(auth.oidc_svc, "validate_state", return_value=True),
        patch.object(auth.oidc_svc, "exchange_code", new=AsyncMock(return_value={"id_token": "id"})),
        patch.object(
            auth.oidc_svc,
            "verify_id_token",
            new=AsyncMock(return_value={"sub": "user", "groups": ["Engineering"]}),
        ),
        patch.object(auth.llm, "ensure_user_exists", new=AsyncMock(return_value=None)),
        patch.object(auth.llm, "sync_user_team_memberships", new=AsyncMock()) as sync,
    ):
        with pytest.raises(HTTPException) as exc:
            await auth.callback("code", state, state_cookie=state)

    assert exc.value.status_code == 502
    sync.assert_not_awaited()


@pytest.mark.asyncio
async def test_sso_callback_rejects_state_from_another_browser():
    with patch.object(auth.oidc_svc, "validate_state", return_value=True):
        with pytest.raises(HTTPException) as exc:
            await auth.callback("code", "signed-state", state_cookie="different-state")
    assert exc.value.status_code == 400


def test_oidc_state_carries_a_verifiable_nonce():
    state = auth.oidc_svc.generate_state()
    assert auth.oidc_svc.validate_state(state) is True
    assert len(auth.oidc_svc.state_nonce(state)) >= 16


@pytest.mark.asyncio
async def test_local_login_uses_httponly_session_cookie(monkeypatch):
    monkeypatch.setattr(auth.settings, "local_auth_username", "admin")
    monkeypatch.setattr(auth.settings, "local_auth_password", "strong-test-password")
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/auth/local",
            "headers": [],
            "client": ("192.0.2.44", 12345),
            "server": ("testserver", 80),
            "scheme": "http",
        }
    )
    with patch.object(auth.llm, "ensure_user_exists", new=AsyncMock(return_value={})):
        response = await auth.local_login(request, "admin", "strong-test-password")

    assert response.body == b'{"authenticated":true}'
    assert _response_cookie(response, "litegate_session")
    session_header = next(
        value.decode("latin-1")
        for name, value in response.raw_headers
        if name == b"set-cookie" and value.startswith(b"litegate_session=")
    )
    assert "HttpOnly" in session_header
    assert "SameSite=lax" in session_header
