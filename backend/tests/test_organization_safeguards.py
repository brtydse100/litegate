"""Regressions for policy migration, partial availability, and request cancellation."""

import asyncio
from unittest.mock import AsyncMock

from fastapi import HTTPException
import pytest

from app.config import settings
from app.models import CurrentUser
from app.organization import OrganizationHierarchy
from app.routers import keys
from app.services import litellm, oidc
from app.services import organization_client as upstream, organization_store as store, organization_sync as sync
from tests.test_organization_config import example
from tests.test_organization_http import client, setup, token


@pytest.mark.asyncio
async def test_flat_sso_mappings_cannot_add_another_managed_root(monkeypatch):
    monkeypatch.setattr(settings, "oidc_group_team_mapping", {"squad1": ["marketing", "manual-team"]})
    monkeypatch.setattr(settings, "sso_default_team_id", "marketing")
    monkeypatch.setattr(oidc, "exchange_code", AsyncMock(return_value={"id_token": "verified-token"}))
    monkeypatch.setattr(oidc, "verify_id_token", AsyncMock(return_value={"sub": "u", "groups": ["squad1"]}))
    monkeypatch.setattr(litellm, "ensure_user_exists", AsyncMock(return_value={}))
    monkeypatch.setattr(litellm, "list_user_keys", AsyncMock(return_value=[]))
    memberships = AsyncMock()
    monkeypatch.setattr(litellm, "sync_user_team_memberships", memberships)
    monkeypatch.setattr(upstream, "sync_root", AsyncMock(return_value={}))
    monkeypatch.setattr(upstream, "sync_member", AsyncMock())
    state = oidc.generate_state()
    async with client() as browser:
        browser.cookies.set("litegate_oidc_state", state, path="/api/auth")
        response = await browser.get("/api/auth/callback", params={"state": state, "code": "code"})
    assert response.status_code == 307
    assert memberships.await_args.args[2] == ["engineering", "manual-team"]


@pytest.mark.asyncio
@pytest.mark.parametrize("old_member_row", [True, False])
async def test_destination_membership_and_deleted_keys_do_not_approve_migration(monkeypatch, old_member_row):
    values = example()
    values["levels"][0]["groups"][0]["members"][1]["ssoGroups"] = ["marketers"]
    monkeypatch.setattr(settings, "organization_hierarchy", OrganizationHierarchy.model_validate(values))
    store.remember("u", "u@example.com", "sso", ["marketers"])
    store.synced("u", "engineering", {"per_user": 100})
    old = {
        "team_info": {"members_with_roles": [{"user_id": "u", "role": "user"}]},
        "team_memberships": [{"user_id": "u", "spend": 100}] if old_member_row else [],
    }
    destination = {"team_memberships": [{"user_id": "u", "spend": 0}]}
    monkeypatch.setattr(upstream, "team_info", AsyncMock(return_value=old))
    monkeypatch.setattr(litellm, "list_user_keys", AsyncMock(return_value=[]))
    update = AsyncMock()
    monkeypatch.setattr(upstream, "sync_member", update)
    with pytest.raises(HTTPException) as exc:
        await sync.sync_identity(store.get("u"), destination)
    assert exc.value.status_code == 409
    update.assert_not_awaited()
    assert store.get("u")["team_id"] == "engineering"

    # A deliberate upstream migration removes the old roster and member row.
    monkeypatch.setattr(upstream, "team_info", AsyncMock(return_value={"team_info": {"members_with_roles": []}, "team_memberships": []}))
    await sync.sync_identity(store.get("u"), destination)
    update.assert_awaited_once()
    assert store.get("u")["team_id"] == "marketing"


@pytest.mark.asyncio
async def test_discovery_outage_does_not_stop_known_user_policy_updates(monkeypatch, caplog):
    store.remember("u", "u@example.com", "sso", ["squad1"])

    async def unavailable(user_id):
        # Known policies must already be current before discovery can stall or fail.
        node = settings.organization_hierarchy.resolve("u", ["squad1"])
        assert store.get("u")["policy"]["per_user"] == node.per_user
        raise HTTPException(status_code=503, detail="Discovery unavailable")

    discovery = AsyncMock(side_effect=unavailable)
    roots, members = AsyncMock(return_value={}), AsyncMock()
    monkeypatch.setattr(litellm, "get_user", discovery)
    monkeypatch.setattr(litellm, "list_user_keys", AsyncMock(return_value=[]))
    monkeypatch.setattr(upstream, "sync_root", roots)
    monkeypatch.setattr(upstream, "team_info", AsyncMock(return_value={}))
    monkeypatch.setattr(upstream, "sync_member", members)
    for allowance in (80, 90):
        values = example()
        values["levels"][2]["groups"][0]["members"][0]["budget"]["perUser"] = allowance
        monkeypatch.setattr(settings, "organization_hierarchy", OrganizationHierarchy.model_validate(values))
        await sync.reconcile()
        assert store.get("u")["policy"]["per_user"] == allowance
    assert roots.await_count == 4
    assert members.await_count == 2
    assert discovery.await_count == 2
    assert "Discovery unavailable" in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["creation verification", "replacement verification", "old key deletion"])
