"""Public authorization, login, and key contracts for managed organizations."""

import asyncio
from unittest.mock import AsyncMock

import httpx
import pytest

from app.config import settings
from app.main import app
from app.organization import OrganizationHierarchy
from app.rate_limit import _key_ops, _login_failures
from app.routers import auth
from app.services import litellm, local_users, oidc
from app.services import organization_client as upstream, organization_store as store, organization_sync as sync
from tests.test_organization_config import example


@pytest.fixture(autouse=True)
def setup(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "organization_hierarchy", OrganizationHierarchy.model_validate(example()))
    monkeypatch.setattr(settings, "local_users_db_path", str(tmp_path / "organization.db"))
    monkeypatch.setattr(settings, "admin_emails", "")
    monkeypatch.setattr(settings, "admin_groups", "")
    monkeypatch.setattr(settings, "management_api_key", "test-management-key")
    monkeypatch.setattr(settings, "inherit_litellm_admin", False)
    sync._locks.clear()
    _key_ops.clear()
    _login_failures.clear()
    local_users.init_db()


def client():
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver")


def token(role="user", user_id="u"):
    return {"Authorization": "Bearer " + auth._make_jwt(user_id, "u@example.com", role)}


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["", "/users", "/usage"])
async def test_organization_endpoints_reject_anonymous_users_and_key_identities(monkeypatch, path):
    monkeypatch.setattr(litellm, "get_key_info", AsyncMock(return_value={"user_id": "u"}))
    async with client() as browser:
        assert (await browser.get("/api/v1/organization" + path)).status_code == 401
        assert (await browser.get("/api/v1/organization" + path, headers=token())).status_code == 403
        assert (await browser.get("/api/v1/organization" + path, headers={"Authorization": "Bearer sk-proof"})).status_code == 403


@pytest.mark.asyncio
async def test_admin_reads_hierarchy_and_disabled_configuration(monkeypatch):
    monkeypatch.setattr(upstream, "team_info", AsyncMock(return_value={"team_info": {"spend": 42}}))
    async with client() as browser:
        response = await browser.get("/api/v1/organization", headers={"X-API-Key": "test-management-key"})
        assert response.status_code == 200
        assert response.json()["levels"] == ["Division", "Business Unit", "Squad"]
        squad = next(group for group in response.json()["groups"] if group["name"] == "squad1")
        assert squad["per_user"] == 100
        assert squad["group_total"] == 5000
        monkeypatch.setattr(settings, "organization_hierarchy", OrganizationHierarchy())
        disabled = await browser.get("/api/v1/organization", headers=token("admin"))
        assert disabled.json()["enabled"] is False


@pytest.mark.asyncio
async def test_sso_mapping_sets_budget_team_before_issuing_a_session(monkeypatch):
    monkeypatch.setattr(settings, "oidc_require_team_mapping", True)
    monkeypatch.setattr(settings, "oidc_group_team_mapping", {})
    monkeypatch.setattr(settings, "sso_default_team_id", "")
    monkeypatch.setattr(oidc, "exchange_code", AsyncMock(return_value={"id_token": "verified-token"}))
    monkeypatch.setattr(oidc, "verify_id_token", AsyncMock(return_value={"sub": "u", "email": "u@example.com", "groups": ["squad1"]}))
    monkeypatch.setattr(litellm, "ensure_user_exists", AsyncMock(return_value={}))
    monkeypatch.setattr(litellm, "sync_user_team_memberships", AsyncMock())
    monkeypatch.setattr(litellm, "list_user_keys", AsyncMock(return_value=[]))
    monkeypatch.setattr(upstream, "sync_root", AsyncMock(return_value={}))
    member = AsyncMock()
    monkeypatch.setattr(upstream, "sync_member", member)
    state = oidc.generate_state()
    async with client() as browser:
        browser.cookies.set("litegate_oidc_state", state, path="/api/auth")
        response = await browser.get("/api/auth/callback", params={"state": state, "code": "code"})
        assert response.status_code == 307
        me = await browser.get("/api/auth/me")
        assert me.json()["team_ids"] == ["engineering"]
        assert me.json()["role"] == "user"
    assert member.call_args.args[0].per_user == 100
    assert store.get("u")["policy"]["per_user"] == 100


