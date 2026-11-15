"""Rotation must retain administrative controls, even outside the hierarchy."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app.config import settings
from app.organization import OrganizationHierarchy
from app.services import organization_sync as sync
from tests.test_organization_lowest_team import native


@pytest.mark.asyncio
@pytest.mark.parametrize("managed", [False, True])
async def test_rotation_preserves_nonbudget_policy_and_absolute_expiry(native, monkeypatch, managed):
    tree, state = native
    if not managed:
        monkeypatch.setattr(settings, "organization_hierarchy", OrganizationHierarchy())
    restriction = {
        "blocked": True,
        "models": ["restricted-model"],
        "rpm_limit": 2,
        "tpm_limit": 30,
        "max_parallel_requests": 1,
    }
    state["keys"]["key-old"].update(restriction)
    if managed:
        await sync.remember("alice", "alice@example.com", "sso", ["squad1"])
    result = await sync.rotate_key("alice", "alice@example.com", None, key_alias="replacement")
    replacement = state["keys"][result["key"]]
    assert {field: replacement.get(field) for field in restriction} == restriction
    assert replacement["spend"] == 42
    assert replacement["team_id"] == (tree.resolve("alice", ["squad1"]).team_id if managed else "engineering")
    assert "key-old" not in state["keys"]


@pytest.mark.asyncio
@pytest.mark.parametrize("expires", ["2030-01-01T00:00:00+00:00", None])
async def test_rotation_uses_supported_duration_without_extending_expiry(native, monkeypatch, expires):
    from app.services import litellm

    _, state = native
    monkeypatch.setattr(settings, "organization_hierarchy", OrganizationHierarchy())
    state["keys"]["key-old"]["expires"] = expires
    monkeypatch.setattr(settings, "key_duration", "30d")
    update = litellm.update_key
    generate = sync._generate_key

    async def generate_with_expiration(*args, **kwargs):
        result = await generate(*args, **kwargs)
        state["keys"][result["key"]]["expires"] = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        return result

    async def supported_update(key, changes):
        # UpdateKeyRequest accepts duration, not an absolute expires field.
        assert "expires" not in changes
        if "duration" in changes:
            changes = dict(changes)
            duration = changes.pop("duration")
            state["keys"][key]["expires"] = (datetime.now(timezone.utc) + timedelta(seconds=int(duration[:-1]))).isoformat() if duration else None
        return await update(key, changes)

    monkeypatch.setattr(litellm, "update_key", supported_update)
    monkeypatch.setattr(sync, "_generate_key", generate_with_expiration)
    result = await sync.rotate_key("alice", "alice@example.com", None, key_alias="replacement")
    actual = state["keys"][result["key"]].get("expires")
    if expires:
        assert actual is not None
        assert 0 <= (datetime.fromisoformat(expires) - datetime.fromisoformat(actual)).total_seconds() < 2
    else:
        assert actual is None


@pytest.mark.asyncio
async def test_incompatible_source_policies_require_admin_assistance(native, monkeypatch):
    _, state = native
    monkeypatch.setattr(settings, "organization_hierarchy", OrganizationHierarchy())
    state["keys"]["key-old"]["models"] = ["model-a"]
    state["keys"]["second"] = {**state["keys"]["key-old"], "token": "second", "models": ["model-b"]}
    with pytest.raises(HTTPException) as error:
        await sync.rotate_key("alice", "alice@example.com", None, key_alias="replacement")
    assert error.value.status_code == 409
    assert set(state["keys"]) == {"key-old", "second"}
    assert not any(path in {"/key/generate", "/key/update", "/key/delete"} for _, path, _ in state["calls"])


@pytest.mark.asyncio
async def test_ignored_policy_write_revokes_replacement_and_keeps_original(native, monkeypatch):
    from app.services import litellm

    _, state = native
    monkeypatch.setattr(settings, "organization_hierarchy", OrganizationHierarchy())
    state["keys"]["key-old"]["blocked"] = True
    update = litellm.update_key

    async def ignore_blocked(key, changes):
        return await update(key, {field: value for field, value in changes.items() if field != "blocked"})

    monkeypatch.setattr(litellm, "update_key", ignore_blocked)
    with pytest.raises(HTTPException) as error:
        await sync.rotate_key("alice", "alice@example.com", None, key_alias="replacement")
    assert error.value.status_code == 502
    assert set(state["keys"]) == {"key-old"}
    assert state["keys"]["key-old"]["blocked"] is True
