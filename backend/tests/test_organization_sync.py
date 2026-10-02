"""Budget changes preserve spend and managed keys cannot bypass their policy."""

import asyncio
from unittest.mock import AsyncMock

from fastapi import HTTPException
import pytest

from app.config import settings
from app.organization import OrganizationHierarchy
from app.services import litellm, local_users
from app.services import organization_client as upstream, organization_store as store, organization_sync as sync
from tests.test_organization_config import example


@pytest.fixture(autouse=True)
def hierarchy(monkeypatch, tmp_path):
    tree = OrganizationHierarchy.model_validate(example())
    monkeypatch.setattr(settings, "organization_hierarchy", tree)
    monkeypatch.setattr(settings, "local_users_db_path", str(tmp_path / "organization.db"))
    sync._locks.clear()
    local_users.init_db()
    return tree


@pytest.mark.asyncio
async def test_reconcile_updates_existing_member_without_resetting_spend(monkeypatch, hierarchy):
    store.remember("alice", "alice@example.com", "sso", ["squad1"])
    node = hierarchy.resolve("alice", ["squad1"])
    old_policy = {"node_id": node.id, "per_user": 50, "duration": "30d"}
    store.synced("alice", "engineering", old_policy)
    info = {"team_memberships": [{"user_id": "alice", "spend": 42, "litellm_budget_table": {"max_budget": 50, "budget_duration": "30d"}}]}
    root = AsyncMock(return_value=info)
    request = AsyncMock(return_value={})
    monkeypatch.setattr(
        upstream,
        "team_info",
        AsyncMock(
            side_effect=[
                info,
                {"team_memberships": [{"user_id": "alice", "spend": 42, "litellm_budget_table": {"max_budget": 100, "budget_duration": "30d"}}]},
            ]
        ),
    )
    monkeypatch.setattr(upstream, "sync_root", root)
    monkeypatch.setattr(upstream, "request", request)
    monkeypatch.setattr(litellm, "get_user", AsyncMock(return_value=None))
    monkeypatch.setattr(litellm, "list_user_keys", AsyncMock(return_value=[]))
    await sync.reconcile()
    request.assert_awaited_once_with(
        "POST", "/team/member_update", payload={"team_id": "engineering", "user_id": "alice", "max_budget_in_team": 100.0}
    )
    assert "spend" not in request.call_args.kwargs["payload"]
    assert store.get("alice")["policy"]["per_user"] == 100
    assert info["team_memberships"][0]["spend"] == 42


@pytest.mark.asyncio
async def test_same_policy_does_not_reset_budget_window(monkeypatch, hierarchy):
    node = hierarchy.resolve("u", ["squad1"])
    info = {"team_memberships": [{"user_id": "u", "spend": 42, "litellm_budget_table": {"max_budget": 100, "budget_duration": "30d"}}]}
    request = AsyncMock()
    monkeypatch.setattr(upstream, "request", request)
    await upstream.sync_member(node, "u", info)
    request.assert_not_awaited()


@pytest.mark.asyncio
async def test_root_budget_sync_never_writes_spend_or_unrelated_model_policy(monkeypatch, hierarchy):
    monkeypatch.setattr(
        litellm, "get_team", AsyncMock(return_value={"max_budget": 4000, "budget_duration": "30d", "spend": 400, "models": ["restricted"]})
    )
    update = AsyncMock()
    monkeypatch.setattr(litellm, "update_team", update)
    monkeypatch.setattr(upstream, "team_info", AsyncMock(return_value={"team_info": {"max_budget": 5000, "budget_duration": "30d", "spend": 400}}))
    await upstream.sync_root(hierarchy.roots[0])
    update.assert_awaited_once_with("engineering", {"max_budget": 5000.0})


@pytest.mark.asyncio
async def test_missing_root_team_is_created(monkeypatch, hierarchy):
    monkeypatch.setattr(litellm, "get_team", AsyncMock(return_value=None))
    create = AsyncMock()
    monkeypatch.setattr(litellm, "create_team", create)
    monkeypatch.setattr(upstream, "team_info", AsyncMock(return_value={"team_info": {"max_budget": 5000, "budget_duration": "30d"}}))
    await upstream.sync_root(hierarchy.roots[0])
    assert create.call_args.args[0]["team_id"] == "engineering"
    assert create.call_args.args[0]["max_budget"] == 5000