@pytest.mark.asyncio
async def test_conflicting_sso_groups_never_issue_session(monkeypatch):
    monkeypatch.setattr(oidc, "exchange_code", AsyncMock(return_value={"id_token": "verified-token"}))
    monkeypatch.setattr(oidc, "verify_id_token", AsyncMock(return_value={"sub": "u", "groups": ["squad1", "squad2"]}))
    provision = AsyncMock()
    monkeypatch.setattr(litellm, "ensure_user_exists", provision)
    state = oidc.generate_state()
    async with client() as browser:
        browser.cookies.set("litegate_oidc_state", state, path="/api/auth")
        response = await browser.get("/api/auth/callback", params={"state": state, "code": "code"})
        assert response.status_code == 403
        assert "litegate_session" not in browser.cookies
    provision.assert_not_awaited()


@pytest.mark.asyncio
async def test_local_user_id_mapping_and_legacy_session_are_resolved(monkeypatch):
    monkeypatch.setattr(litellm, "list_user_keys", AsyncMock(return_value=[]))
    monkeypatch.setattr(upstream, "sync_root", AsyncMock(return_value={}))
    monkeypatch.setattr(upstream, "sync_member", AsyncMock())
    generate = AsyncMock(return_value={"key": "sk-managed", "user_id": "local:alice"})
    monkeypatch.setattr(upstream, "generate_key", generate)
    async with client() as browser:
        response = await browser.post("/api/keys", headers=token(user_id="local:alice"))
        assert response.status_code == 201
    generate.assert_awaited_once_with("local:alice", "u@example.com", "engineering")
    assert store.get("local:alice")["policy"]["per_user"] == 50


@pytest.mark.asyncio
async def test_personal_key_display_uses_member_budget_and_cycle_spend(monkeypatch):
    store.remember("u", "u@example.com", "sso", ["squad1"])
    monkeypatch.setattr(litellm, "list_user_keys", AsyncMock(return_value=[{"token": "hash", "spend": 2, "max_budget": None}]))
    monkeypatch.setattr(upstream, "team_info", AsyncMock(return_value={"team_memberships": [{"user_id": "u", "spend": 42}]}))
    async with client() as browser:
        response = await browser.get("/api/keys", headers=token())
    key = response.json()["keys"][0]
    assert key["user_budget"] == 100
    assert key["user_spend"] == 42
    assert key["organization_path"] == ["Engineering", "Digital", "squad1"]


@pytest.mark.asyncio
async def test_managed_team_mutations_are_blocked_before_upstream_requests(monkeypatch):
    update, delete, move = AsyncMock(), AsyncMock(), AsyncMock()
    monkeypatch.setattr(litellm, "update_team", update)
    monkeypatch.setattr(litellm, "delete_team", delete)
    monkeypatch.setattr(litellm, "get_team", move)
    async with client() as browser:
        assert (await browser.patch("/api/v1/teams/engineering", json={"max_budget": 999}, headers=token("admin"))).status_code == 409
        assert (await browser.delete("/api/v1/teams/engineering", headers=token("admin"))).status_code == 409
        assert (
            await browser.post(
                "/api/v1/teams/engineering/members/move",
                json={"user_id": "u", "destination_team_id": "other", "confirm_policy_change": True},
                headers=token("admin"),
            )
        ).status_code == 409
    update.assert_not_awaited()
    delete.assert_not_awaited()
    move.assert_not_awaited()