async def test_cancelled_key_operations_finish_revoking_undelivered_keys(monkeypatch, stage):
    entered, cleanup_entered, release_cleanup = asyncio.Event(), asyncio.Event(), asyncio.Event()
    active = {"sk-old"} if stage != "creation verification" else set()
    created = []

    async def generate(method, path, *, payload):
        created.append("sk-new")
        active.add("sk-new")
        return {"key": "sk-new"}

    async def verify(*args):
        entered.set()
        await asyncio.Event().wait()

    async def delete(key):
        if key == "sk-old":
            entered.set()
            await asyncio.Event().wait()
        cleanup_entered.set()
        await release_cleanup.wait()
        active.discard(key)

    monkeypatch.setattr(upstream, "request", generate)
    monkeypatch.setattr(litellm, "get_key_info", verify)
    monkeypatch.setattr(litellm, "delete_key", delete)
    if stage == "creation verification":
        operation = upstream.generate_key("u", "u@example.com", "engineering")
    else:
        monkeypatch.setattr(litellm, "list_user_keys", AsyncMock(return_value=[{"token": "sk-old", "spend": 3}]))
        if stage == "old key deletion":

            async def replacement(*args, **kwargs):
                active.add("sk-new")
                created.append("sk-new")
                return {"key": "sk-new"}

            monkeypatch.setattr(sync, "generate_key", replacement)
        else:
            monkeypatch.setattr(sync, "prepare_user", AsyncMock(return_value=settings.organization_hierarchy.roots[0]))
        operation = keys.regenerate_key(CurrentUser(user_id="u", email="u@example.com"))
    task = asyncio.create_task(operation)
    try:
        await asyncio.wait_for(entered.wait(), 2)
        task.cancel()
        await asyncio.wait_for(cleanup_entered.wait(), 2)
        task.cancel()  # Another disconnect must not cancel the revocation itself.
        await asyncio.sleep(0)
        assert not task.done()
        release_cleanup.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert created == ["sk-new"]
        assert active == ({"sk-old"} if stage != "creation verification" else set())
    finally:
        release_cleanup.set()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("mapping", ["valid", "removed", "conflicting"])
async def test_personal_keys_show_enforced_budget_and_policy_errors(monkeypatch, mapping):
    groups = {"valid": ["squad1"], "removed": [], "conflicting": ["squad1", "squad2"]}[mapping]
    store.remember("u", "u@example.com", "sso", groups)
    store.synced("u", "engineering", {"per_user": 200})
    if mapping == "valid":
        store.failed("u", "Budget update failed")
    monkeypatch.setattr(litellm, "list_user_keys", AsyncMock(return_value=[{"token": "hash", "team_id": "engineering", "spend": 2}]))
    info = {"team_memberships": [{"user_id": "u", "spend": 60, "litellm_budget_table": {"max_budget": 200, "budget_duration": "30d"}}]}
    monkeypatch.setattr(upstream, "team_info", AsyncMock(return_value=info))
    async with client() as browser:
        response = await browser.get("/api/keys", headers=token())
    assert response.status_code == 200
    key = response.json()["keys"][0]
    assert key["user_budget"] == 200
    assert key["user_spend"] == 60
    assert key["organization_managed"] is True
    assert key["user_budget_available"] is True
    assert key["policy_error"]


@pytest.mark.asyncio
async def test_budget_lookup_outage_keeps_key_metadata_with_an_unknown_allowance(monkeypatch):
    store.remember("u", "u@example.com", "sso", ["squad1"])
    metadata = {"token": "hash", "team_id": "engineering", "spend": 12, "models": ["model-a"]}
    monkeypatch.setattr(litellm, "list_user_keys", AsyncMock(return_value=[metadata]))
    monkeypatch.setattr(upstream, "team_info", AsyncMock(side_effect=HTTPException(status_code=503, detail="Budget service unavailable")))
    async with client() as browser:
        response = await browser.get("/api/keys", headers=token())
    assert response.status_code == 200
    key = response.json()["keys"][0]
    assert all(key[field] == value for field, value in metadata.items())
    assert key["user_budget_available"] is False
    assert key["user_budget"] is None
    assert "unavailable" in key["policy_error"]


@pytest.mark.asyncio
async def test_a_failed_key_adoption_does_not_show_an_inapplicable_member_allowance(monkeypatch):
    store.remember("u", "u@example.com", "sso", ["squad1"])
    store.synced("u", "engineering", {"per_user": 100})
    store.failed("u", "Key team update failed")
    metadata = {"token": "hash", "team_id": None, "spend": 12, "max_budget": 50}
    monkeypatch.setattr(litellm, "list_user_keys", AsyncMock(return_value=[metadata]))
    lookup = AsyncMock(return_value={"team_memberships": [{"user_id": "u", "litellm_budget_table": {"max_budget": 100}}]})
    monkeypatch.setattr(upstream, "team_info", lookup)
    async with client() as browser:
        response = await browser.get("/api/keys", headers=token())
    assert response.status_code == 200
    key = response.json()["keys"][0]
    assert key["user_budget_available"] is False
    assert key["policy_error"] == "Key team update failed"
    assert key["max_budget"] == 50
    lookup.assert_not_awaited()


@pytest.mark.asyncio
async def test_early_end_date_without_a_start_returns_validation_error():
    async with client() as browser:
        response = await browser.get("/api/v1/organization/usage", params={"end_date": "0001-01-01"}, headers=token("admin"))
    assert response.status_code == 422