@pytest.mark.asyncio
async def test_unmanaged_existing_key_adopts_person_policy_only_after_member_sync(monkeypatch):
    store.remember("u", "u@example.com", "sso", ["squad1"])
    order = []

    async def member(*args):
        order.append("member")

    async def update(*args):
        order.append("key")

    monkeypatch.setattr(upstream, "sync_member", member)
    monkeypatch.setattr(litellm, "list_user_keys", AsyncMock(return_value=[{"token": "key-hash", "spend": 42, "max_budget": 50}]))
    monkeypatch.setattr(litellm, "update_key", update)
    monkeypatch.setattr(litellm, "get_key_info", AsyncMock(return_value={"team_id": "engineering", "max_budget": None, "budget_duration": None}))
    await sync.sync_identity(store.get("u"), {})
    assert order == ["member", "key"]
    assert store.get("u")["team_id"] == "engineering"


@pytest.mark.asyncio
async def test_cross_department_mapping_does_not_reset_member_allowance(monkeypatch):
    store.remember("u", "u@example.com", "sso", ["squad1"])
    monkeypatch.setattr(litellm, "list_user_keys", AsyncMock(return_value=[{"token": "key-hash", "team_id": "marketing"}]))
    member = AsyncMock()
    monkeypatch.setattr(upstream, "sync_member", member)
    with pytest.raises(HTTPException) as exc:
        await sync.sync_identity(store.get("u"), {})
    assert exc.value.status_code == 409
    member.assert_not_awaited()
    assert store.get("u")["team_id"] is None


@pytest.mark.asyncio
async def test_removed_or_conflicting_mapping_blocks_and_reports_sync_error(monkeypatch):
    store.remember("u", "u@example.com", "sso", ["squad1", "squad2"])
    monkeypatch.setattr(upstream, "sync_root", AsyncMock(return_value={}))
    monkeypatch.setattr(litellm, "get_user", AsyncMock(return_value=None))
    await sync.reconcile()
    assert "conflict" in store.get("u")["sync_error"]
    store.remember("u", "u@example.com", "sso", ["removed-group"])
    store.synced("u", "engineering", {})
    with pytest.raises(HTTPException) as exc:
        await sync.remember("u", "u@example.com", "sso", [])
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_managed_key_generation_uses_user_budget_and_revokes_on_verification_failure(monkeypatch):
    monkeypatch.setattr(settings, "key_max_budget", 5)
    monkeypatch.setattr(settings, "key_models", '["model-a"]')
    request = AsyncMock(return_value={"key": "sk-test-managed"})
    monkeypatch.setattr(upstream, "request", request)
    monkeypatch.setattr(
        litellm, "get_key_info", AsyncMock(return_value={"user_id": "u", "team_id": "engineering", "max_budget": None, "budget_duration": None})
    )
    result = await upstream.generate_key("u", "u@example.com", "engineering", initial_spend=12)
    assert result["key"] == "sk-test-managed"
    payload = request.call_args.kwargs["payload"]
    assert payload["max_budget"] is None
    assert payload["models"] == ["model-a"]
    assert payload["spend"] == 12
    monkeypatch.setattr(litellm, "get_key_info", AsyncMock(return_value=None))
    delete = AsyncMock()
    monkeypatch.setattr(litellm, "delete_key", delete)
    with pytest.raises(HTTPException):
        await upstream.generate_key("u", "", "engineering")
    delete.assert_awaited_once_with("sk-test-managed")