@pytest.mark.asyncio
async def test_bulk_policy_updates_report_managed_key_failure(monkeypatch):
    monkeypatch.setattr(litellm, "get_key_info", AsyncMock(return_value={"user_id": "u", "team_id": "engineering"}))
    update = AsyncMock()
    monkeypatch.setattr(litellm, "update_key", update)
    async with client() as browser:
        response = await browser.patch("/api/v1/keys/bulk", headers=token("admin"), json={"keys": ["hash"], "settings": {"max_budget": 999}})
    assert response.status_code == 200
    assert response.json()["failed"] == 1
    assert "organizationHierarchy" in response.json()["results"][0]["error"]
    update.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("groups", [[], ["squad1", "squad2"]])
@pytest.mark.parametrize("require_mapping", [False, True])
@pytest.mark.parametrize("path", ["/api/keys", "/api/keys/regenerate", "/api/v1/keys"])
async def test_verified_membership_rejection_blocks_key_creation_with_an_existing_session(monkeypatch, groups, require_mapping, path):
    store.remember("u", "u@example.com", "sso", ["squad1"])
    store.synced("u", "engineering", {})
    monkeypatch.setattr(settings, "oidc_require_team_mapping", require_mapping)
    monkeypatch.setattr(oidc, "exchange_code", AsyncMock(return_value={"id_token": "verified-token"}))
    monkeypatch.setattr(oidc, "verify_id_token", AsyncMock(return_value={"sub": "u", "email": "u@example.com", "groups": groups}))
    monkeypatch.setattr(litellm, "list_user_keys", AsyncMock(return_value=[]))
    generate = AsyncMock(return_value={"key": "sk-forbidden"})
    monkeypatch.setattr(upstream, "generate_key", generate)
    state = oidc.generate_state()
    async with client() as browser:
        browser.cookies.set("litegate_session", auth._make_jwt("u", "u@example.com"), path="/api")
        browser.cookies.set("litegate_oidc_state", state, path="/api/auth")
        rejected = await browser.get("/api/auth/callback", params={"state": state, "code": "code"})
        assert rejected.status_code == 403
        assert store.get("u")["groups"] == groups
        assert store.get("u")["sync_error"]
        assert (await browser.post(path)).status_code == 403
    generate.assert_not_awaited()


@pytest.mark.asyncio
async def test_an_older_inflight_login_cannot_restore_removed_verified_groups(monkeypatch):
    store.remember("u", "u@example.com", "sso", ["squad1"])
    store.synced("u", "engineering", {})
    entered, release = asyncio.Event(), asyncio.Event()

    async def provision(*args):
        entered.set()
        await release.wait()
        return {}

    monkeypatch.setattr(litellm, "ensure_user_exists", provision)
    monkeypatch.setattr(oidc, "exchange_code", AsyncMock(return_value={"id_token": "verified-token"}))
    monkeypatch.setattr(
        oidc,
        "verify_id_token",
        AsyncMock(
            side_effect=[
                {"sub": "u", "email": "u@example.com", "groups": ["squad1"]},
                {"sub": "u", "email": "u@example.com", "groups": []},
            ]
        ),
    )
    upstream_sync = AsyncMock(return_value={})
    monkeypatch.setattr(upstream, "sync_root", upstream_sync)
    first_state, second_state = oidc.generate_state(), oidc.generate_state()
    async with client() as first, client() as second:
        first.cookies.set("litegate_oidc_state", first_state, path="/api/auth")
        second.cookies.set("litegate_oidc_state", second_state, path="/api/auth")
        earlier = asyncio.create_task(first.get("/api/auth/callback", params={"state": first_state, "code": "earlier"}))
        try:
            await asyncio.wait_for(entered.wait(), 2)
            rejected = await second.get("/api/auth/callback", params={"state": second_state, "code": "later"})
            assert rejected.status_code == 403
            release.set()
            assert (await earlier).status_code == 403
            assert store.get("u")["groups"] == []
        finally:
            release.set()
            await earlier
    upstream_sync.assert_not_awaited()
