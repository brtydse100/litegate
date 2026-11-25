"""People are switched to LiteLLM's view-only role; administrators never are."""

from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.services import litellm, litellm_roles, local_users, organization_store, sso_legacy


def audits() -> int:
    with local_users.connect() as db:
        return db.execute("SELECT count(*) FROM audit_events WHERE action='litellm.user_role_restricted'").fetchone()[0]


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["internal_user", None])
async def test_self_service_user_is_switched_to_viewer(monkeypatch, role):
    update = AsyncMock()
    monkeypatch.setattr(litellm, "update_user_role", update)
    user = {"user_id": "ann", "user_info": {"user_role": role}}
    assert await litellm_roles.restrict("ann", user) is True
    update.assert_awaited_once_with("ann", "internal_user_viewer")
    assert user["user_info"]["user_role"] == "internal_user_viewer"
    assert audits() == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["proxy_admin", "proxy_admin_viewer", "internal_user_viewer", "team"])
async def test_other_roles_are_left_alone(monkeypatch, role):
    update = AsyncMock()
    monkeypatch.setattr(litellm, "update_user_role", update)
    assert await litellm_roles.restrict("ann", {"user_info": {"user_role": role}}) is False
    update.assert_not_awaited()


@pytest.mark.asyncio
async def test_failed_switch_never_blocks_sign_in(monkeypatch):
    monkeypatch.setattr(litellm, "update_user_role", AsyncMock(side_effect=HTTPException(502, "down")))
    monkeypatch.setattr(litellm, "get_user", AsyncMock(return_value={"user_info": {"user_role": "internal_user"}}))
    user = await litellm.ensure_user_exists("ann", "ann@example.com")
    assert user == {"user_info": {"user_role": "internal_user"}}
    assert audits() == 0


@pytest.mark.asyncio
async def test_existing_user_is_switched_at_sign_in(monkeypatch):
    update = AsyncMock()
    monkeypatch.setattr(litellm, "update_user_role", update)
    monkeypatch.setattr(litellm, "get_user", AsyncMock(return_value={"user_info": {"user_role": "internal_user"}}))
    await litellm.ensure_user_exists("ann", "ann@example.com")
    update.assert_awaited_once_with("ann", "internal_user_viewer")


@pytest.mark.asyncio
async def test_startup_pass_covers_local_and_organization_people(monkeypatch):
    local_users.create_user("bob", "bob@example.com", "synthetic-password-1")
    organization_store.remember("carol", "carol@example.com", "sso", [])
    roles = {"local:bob": "internal_user", "carol": "proxy_admin"}
    monkeypatch.setattr(litellm, "get_user", AsyncMock(side_effect=lambda user_id: {"user_info": {"user_role": roles[user_id]}}))
    update = AsyncMock()
    monkeypatch.setattr(litellm, "update_user_role", update)

    assert await litellm_roles.restrict_known_users() == 1
    update.assert_awaited_once_with("local:bob", "internal_user_viewer")


@pytest.mark.asyncio
async def test_startup_pass_failure_is_contained(monkeypatch):
    monkeypatch.setattr(litellm_roles, "known_user_ids", lambda: (_ for _ in ()).throw(RuntimeError("database locked")))
    assert await litellm_roles.restrict_known_users() == 0


@pytest.mark.parametrize("role", ["internal_user", "internal_user_viewer"])
def test_legacy_sso_ownership_accepts_the_viewer_role(role):
    reservation = {"user_id": "u", "email": "u@example.com", "ownership_token": "t"}
    user = {"user_id": "u", "user_email": "u@example.com", "user_role": role, "metadata": {"litegate_organization_owner": "t"}}
    sso_legacy._verify_owned(user, reservation)
