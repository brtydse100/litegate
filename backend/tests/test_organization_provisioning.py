import asyncio
from copy import deepcopy
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.config import settings
from app.services import local_users, organization_mapping
from app.services import organization_provisioning as provisioning
from app.services import sso_identity as store

EMAIL = "alice@example.com"


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "local_users_db_path", str(tmp_path / "identity.db"))
    monkeypatch.setattr(settings, "oidc_issuer_url", "https://idp.example.invalid")
    monkeypatch.setattr(settings, "oidc_client_id", "portal")
    monkeypatch.setattr(
        settings,
        "organization_mapping",
        {"groups": {"company": {"team_id": "company"}, "engineering": {"team_id": "engineering", "parent": "company", "members": [EMAIL]}}},
    )
    monkeypatch.setattr(settings, "organization_mapping_file", "")
    mapping = organization_mapping.load_mapping(settings.organization_mapping, "")
    monkeypatch.setattr(provisioning, "get_mapping", lambda: mapping)
    local_users.init_db()
    users = {}
    mutations = []

    async def get_user(user_id):
        return deepcopy(users.get(user_id))

    async def find(email):
        return [deepcopy(u) for u in users.values() if u.get("user_email", "").casefold() == email]

    async def create(user_id, email, token):
        assert store.reservation(store.provider_authority(), email)["ownership_token"] == token
        mutations.append(("create", user_id))
        users[user_id] = {"user_id": user_id, "user_email": email, "user_role": "internal_user", "metadata": {"litegate_organization_owner": token}}

    monkeypatch.setattr(provisioning.remote, "get_user", get_user)
    monkeypatch.setattr(provisioning.remote, "find_users_by_email", find)
    monkeypatch.setattr(provisioning.remote, "create_reserved_user", create)
    monkeypatch.setattr(provisioning.litellm, "get_team", AsyncMock(return_value={"team_id": "team"}))
    monkeypatch.setattr(provisioning.litellm, "sync_user_team_memberships", AsyncMock())
    return mapping, users, mutations


@pytest.mark.asyncio
async def test_keyless_startup_and_first_login_are_idempotent(setup):
    mapping, users, mutations = setup
    await provisioning.provision_members(mapping)
    canonical = next(iter(users))
    provider = store.provider_authority()
    assert await provisioning.resolve_sso_user_id(provider, "sub", EMAIL) == canonical
    await provisioning.provision_members(mapping)
    assert await provisioning.resolve_sso_user_id(provider, "sub", EMAIL) == canonical
    assert mutations == [("create", canonical)]
    provisioning.litellm.sync_user_team_memberships.assert_awaited_with(canonical, EMAIL, ["engineering", "company"])


@pytest.mark.asyncio
async def test_all_teams_preflight_before_writes(setup):
    mapping, _, mutations = setup
    provisioning.litellm.get_team.side_effect = [{"team_id": "company"}, None]
    with pytest.raises(HTTPException):
        await provisioning.provision_members(mapping)
    assert not mutations


@pytest.mark.asyncio
async def test_pending_candidate_untouched_until_subject_proof(setup):
    mapping, users, mutations = setup
    users["legacy"] = {"user_id": "legacy", "user_email": EMAIL, "user_role": "internal_user"}
    await provisioning.provision_members(mapping)
    assert store.reservation(store.provider_authority(), EMAIL)["status"] == "pending"
    assert not mutations
    provisioning.litellm.sync_user_team_memberships.assert_not_awaited()
    with pytest.raises(HTTPException):
        await provisioning.resolve_sso_user_id(store.provider_authority(), "wrong-sub", EMAIL)
    assert await provisioning.resolve_sso_user_id(store.provider_authority(), "legacy", EMAIL) == "legacy"
    assert not mutations


@pytest.mark.asyncio
@pytest.mark.parametrize("role,user_id", [("proxy_admin", "admin"), ("internal_user", "local:alice")])
async def test_known_local_and_admin_email_conflicts_fail(setup, role, user_id):
    mapping, users, mutations = setup
    users[user_id] = {"user_id": user_id, "user_email": EMAIL, "user_role": role}
    with pytest.raises(HTTPException):
        await provisioning.provision_members(mapping)
    assert not mutations


