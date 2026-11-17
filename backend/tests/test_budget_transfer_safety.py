"""Transfers and first provisioning cannot release unverified allowances."""

from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.config import settings
from app.organization import OrganizationHierarchy
from app.services import budget_enforcement as enforcement, budget_store, litellm, organization_store as store, organization_sync as sync
from tests.test_budget_enforcement import org, join


@pytest.mark.asyncio
@pytest.mark.parametrize("registered", [True, False])
async def test_first_generation_registers_participant_before_pinning(org, monkeypatch, registered):
    org()
    if not registered:
        from app.services import database

        with database.connect() as db:
            db.execute("DELETE FROM organization_identities WHERE user_id = ?", ("ann",))
    monkeypatch.setattr(litellm, "list_user_keys", AsyncMock(return_value=[]))
    monkeypatch.setattr(sync, "sync_root", AsyncMock(return_value={}))
    monkeypatch.setattr(sync.upstream, "membership", lambda info, user: {"user_id": user})
    monkeypatch.setattr(sync.key_policy, "guard_ancestor_restrictions", AsyncMock())
    monkeypatch.setattr(sync.key_policy, "normalize_individual_caps", AsyncMock())
    generate = AsyncMock(return_value={"key": "synthetic-created-key"})
    monkeypatch.setattr(sync.upstream, "generate_key", generate)
    assert (await sync.generate_key("ann", "ann@example.invalid", None))["key"] == "synthetic-created-key"
    assert generate.await_args.kwargs["max_budget"] == 90


@pytest.mark.asyncio
async def test_failed_transfer_preserves_source_caps_before_any_write(org, monkeypatch):
    org()
    hierarchy = OrganizationHierarchy.model_validate(
        {
            "levels": [
                {
                    "name": "Department",
                    "groups": [
                        {
                            "members": [
                                {"name": "Eng", "litellmTeamId": "eng", "ssoGroups": ["eng"], "budget": {"groupTotal": 90}},
                                {"name": "Sales", "litellmTeamId": "sales", "ssoGroups": ["sales"], "budget": {"groupTotal": 90}},
                            ]
                        }
                    ],
                }
            ]
        }
    )
    monkeypatch.setattr(settings, "organization_hierarchy", hierarchy)
    for user in ("ann", "ben"):
        store.remember(user, f"{user}@example.invalid", "sso", ["eng"])
        store.bind_team(user, "eng")
    join("ann", "ben")
    current = {
        user: {"token": user, "user_id": user, "team_id": "eng", "max_budget": 45, "budget_duration": None, "spend": 0} for user in ("ann", "ben")
    }
    monkeypatch.setattr(litellm, "list_user_keys", AsyncMock(side_effect=lambda user: [dict(current[user])] if user in current else []))
    update = AsyncMock()
    monkeypatch.setattr(litellm, "update_key", update)
    await sync.record_identity("ann", "ann@example.invalid", "sso", ["sales"])
    with pytest.raises(HTTPException) as exc:
        await sync.reconcile()
    assert exc.value.status_code == 409
    update.assert_not_awaited()
    assert current["ann"]["max_budget"] + current["ben"]["max_budget"] == 90


def test_deficit_snapshot_replaces_floors_without_mutating_pinned_snapshot(org):
    org()
    join("ann", "ben", "cat")
    budget_store.edit(0, lambda state: state.update(overrides={"ann": 100_000_000}))
    enforcement.observe_spend("ben", 20)
    enforcement.observe_spend("cat", 10)
    before = enforcement.refresh()
    enforcement.observe_spend("ben", 0)
    enforcement.observe_spend("cat", 30)
    after = enforcement.refresh()
    assert after is not before
    assert before["floors"]["ben"] == 20_000_000
    assert after["floors"]["ben"] == 0
    assert sync.resolve_identity(store.get("ben")).per_user == 0