@pytest.mark.asyncio
async def test_upstream_default_key_cap_is_cleared_and_verified(monkeypatch):
    monkeypatch.setattr(upstream, "request", AsyncMock(return_value={"key": "sk-managed"}))
    monkeypatch.setattr(
        litellm,
        "get_key_info",
        AsyncMock(side_effect=[{"user_id": "u", "team_id": "engineering", "max_budget": 5}, {"max_budget": None, "budget_duration": None}]),
    )
    update = AsyncMock()
    monkeypatch.setattr(litellm, "update_key", update)
    await upstream.generate_key("u", "", "engineering")
    update.assert_awaited_once_with("sk-managed", {"max_budget": None, "budget_duration": None})


@pytest.mark.asyncio
async def test_managed_budget_guard_cannot_be_bypassed_by_changing_key_team(monkeypatch):
    store.remember("u", "u@example.com", "sso", ["squad1"])
    store.synced("u", "engineering", {})
    monkeypatch.setattr(litellm, "get_key_info", AsyncMock(return_value={"user_id": "u", "team_id": "old-team"}))
    with pytest.raises(HTTPException) as exc:
        await sync.guard_key("key", {"team_id": "other"})
    assert exc.value.status_code == 409
    await sync.guard_key("key", {"models": ["restricted"]})


@pytest.mark.asyncio
async def test_login_sync_failure_is_immediately_visible_to_administrators(monkeypatch):
    monkeypatch.setattr(upstream, "sync_root", AsyncMock(side_effect=HTTPException(status_code=502, detail="Budget unsupported")))
    with pytest.raises(HTTPException):
        await sync.remember("u", "u@example.com", "sso", ["squad1"])
    assert store.get("u")["sync_error"] == "Budget unsupported"


@pytest.mark.asyncio
async def test_bulk_updates_cannot_move_unmapped_keys_into_managed_roots(monkeypatch):
    monkeypatch.setattr(litellm, "get_key_info", AsyncMock(return_value={"user_id": "unmapped", "team_id": "manual-team"}))
    with pytest.raises(HTTPException) as exc:
        await sync.guard_key("key", {"team_id": "engineering"})
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_slow_reconciliation_does_not_block_another_user_in_the_same_root(monkeypatch):
    store.remember("alice", "alice@example.com", "sso", ["squad1"])
    entered, release = asyncio.Event(), asyncio.Event()

    async def member(node, user_id, info):
        if user_id == "alice":
            entered.set()
            await release.wait()

    monkeypatch.setattr(upstream, "sync_root", AsyncMock(return_value={}))
    monkeypatch.setattr(upstream, "team_info", AsyncMock(return_value={}))
    monkeypatch.setattr(upstream, "sync_member", member)
    monkeypatch.setattr(upstream, "generate_key", AsyncMock(return_value={"key": "sk-bob-test"}))
    monkeypatch.setattr(litellm, "get_user", AsyncMock(return_value=None))
    monkeypatch.setattr(litellm, "list_user_keys", AsyncMock(return_value=[]))
    background = asyncio.create_task(sync.reconcile())
    try:
        await asyncio.wait_for(entered.wait(), 2)
        node = await asyncio.wait_for(sync.remember("bob", "bob@example.com", "sso", ["squad2"]), 2)
        assert node.per_user == 50
        assert store.get("bob")["team_id"] == "engineering"
        generated = await asyncio.wait_for(sync.generate_key("bob", "bob@example.com", None), 2)
        assert generated["key"] == "sk-bob-test"
        assert not background.done()
    finally:
        release.set()
        await background


@pytest.mark.asyncio
async def test_identity_changes_and_key_issuance_are_serialized_for_the_same_user(monkeypatch):
    store.remember("u", "u@example.com", "sso", ["squad1"])
    store.synced("u", "engineering", {})
    entered, release = asyncio.Event(), asyncio.Event()

    async def generate(*args, **kwargs):
        entered.set()
        await release.wait()
        return {"key": "sk-test"}

    monkeypatch.setattr(upstream, "sync_root", AsyncMock(return_value={}))
    monkeypatch.setattr(upstream, "sync_member", AsyncMock())
    monkeypatch.setattr(upstream, "generate_key", generate)
    monkeypatch.setattr(litellm, "list_user_keys", AsyncMock(return_value=[]))
    issued = asyncio.create_task(sync.generate_key("u", "u@example.com", None))
    invalidated = None
    try:
        await asyncio.wait_for(entered.wait(), 2)
        invalidated = asyncio.create_task(sync.record_identity("u", "u@example.com", "sso", []))
        await asyncio.sleep(0)
        assert not invalidated.done()
        release.set()
        await issued
        with pytest.raises(HTTPException) as exc:
            await invalidated
        assert exc.value.status_code == 403
        with pytest.raises(HTTPException):
            await sync.generate_key("u", "u@example.com", None)
        assert store.get("u")["groups"] == []
    finally:
        release.set()
        await asyncio.gather(issued, *([invalidated] if invalidated else []), return_exceptions=True)


