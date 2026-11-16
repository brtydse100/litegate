"""Public regressions for the second review of hierarchy adoption."""

import asyncio
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import HTTPException

from app.config import settings
from app.main import app
from app.organization import OrganizationHierarchy
from app.rate_limit import _key_ops
from app.routers.auth import _make_jwt
from app.services import key_budgets, litellm, organization_client as upstream
from app.services import organization_sync as sync, organization_store as store, organization_reports as reports
from tests.test_organization_lowest_team import native


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/api/keys", "/api/keys/key-old", "/api/v1/keys"])
async def test_user_cannot_delete_exhausted_key_and_recreate_allowance(native, path):
    _, state = native
    await sync.remember("alice", "alice@example.com", "sso", ["squad1"])
    state["keys"]["key-old"]["spend"] = 100
    _key_ops.clear()
    token = _make_jwt("alice", "alice@example.com", "user", "sso")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test", headers={"Authorization": f"Bearer {token}"}
    ) as client:
        deleted = await client.request("DELETE", path, json={"key": "key-old"})
        created = await client.post("/api/keys")
    assert deleted.status_code == 403
    assert created.status_code == 409
    assert state["keys"]["key-old"]["spend"] == 100


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "controls",
    [
        {"blocked": True},
        {"models": ["model-a"]},
        {"rpm_limit": 2},
        {"mcp_rpm_limit": {"server": 1}},
        {"metadata": {"mcp_rpm_limit": {"server": 1}}},
        {"metadata": {"guardrails": ["mandatory"]}},
        {"metadata": {"model_rpm_limit": {"model-a": 1}}},
        {"metadata": {"prompts": ["system-prompt"]}},
    ],
)
async def test_restricted_nonancestor_source_team_cannot_be_silently_dropped(native, controls):
    _, state = native
    state["teams"]["legacy"] = {"team_id": "legacy", "max_budget": 500, **controls}
    state["keys"]["key-old"]["team_id"] = "legacy"
    with pytest.raises(HTTPException) as error:
        await sync.remember("alice", "alice@example.com", "sso", ["squad1"])
    assert error.value.status_code == 409
    assert state["keys"]["key-old"]["team_id"] == "legacy"
    assert store.get("alice")["sync_error"]


@pytest.mark.asyncio
async def test_rotation_preserves_advanced_policy_controls(native, monkeypatch):
    _, state = native
    monkeypatch.setattr(settings, "organization_hierarchy", OrganizationHierarchy())
    controls = {"mcp_rpm_limit": {"server": 1}, "tag_rpm_limit": {"tag": 2}, "policies": ["safety"], "prompts": ["system-prompt"]}
    state["keys"]["key-old"].update(controls)
    result = await sync.rotate_key("alice", "alice@example.com", None, key_alias="replacement")
    assert {key: state["keys"][result["key"]].get(key) for key in controls} == controls


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/api/keys", "/api/v1/keys"])
async def test_administrator_can_permanently_delete_with_audit(native, path):
    from app.services import audit

    _, state = native
    _key_ops.clear()
    token = _make_jwt("alice", "alice@example.com", "admin", "sso")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test", headers={"Authorization": f"Bearer {token}"}
    ) as client:
        deleted = await client.request("DELETE", path, json={"key": "key-old"})
    assert deleted.status_code == 200
    assert "key-old" not in state["keys"]
    assert audit.list_events()[0]["action"] == "key.delete"


