"""Background passes skip members already in sync, and sign-ins wait briefly for budget passes."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from app.config import settings
from app.organization import OrganizationHierarchy
from app.services import budget_enforcement, budget_pass, litellm, organization_reconcile
from app.services import organization_client as upstream
from app.services import organization_store as store
from app.services import organization_sync as sync
from tests.test_organization_config import example


@pytest.fixture
def member(monkeypatch):
    tree = OrganizationHierarchy.model_validate(example())
    monkeypatch.setattr(settings, "organization_hierarchy", tree)
    node = tree.resolve("ann", ["squad1"])
    store.remember("ann", "ann@example.com", "sso", ["squad1"])
    store.synced("ann", node.team_id, sync.policy(node))
    monkeypatch.setattr(upstream, "team_info", AsyncMock(return_value={"team_memberships": [{"user_id": "ann"}]}))
    monkeypatch.setattr(
        litellm, "list_user_keys", AsyncMock(return_value=[{"token": "k", "team_id": node.team_id, "max_budget": 100, "budget_duration": "30d"}])
    )
    full = AsyncMock(return_value=node)
    monkeypatch.setattr(sync, "sync_identity", full)
    return node, full


@pytest.mark.asyncio
async def test_settled_member_with_matching_keys_is_not_rewritten(member):
    node, full = member
    await organization_reconcile._reconcile_group(node.id, ["ann"])
    full.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("drift", ["key", "membership", "policy"])
async def test_any_drift_takes_the_full_synchronization(monkeypatch, member, drift):
    node, full = member
    if drift == "key":
        monkeypatch.setattr(litellm, "list_user_keys", AsyncMock(return_value=[{"token": "k", "team_id": "elsewhere"}]))
    elif drift == "membership":
        monkeypatch.setattr(upstream, "team_info", AsyncMock(return_value={"team_memberships": []}))
    else:
        store.synced("ann", node.team_id, {"node_id": node.id, "per_user": 1, "duration": None})
    await organization_reconcile._reconcile_group(node.id, ["ann"])
    full.assert_awaited_once()


@pytest.mark.asyncio
async def test_enforced_budgets_always_take_the_full_synchronization(monkeypatch, member):
    node, full = member
    monkeypatch.setattr(budget_enforcement, "enforced", lambda: True)
    await organization_reconcile._reconcile_group(node.id, ["ann"])
    full.assert_awaited_once()


@pytest.mark.asyncio
async def test_sign_in_waits_for_the_background_pass_instead_of_running_its_own(monkeypatch):
    monkeypatch.setattr(budget_enforcement, "enforced", lambda: True)
    budget_pass.mark_clean(budget_pass.generation())
    budget_pass.mark_cross_group_edit()
    release = asyncio.Event()
    calls = []

    async def run(groups, operation, **kwargs):
        calls.append(groups)
        if groups is None and not kwargs:
            await release.wait()  # The background pass.
        return await operation()

    monkeypatch.setattr(budget_pass, "_run", run)
    monkeypatch.setattr(budget_pass, "_groups_for", lambda *args: {"group"})
    monkeypatch.setattr(store, "list_identities", list)
    monkeypatch.setattr(litellm, "list_user_keys", AsyncMock(return_value=[]))

    @budget_pass.serialized
    async def sign_in(user_id):
        return "done"

    budget_pass.settle_soon()
    waiting = asyncio.create_task(sign_in("ann"))
    await asyncio.sleep(0)
    release.set()
    assert await waiting == "done"
    assert calls == [None, {"group"}]  # Only the background pass read everyone.


@pytest.mark.asyncio
async def test_sign_in_falls_back_to_its_own_pass_when_the_background_pass_is_slow(monkeypatch):
    monkeypatch.setattr(budget_enforcement, "enforced", lambda: True)
    monkeypatch.setattr(budget_pass, "SETTLE_WAIT", 0.01)
    budget_pass.mark_cross_group_edit()
    never = asyncio.Event()
    calls = []

    async def run(groups, operation, **kwargs):
        calls.append(kwargs.get("user_id"))
        if not kwargs:
            await never.wait()
        return await operation()

    monkeypatch.setattr(budget_pass, "_run", run)

    @budget_pass.serialized
    async def sign_in(user_id):
        return "done"

    budget_pass.settle_soon()
    assert await sign_in("ann") == "done"
    assert calls == [None, "ann"]
    budget_pass._settling.cancel()