@pytest.mark.asyncio
async def test_queued_key_creation_reads_membership_after_acquiring_the_user_lock(monkeypatch):
    store.remember("u", "u@example.com", "sso", ["squad1"])
    store.synced("u", "engineering", {})
    upstream_sync = AsyncMock()
    monkeypatch.setattr(upstream, "sync_root", upstream_sync)
    async with sync.lock_for("user", "u"):
        invalidation = asyncio.create_task(sync.record_identity("u", "u@example.com", "sso", []))
        creation = asyncio.create_task(sync.generate_key("u", "u@example.com", None))
        await asyncio.sleep(0)
    results = await asyncio.gather(invalidation, creation, return_exceptions=True)
    assert all(isinstance(result, HTTPException) and result.status_code == 403 for result in results)
    upstream_sync.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["member response", "member verification", "key verification"])
async def test_partial_sync_retains_root_and_blocks_a_fresh_allowance_in_another_root(monkeypatch, failure):
    values = example()
    values["levels"][0]["groups"][0]["members"][1]["ssoGroups"] = ["marketers"]
    monkeypatch.setattr(settings, "organization_hierarchy", OrganizationHierarchy.model_validate(values))
    root = AsyncMock(return_value={})
    monkeypatch.setattr(upstream, "sync_root", root)
    keys = AsyncMock(return_value=[{"token": "old-key", "max_budget": 50}] if failure == "key verification" else [])
    monkeypatch.setattr(litellm, "list_user_keys", keys)
    monkeypatch.setattr(litellm, "add_team_member", AsyncMock())
    monkeypatch.setattr(litellm, "update_key", AsyncMock())
    monkeypatch.setattr(litellm, "get_key_info", AsyncMock(return_value=None))
    writes = []

    async def write(method, path, *, payload):
        assert store.get("u")["team_id"] == "engineering"
        writes.append(payload["team_id"])
        if failure == "member response":
            raise HTTPException(status_code=502, detail="Response lost after writing member budget")
        return {}

    verified = {"team_memberships": [{"user_id": "u", "litellm_budget_table": {"max_budget": 100, "budget_duration": "30d"}}]}
    monkeypatch.setattr(upstream, "request", write)
    monkeypatch.setattr(
        upstream,
        "team_info",
        AsyncMock(
            side_effect=HTTPException(status_code=502, detail="Verification unavailable") if failure == "member verification" else None,
            return_value=verified,
        ),
    )
    with pytest.raises(HTTPException) as exc:
        await sync.remember("u", "u@example.com", "sso", ["squad1"])
    assert exc.value.status_code == 502
    assert writes == ["engineering"]
    identity = store.get("u")
    assert identity["team_id"] == "engineering"
    assert identity["policy"] is None
    assert identity["sync_error"]

    keys.return_value = []
    with pytest.raises(HTTPException) as exc:
        await sync.remember("u", "u@example.com", "sso", ["marketers"])
    assert exc.value.status_code == 409
    assert writes == ["engineering"]
    assert store.get("u")["team_id"] == "engineering"

    # Retrying the original root uses its existing allowance rather than making a new one.
    root.return_value = verified
    await sync.remember("u", "u@example.com", "sso", ["squad1"])
    assert writes == ["engineering"]
    assert store.get("u")["policy"]["per_user"] == 100
    assert store.get("u")["sync_error"] is None