@pytest.mark.asyncio
async def test_legacy_subject_wins_without_mutating_reservation(setup):
    mapping, users, mutations = setup
    await provisioning.provision_members(mapping)
    reserved = next(iter(users))
    users[reserved].update(keys=[{"token": "independently-added"}], max_budget=17, teams=["manual"])
    retained = deepcopy(users[reserved])
    users["legacy"] = {"user_id": "legacy", "user_email": EMAIL, "user_role": "internal_user"}
    assert await provisioning.resolve_sso_user_id(store.provider_authority(), "legacy", EMAIL) == "legacy"
    assert store.reservation(store.provider_authority(), EMAIL)["status"] == "superseded"
    await provisioning.provision_members(mapping)
    assert users[reserved] == retained
    assert mutations == [("create", reserved)]
    assert provisioning.litellm.sync_user_team_memberships.await_args.args[0] == "legacy"


@pytest.mark.asyncio
async def test_crash_after_remote_creation_recovers_by_marker(setup, monkeypatch):
    mapping, users, mutations = setup
    original = provisioning.remote.create_reserved_user

    async def interrupted(*args):
        await original(*args)
        raise HTTPException(503, "connection lost")

    monkeypatch.setattr(provisioning.remote, "create_reserved_user", interrupted)
    with pytest.raises(HTTPException):
        await provisioning.provision_members(mapping)
    monkeypatch.setattr(provisioning.remote, "create_reserved_user", original)
    await provisioning.provision_members(mapping)
    assert len(mutations) == 1
    assert len(users) == 1


@pytest.mark.asyncio
async def test_marker_mismatch_and_ambiguous_email_fail_without_writes(setup):
    mapping, users, mutations = setup
    reservation = store.reserve(store.provider_authority(), EMAIL)
    users[reservation["user_id"]] = {"user_id": reservation["user_id"], "user_email": EMAIL, "user_role": "internal_user", "metadata": {}}
    with pytest.raises(HTTPException):
        await provisioning.provision_members(mapping)
    users.clear()
    for name in ["one", "two"]:
        users[name] = {"user_id": name, "user_email": EMAIL, "user_role": "internal_user"}
    with pytest.raises(HTTPException):
        await provisioning.provision_members(mapping)
    assert not mutations


@pytest.mark.asyncio
async def test_interrupted_creation_and_new_email_candidate_are_ambiguous(setup):
    mapping, users, mutations = setup
    reservation = store.reserve(store.provider_authority(), EMAIL)
    await provisioning.remote.create_reserved_user(reservation["user_id"], EMAIL, reservation["ownership_token"])
    users["unrelated"] = {"user_id": "unrelated", "user_email": EMAIL, "user_role": "internal_user"}
    with pytest.raises(HTTPException):
        await provisioning.provision_members(mapping)
    assert len(mutations) == 1
    provisioning.litellm.sync_user_team_memberships.assert_not_awaited()


@pytest.mark.asyncio
async def test_binding_survives_mapping_removal_and_email_change(setup, monkeypatch):
    mapping, _, _ = setup
    await provisioning.provision_members(mapping)
    canonical = await provisioning.resolve_sso_user_id(store.provider_authority(), "subject", EMAIL)
    monkeypatch.setattr(provisioning, "get_mapping", lambda: organization_mapping.load_mapping({}, ""))
    assert await provisioning.resolve_sso_user_id(store.provider_authority(), "subject", "changed@example.com") == canonical
    assert await provisioning.resolve_sso_user_id(store.provider_authority(), "other", "") == "other"
    with pytest.raises(HTTPException):
        await provisioning.resolve_sso_user_id(store.provider_authority(), "other", EMAIL)


