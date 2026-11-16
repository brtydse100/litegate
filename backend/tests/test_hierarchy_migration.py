"""Automatic adoption of existing credentials, including interrupted rollouts."""

import pytest
from fastapi import HTTPException

from app.config import settings
from app.organization import OrganizationHierarchy
from app.services import litellm, organization_store as store, organization_sync as sync
from tests.test_organization_lowest_team import native


def existing_installation(monkeypatch, state):
    tree = OrganizationHierarchy.model_validate(
        {
            "levels": [
                {
                    "name": "Division",
                    "groups": [
                        {
                            "members": [
                                {
                                    "name": "Engineering",
                                    "litellmTeamId": "engineering",
                                    "userIds": ["alice", "bob"],
                                    "budget": {"perUser": 100, "duration": "30d"},
                                }
                            ]
                        }
                    ],
                }
            ]
        }
    )
    monkeypatch.setattr(settings, "organization_hierarchy", tree)
    state["keys"]["key-bob"] = {**state["keys"]["key-old"], "token": "key-bob", "user_id": "bob", "spend": 13}
    state["keys"]["key-old"].update(models=["model-a"], rpm_limit=2, blocked=True)
    original = litellm.get_user

    async def user_info(user_id):
        result = await original(user_id)
        result["user_info"].update(user_id=user_id, user_email=f"{user_id}@example.com")
        return result

    monkeypatch.setattr(litellm, "get_user", user_info)


@pytest.mark.asyncio
async def test_first_reconciliation_adopts_all_existing_users_and_finishes_shared_cap_migration(native, monkeypatch):
    _, state = native
    existing_installation(monkeypatch, state)
    assert store.list_identities() == []
    await sync.reconcile()
    for owner in ("alice", "bob"):
        identity = store.get(owner)
        assert identity["auth_source"] == "explicit"
        assert identity["team_id"] == "engineering"
        assert identity["policy"]["per_user"] == 100
        assert identity["sync_error"] is None
        assert state["members"][("engineering", owner)]["max_budget"] is None
    assert state["teams"]["engineering"]["max_budget"] is None
    assert state["teams"]["engineering"]["spend"] == 5
    assert state["keys"]["key-old"]["spend"] == 42
    assert state["keys"]["key-bob"]["spend"] == 13
    assert state["keys"]["key-old"]["models"] == ["model-a"]
    assert state["keys"]["key-old"]["blocked"] is True
    assert not any(path in {"/user/new", "/key/generate", "/key/delete"} for _, path, _ in state["calls"])
    writes = [(path, data) for method, path, data in state["calls"] if method == "POST"]
    keys_protected = max(i for i, (path, _) in enumerate(writes) if path == "/key/update")
    caps_removed = min(i for i, (path, _) in enumerate(writes) if path in {"/team/update", "/team/member_update", "/user/update"})
    assert keys_protected < caps_removed
    state["calls"].clear()
    await sync.reconcile()
    assert not any(method == "POST" for method, _, _ in state["calls"])


@pytest.mark.asyncio
async def test_partial_migration_resumes_without_replacing_credentials_or_dropping_old_caps(native, monkeypatch):
    _, state = native
    existing_installation(monkeypatch, state)
    original = litellm.update_key
    fail = True

    async def update(key, changes):
        if fail and key == "key-bob":
            raise HTTPException(502, "Temporary upstream failure")
        return await original(key, changes)

    monkeypatch.setattr(litellm, "update_key", update)
    await sync.reconcile()
    assert state["teams"]["engineering"]["max_budget"] == 5000
    assert state["user_budget"] == 25
    assert store.get("bob")["sync_error"]
    assert state["keys"]["key-old"]["max_budget"] == 100
    fail = False
    await sync.reconcile()
    assert all(identity["sync_error"] is None for identity in store.list_identities())
    assert state["user_budget"] is None
    assert state["teams"]["engineering"]["max_budget"] is None
    assert set(state["keys"]) == {"key-old", "key-bob"}
    assert [state["keys"][key]["spend"] for key in ("key-old", "key-bob")] == [42, 13]
