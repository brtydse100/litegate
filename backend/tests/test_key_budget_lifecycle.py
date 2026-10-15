"""Migration remains safe across regeneration and verified native rosters."""

import asyncio
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import HTTPException

from tests.test_key_budget_policy import actor, upstream
from app.config import settings
from app.dependencies import get_current_user
from app.main import app
from app.models import CurrentUser
from app.organization import OrganizationHierarchy
from app.services import key_budgets, litellm, organization_store, organization_sync


@pytest.mark.asyncio
@pytest.mark.parametrize("ignore_budget", [False, True])
async def test_migrated_key_regeneration_keeps_cap_and_spend_or_revokes_replacement(upstream, monkeypatch, ignore_budget):
    actor("admin")
    monkeypatch.setattr(settings, "key_max_budget", None)
    monkeypatch.setattr(settings, "key_budget_duration", None)
    monkeypatch.setattr(settings, "save_api_keys_in_db", False)
    upstream["ignore_replacement_budget"] = ignore_budget
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(user_id="alice", email="alice@example.com")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as browser:
        migrated = await browser.patch("/api/v1/keys/bulk", json={"keys": ["key-1"], "settings": {"max_budget": 100}, "use_key_budget_only": True})
        assert migrated.json()["updated"] == 1
        rotated = await browser.post("/api/keys/regenerate")
    if ignore_budget:
        assert rotated.status_code == 502
        assert upstream["deleted"] == ["sk-replacement"]
    else:
        assert rotated.status_code == 201
        assert upstream["generated"]["max_budget"] == 100
        assert upstream["generated"]["budget_duration"] == "30d"
        assert upstream["generated"]["spend"] == 20
        assert upstream["deleted"] == ["key-1"]


@pytest.mark.asyncio
@pytest.mark.parametrize("roster", [[{"user_id": "alice", "role": "user"}], [], [{"user_id": "alice", "budget_id": "unresolved"}]])
async def test_roster_only_migration_requires_verified_uncapped_member(upstream, roster):
    actor("admin")
    upstream["memberships"] = []
    upstream["team_info"] = {"members_with_roles": roster}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as browser:
        response = await browser.patch("/api/v1/keys/bulk", json={"keys": ["key-1"], "use_key_budget_only": True})
    valid = roster == [{"user_id": "alice", "role": "user"}]
    assert response.json()["updated"] == int(valid)
    assert upstream["user_budget"] == (None if valid else 25)


@pytest.mark.asyncio
async def test_migration_waits_for_owner_lock_and_rechecks_key_ownership(monkeypatch):
    info = AsyncMock(return_value={"user_id": "alice", "max_budget": 100})
    monkeypatch.setattr(litellm, "get_key_info", info)
    changed = AsyncMock()
    monkeypatch.setattr(litellm, "update_key", changed)
    lock = organization_sync.lock_for("user", "alice")
    async with lock:
        task = asyncio.create_task(key_budgets.update_key("key-1", {}, use_key_budget_only=True))
        try:
            await asyncio.sleep(0)
            assert info.await_count == 1
            assert not task.done()
            info.return_value = {"user_id": "someone-else", "max_budget": 100}
        finally:
            if info.await_count != 1:
                task.cancel()
    with pytest.raises(HTTPException) as error:
        await asyncio.wait_for(task, 2)
    assert getattr(error.value, "status_code", None) == 409
    changed.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("mapped", [False, True])
async def test_managed_team_fallback_does_not_exempt_an_unmapped_owner(monkeypatch, mapped):
    tree = OrganizationHierarchy.model_validate(
        {
            "levels": [
                {"name": "Team", "groups": [{"members": [{"name": "Platform", "litellmTeamId": "platform", "userIds": ["alice"] if mapped else []}]}]}
            ]
        }
    )
    monkeypatch.setattr(settings, "organization_hierarchy", tree)
    monkeypatch.setattr(organization_store, "get", lambda _: None)
    info = {"user_id": "alice", "team_id": "platform", "max_budget": 100, "budget_duration": "30d"}
    monkeypatch.setattr(litellm, "get_key_info", AsyncMock(return_value=info))
    update = AsyncMock()
    monkeypatch.setattr(litellm, "update_key", update)
    await key_budgets.preserve_rotation_budget("alice", [{"max_budget": 100, "budget_duration": "30d"}], "replacement")
    assert update.await_count == (0 if mapped else 1)


@pytest.mark.asyncio
@pytest.mark.parametrize("wrong_read", [0, 1])
async def test_rotation_verifies_expected_owner_before_and_after_budget_update(monkeypatch, wrong_read):
    correct = {"user_id": "alice", "max_budget": 100, "budget_duration": "30d"}
    values = [dict(correct), dict(correct)]
    values[wrong_read]["user_id"] = "other"
    monkeypatch.setattr(litellm, "get_key_info", AsyncMock(side_effect=values))
    monkeypatch.setattr(organization_store, "get", lambda _: None)
    monkeypatch.setattr(litellm, "update_key", AsyncMock())
    with pytest.raises(HTTPException) as error:
        await key_budgets.preserve_rotation_budget("alice", [{"max_budget": 100, "budget_duration": "30d"}], "replacement")
    assert getattr(error.value, "status_code", None) == 502