@pytest.mark.asyncio
async def test_additional_budget_windows_require_assisted_rotation(native, monkeypatch):
    _, state = native
    monkeypatch.setattr(settings, "organization_hierarchy", OrganizationHierarchy())
    state["keys"]["key-old"]["budget_limits"] = [{"max_budget": 50, "budget_duration": "1d"}]
    with pytest.raises(HTTPException) as error:
        await sync.rotate_key("alice", "alice@example.com", None, key_alias="replacement")
    assert error.value.status_code == 409
    assert not any(path in {"/key/generate", "/key/update", "/key/delete"} for _, path, _ in state["calls"])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change",
    [
        {"blocked": True},
        {"budget_limits": [{"max_budget": 1, "budget_duration": "1d"}]},
        {"model_max_budget": {"model": {"budget_limit": 1, "time_period": "1d"}}},
    ],
)
async def test_external_policy_change_during_rotation_keeps_original(native, monkeypatch, change):
    _, state = native
    monkeypatch.setattr(settings, "organization_hierarchy", OrganizationHierarchy())
    state["keys"]["key-old"]["blocked"] = False
    generate = sync._generate_key

    async def concurrent_external_admin(*args, **kwargs):
        result = await generate(*args, **kwargs)
        state["keys"]["key-old"].update(change)
        return result

    monkeypatch.setattr(sync, "_generate_key", concurrent_external_admin)
    with pytest.raises(HTTPException) as error:
        await sync.rotate_key("alice", "alice@example.com", None, key_alias="replacement")
    assert error.value.status_code == 409
    assert set(state["keys"]) == {"key-old"}
    assert all(state["keys"]["key-old"][field] == value for field, value in change.items())


@pytest.mark.asyncio
async def test_admin_policy_update_waits_for_rotation_and_rechecks_original(native):
    _, state = native
    async with sync.lock_for("user", "alice"):
        task = asyncio.create_task(key_budgets.update_key("key-old", {"blocked": True}))
        try:
            await asyncio.sleep(0.02)
            assert not task.done(), "administrator policy mutations must share the rotation lock"
            state["keys"].pop("key-old")
        finally:
            if task.done():
                await task
    with pytest.raises(HTTPException) as error:
        await asyncio.wait_for(task, 2)
    assert error.value.status_code == 409


@pytest.mark.asyncio
async def test_ambiguous_discovery_is_visible_then_clears_when_resolved(native, monkeypatch):
    _, state = native
    hierarchy = OrganizationHierarchy.model_validate(
        {
            "levels": [
                {
                    "name": "Team",
                    "groups": [
                        {
                            "members": [
                                {
                                    "name": "Engineering",
                                    "litellmTeamId": "engineering",
                                    "userIds": ["alice@example.com"],
                                    "budget": {"perUser": 100},
                                }
                            ]
                        }
                    ],
                }
            ]
        }
    )
    monkeypatch.setattr(settings, "organization_hierarchy", hierarchy)
    original = litellm.get_user

    async def user(user_id):
        if user_id == "alice@example.com":
            return None
        result = await original(user_id)
        result["user_info"].update(user_id=user_id, user_email="alice@example.com")
        return result

    monkeypatch.setattr(litellm, "get_user", user)
    users = [{"user_id": name, "user_email": "alice@example.com"} for name in ("alice", "other")]
    request = AsyncMock(return_value={"users": users, "page": 1, "page_size": 100, "total": 2, "total_pages": 1})
    monkeypatch.setattr(upstream, "request", request)
    monkeypatch.setattr(upstream, "sync_root", AsyncMock(return_value={}))
    monkeypatch.setattr(sync.key_policy, "finish_team", AsyncMock())
    monkeypatch.setattr(sync.key_policy, "normalize_individual_caps", AsyncMock())
    await sync.reconcile()
    overview = await reports.children(None)
    assert overview["total_users"] == 0
    assert any("multiple" in issue["error"] and issue["user_id"] == "alice@example.com" for issue in overview["issues"])
    # Resolution retries without an operator triggering any special migration.
    request.return_value = {"users": users[:1], "page": 1, "page_size": 100, "total": 1, "total_pages": 1}
    # Restore actual policy calls now that discovery may adopt the user.
    monkeypatch.setattr(sync, "sync_identity", AsyncMock())
    await sync.reconcile()
    assert not (await reports.children(None))["issues"]
