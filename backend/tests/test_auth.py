from unittest.mock import AsyncMock, patch

import jwt
import pytest
from fastapi import HTTPException
from jwt import InvalidTokenError

from app.dependencies import decode_portal_token
from app.config import settings
from app.routers import auth


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


@pytest.mark.asyncio
async def test_sso_callback_syncs_mapped_teams_and_embeds_them_in_token(monkeypatch):
    monkeypatch.setattr(auth.settings, "oidc_groups_claim", "groups")
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
        response = await auth.callback("code", "state")

    sync.assert_awaited_once_with(
        "oidc-user", "user@example.com", ["team-primary", "team-shared"]
    )
    token = response.headers["location"].split("#token=", 1)[1]
    assert decode_portal_token(token).team_ids == ["team-primary", "team-shared"]


@pytest.mark.asyncio
async def test_sso_callback_rejects_user_without_required_team_mapping(monkeypatch):
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
            await auth.callback("code", "state")

    assert exc.value.status_code == 403
    ensure.assert_not_awaited()


@pytest.mark.asyncio
async def test_sso_callback_fails_closed_when_mapped_user_cannot_be_provisioned(monkeypatch):
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
            await auth.callback("code", "state")

    assert exc.value.status_code == 502
    sync.assert_not_awaited()