@pytest.mark.asyncio
async def test_competing_subject_cannot_claim_bound_email(setup):
    mapping, _, _ = setup
    await provisioning.provision_members(mapping)
    await provisioning.resolve_sso_user_id(store.provider_authority(), "subject", EMAIL)
    with pytest.raises(HTTPException):
        await provisioning.resolve_sso_user_id(store.provider_authority(), "other", EMAIL)


@pytest.mark.asyncio
@pytest.mark.parametrize("round", [1, 2])
async def test_concurrent_subjects_select_only_one_canonical_identity(setup, monkeypatch, round):
    mapping, _, _ = setup
    await provisioning.provision_members(mapping)
    original = provisioning.remote.get_user

    async def yielding_read(*args):
        await asyncio.sleep(0)
        return await original(*args)

    monkeypatch.setattr(provisioning.remote, "get_user", yielding_read)
    results = await asyncio.gather(
        provisioning.resolve_sso_user_id(store.provider_authority(), "one", EMAIL),
        provisioning.resolve_sso_user_id(store.provider_authority(), "two", EMAIL),
        return_exceptions=True,
    )
    assert sum(isinstance(result, str) for result in results) == 1
    assert sum(isinstance(result, HTTPException) for result in results) == 1


@pytest.mark.asyncio
async def test_membership_failure_retries_without_creating_another_user(setup):
    mapping, users, mutations = setup
    provisioning.litellm.sync_user_team_memberships.side_effect = HTTPException(502, "team write failed")
    with pytest.raises(HTTPException):
        await provisioning.provision_members(mapping)
    provisioning.litellm.sync_user_team_memberships.side_effect = None
    await provisioning.provision_members(mapping)
    assert len(users) == len(mutations) == 1


@pytest.mark.asyncio
async def test_existing_admin_subject_can_bind_but_startup_email_cannot_adopt(setup):
    _, users, mutations = setup
    users["admin-subject"] = {"user_id": "admin-subject", "user_email": EMAIL, "user_role": "proxy_admin"}
    assert await provisioning.resolve_sso_user_id(store.provider_authority(), "admin-subject", EMAIL) == "admin-subject"
    assert not mutations


@pytest.mark.asyncio
async def test_governed_budget_team_overlap_fails_before_writes(setup, monkeypatch):
    from types import SimpleNamespace

    mapping, _, mutations = setup
    hierarchy = SimpleNamespace(is_managed_team=lambda team_id: team_id == "company")
    monkeypatch.setattr(settings, "organization_hierarchy", hierarchy)
    with pytest.raises(HTTPException):
        await provisioning.provision_members(mapping)
    assert not mutations
    provisioning.litellm.get_team.assert_not_awaited()


@pytest.mark.asyncio
async def test_manual_members_need_configured_sso_authority(setup, monkeypatch):
    mapping, _, mutations = setup
    monkeypatch.setattr(settings, "oidc_issuer_url", "")
    monkeypatch.setattr(settings, "generic_client_id", "")
    with pytest.raises(HTTPException):
        await provisioning.provision_members(mapping)
    assert not mutations
    provisioning.litellm.get_team.assert_not_awaited()


@pytest.mark.asyncio
async def test_binding_checkpoint_precedes_login_membership_writes(setup):
    _, _, _ = setup
    canonical = await provisioning.resolve_sso_user_id(store.provider_authority(), "subject", EMAIL)
    assert store.lookup_binding(store.provider_authority(), "subject")["user_id"] == canonical
    provisioning.litellm.sync_user_team_memberships.assert_not_awaited()


@pytest.mark.asyncio
async def test_no_mapping_keeps_legacy_login_without_database_or_remote_lookup(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "local_users_db_path", str(tmp_path / "absent.db"))
    mapping = organization_mapping.load_mapping({}, "")
    monkeypatch.setattr(provisioning, "get_mapping", lambda: mapping)
    lookup = AsyncMock(side_effect=AssertionError("unexpected remote lookup"))
    monkeypatch.setattr(provisioning.remote, "get_user", lookup)
    await provisioning.provision_members(mapping)
    assert await provisioning.resolve_sso_user_id("authority", "legacy", EMAIL) == "legacy"
    assert not local_users._db_path().exists()
