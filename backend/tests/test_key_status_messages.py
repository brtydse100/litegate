"""Key-page status distinguishes missing sign-in context, moves and real failures."""

from unittest.mock import AsyncMock

import pytest

from app.config import settings
from app.services import litellm, organization_client as upstream, organization_store as store
from tests.test_organization_http import client, setup, token  # noqa: F401 - autouse hierarchy fixture


def managed_key(team_id: str) -> dict:
    return {"token": "hash", "team_id": team_id, "spend": 5, "max_budget": 50, "budget_duration": "30d"}


async def key_status(monkeypatch, team_id: str) -> dict:
    monkeypatch.setattr(litellm, "list_user_keys", AsyncMock(return_value=[managed_key(team_id)]))
    monkeypatch.setattr(litellm, "get_key_info", AsyncMock(return_value={"user_id": "u", "spend": 5}))
    monkeypatch.setattr(upstream, "team_info", AsyncMock(return_value={"team_memberships": []}))
    async with client() as browser:
        response = await browser.get("/api/keys", headers=token())
    assert response.status_code == 200
    return response.json()["keys"][0]


def squad_team() -> str:
    return settings.organization_hierarchy.resolve("u", ["squad1"]).team_id


@pytest.mark.asyncio
async def test_missing_sign_in_details_is_an_info_notice_not_a_removal(monkeypatch):
    # A database lost on restart: the session survives but its group claims do not.
    key = await key_status(monkeypatch, squad_team())
    assert key["policy_error"] is None
    assert "Sign out and sign in again" in key["policy_notice"]
    assert key["user_budget_available"] is True


@pytest.mark.asyncio
async def test_a_moved_user_is_told_where_and_keeps_their_current_budget(monkeypatch):
    store.remember("u", "u@example.com", "sso", ["squad1"])
    key = await key_status(monkeypatch, "engineering")
    assert key["policy_error"] is None
    target = " / ".join(settings.organization_hierarchy.resolve("u", ["squad1"]).path)
    assert key["policy_notice"] == f"You were moved to {target}. Your key moves there within about a minute."
    assert key["user_budget"] == 50


@pytest.mark.asyncio
async def test_a_removed_mapping_is_still_a_warning(monkeypatch):
    store.remember("u", "u@example.com", "sso", [])
    key = await key_status(monkeypatch, "engineering")
    assert key["policy_error"] == "Your organization mapping was removed; contact an administrator"
    assert key["policy_notice"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("enforced", [False, True])
async def test_key_replacement_availability_matches_the_backend_guard(monkeypatch, enforced):
    monkeypatch.setattr(settings, "hierarchical_budgets_enforced", enforced)
    store.remember("u", "u@example.com", "sso", ["squad1"])
    key = await key_status(monkeypatch, squad_team())
    # Enforced budgets reject replacing a managed key, so the page must not offer it.
    assert key["rotation_available"] is (not enforced)
