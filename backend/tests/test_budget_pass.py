"""Budget writes use fresh observations and verify decreases before increases."""

from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.services import budget_enforcement as enforcement, litellm, organization_store as store, organization_sync as sync
from tests.test_budget_enforcement import org, join


@pytest.mark.asyncio
async def test_empty_key_roster_does_not_reclaim_consumed_spend(org):
    org()
    join("ann", "ben")
    enforcement.observe_spend("ann", 80)
    await enforcement.observe("ann", [])
    enforcement.refresh()
    assert sync.resolve_identity(store.get("ben")).per_user == 10


@pytest.mark.asyncio
async def test_current_spend_is_collected_before_pinning(org, monkeypatch):
    from app.services import budget_pass

    org()
    join("ann", "ben")
    monkeypatch.setattr(
        litellm,
        "list_user_keys",
        AsyncMock(
            side_effect=lambda user: (
                [{"token": user, "user_id": user, "team_id": "eng", "spend": 80 if user == "ann" else 0, "max_budget": 90 if user == "ann" else 10}]
                if user in {"ann", "ben"}
                else []
            )
        ),
    )
    update = AsyncMock()
    monkeypatch.setattr(litellm, "update_key", update)
    monkeypatch.setattr(litellm, "get_key_info", AsyncMock(return_value={"user_id": "ann", "max_budget": 80}))

    @budget_pass.serialized
    async def operation():
        return sync.resolve_identity(store.get("ben")).per_user

    assert await operation() == 10
    update.assert_awaited_once_with("ann", {"max_budget": 80})


@pytest.mark.asyncio
async def test_failed_decrease_prevents_any_increase(org, monkeypatch):
    from app.services import budget_pass

    hierarchy = org()
    join("ann", "ben")
    node = next(node for node in hierarchy.nodes.values() if node.team_id == "eng")
    from app.services import budget_store

    budget_store.edit(0, lambda state: state.update(overrides={"ann": 10_000_000, "ben": 80_000_000}))
    monkeypatch.setattr(
        litellm,
        "list_user_keys",
        AsyncMock(
            side_effect=lambda user: (
                [{"token": user, "user_id": user, "team_id": "eng", "spend": 0, "max_budget": 80 if user == "ann" else 10}]
                if user in {"ann", "ben"}
                else []
            )
        ),
    )
    monkeypatch.setattr(litellm, "update_key", AsyncMock(side_effect=HTTPException(502, "Decrease failed")))
    increase = AsyncMock()

    @budget_pass.serialized
    async def operation():
        await increase(node)

    with pytest.raises(HTTPException, match="502"):
        await operation()
    increase.assert_not_awaited()


@pytest.mark.asyncio
async def test_multiple_key_owner_aborts_before_mutations(org, monkeypatch):
    from app.services import budget_pass

    org()
    join("ann")
    monkeypatch.setattr(litellm, "list_user_keys", AsyncMock(side_effect=lambda user: [{"token": "a"}, {"token": "b"}] if user == "ann" else []))
    operation = AsyncMock()
    update = AsyncMock()
    monkeypatch.setattr(litellm, "update_key", update)
    with pytest.raises(HTTPException, match="409"):
        await budget_pass.serialized(operation)()
    operation.assert_not_awaited()
    update.assert_not_awaited()


@pytest.mark.asyncio
async def test_reconcile_uses_current_spend_and_one_pinned_snapshot(org, monkeypatch):
    org()
    join("ann", "ben")
    monkeypatch.setattr(
        litellm,
        "list_user_keys",
        AsyncMock(
            side_effect=lambda user: (
                [{"token": user, "user_id": user, "team_id": "eng", "spend": 80 if user == "ann" else 0, "max_budget": 80 if user == "ann" else 10}]
                if user in {"ann", "ben"}
                else []
            )
        ),
    )
    monkeypatch.setattr(sync.discovery, "refresh", AsyncMock(return_value=set()))
    monkeypatch.setattr(sync.upstream, "sync_root", AsyncMock())
    monkeypatch.setattr(sync.upstream, "team_info", AsyncMock(return_value={}))
    monkeypatch.setattr(sync.key_policy, "finish_team", AsyncMock())
    monkeypatch.setattr(sync, "finalize_identity", AsyncMock())
    applied = {}

    async def synchronize(identity, info, **kwargs):
        node = sync.resolve_identity(identity)
        applied[identity["user_id"]] = node.per_user
        return node

    monkeypatch.setattr(sync, "sync_identity", synchronize)
    await sync.reconcile()
    assert (applied["ann"], applied["ben"]) == (80, 10)


@pytest.mark.asyncio
async def test_unavailable_spend_does_not_allow_policy_writes(org, monkeypatch):
    from app.services import budget_pass

    org()
    join("ann")
    monkeypatch.setattr(
        litellm,
        "list_user_keys",
        AsyncMock(side_effect=lambda user: [{"token": "a", "user_id": "ann", "team_id": "eng", "max_budget": 90}] if user == "ann" else []),
    )
    operation = AsyncMock()
    with pytest.raises(HTTPException, match="502"):
        await budget_pass.serialized(operation)()
    operation.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_moved_members_key_counts_its_spend_in_the_new_group(org, monkeypatch):
    from app.services import budget_pass

    org()
    join("ann", "ben")
    # ann's key is still in Sales, her previous group, with $50 already spent.
    monkeypatch.setattr(
        litellm,
        "list_user_keys",
        AsyncMock(
            side_effect=lambda user: [{"token": "k", "user_id": "ann", "team_id": "sales", "spend": 50, "max_budget": 7}] if user == "ann" else []
        ),
    )
    monkeypatch.setattr(litellm, "update_key", AsyncMock())

    @budget_pass.serialized
    async def operation():
        return sync.resolve_identity(store.get("ann")).per_user, sync.resolve_identity(store.get("ben")).per_user

    # The transfer no longer stops every budget write; Engineering's $90 keeps
    # ann's consumed $50 and shares the rest.
    assert await operation() == (50, 40)
