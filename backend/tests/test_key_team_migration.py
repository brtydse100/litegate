import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from app.services import key_team_migration as migration
from app.routers import auth


@pytest.mark.asyncio
async def test_migration_reads_current_replacement_after_acquiring_owner_lock():
    current = [{"token": "old"}]
    replacement = {"user_id": "owner", "team_id": "previous"}

    async def update(key, fields):
        assert key == "replacement"
        replacement.update(fields)

    with (
        patch.object(migration.llm, "list_user_keys", new=AsyncMock(side_effect=lambda user_id: list(current))) as listing,
        patch.object(migration.llm, "get_key_info", new=AsyncMock(side_effect=lambda key: dict(replacement))),
        patch.object(migration.llm, "update_key", new=AsyncMock(side_effect=update)),
        patch.object(migration.audit, "record"),
    ):
        async with migration.organization_sync.lock_for("user", "owner"):
            pending = asyncio.create_task(migration.migrate_user_keys("owner", "", "primary"))
            await asyncio.sleep(0)
            listing.assert_not_awaited()
            current[:] = [{"token": "replacement", "team_id": "previous"}]
        assert await pending == 1
    assert replacement["team_id"] == "primary"


@pytest.mark.asyncio
async def test_migration_changes_only_team_and_is_safe_to_retry():
    records = [
        {"token": "hash-unassigned", "team_id": None},
        {"token": "hash-other-team", "team_id": "other"},
        {"token": "hash-primary", "team_id": "primary"},
    ]
    infos = {key["token"]: {"user_id": "owner", "team_id": key["team_id"], "spend": 1.234567, "key_alias": "owner's key"} for key in records}

    async def update(key, fields):
        infos[key].update(fields)
        return infos[key]

    with (
        patch.object(migration.llm, "list_user_keys", new=AsyncMock(return_value=records)),
        patch.object(migration.llm, "get_key_info", new=AsyncMock(side_effect=lambda key: dict(infos[key]))),
        patch.object(migration.llm, "update_key", new=AsyncMock(side_effect=update)) as update_key,
        patch.object(migration.audit, "record") as audit,
    ):
        assert await migration.migrate_user_keys("owner", "owner@example.com", "primary") == 2
        assert await migration.migrate_user_keys("owner", "owner@example.com", "primary") == 0

    assert [call.args[0] for call in update_key.await_args_list] == ["hash-unassigned", "hash-other-team"]
    assert all(call.args[1] == {"team_id": "primary"} for call in update_key.await_args_list)
    assert all(info["spend"] == 1.234567 and info["key_alias"] == "owner's key" for info in infos.values())
    assert audit.call_count == 2
    assert "hash-unassigned" not in str(audit.call_args)


@pytest.mark.asyncio
@pytest.mark.parametrize("info", [None, {"user_id": "other"}, {"user_id": "owner", "team_id": "primary"}])
async def test_migration_rechecks_current_ownership_and_team(info):
    with (
        patch.object(migration.llm, "list_user_keys", new=AsyncMock(return_value=[{"token": "hash"}])),
        patch.object(migration.llm, "get_key_info", new=AsyncMock(return_value=info)),
        patch.object(migration.llm, "update_key", new=AsyncMock()) as update,
    ):
        assert await migration.migrate_user_keys("owner", "", "primary") == 0
    update.assert_not_awaited()


@pytest.mark.asyncio
async def test_migration_size_limit_is_checked_before_mutations():
    with (
        patch.object(migration.llm, "list_user_keys", new=AsyncMock(return_value=[{"token": f"hash-{i}"} for i in range(501)])),
        patch.object(migration.llm, "update_key", new=AsyncMock()) as update,
    ):
        with pytest.raises(HTTPException) as error:
            await migration.migrate_user_keys("owner", "", "primary")
    assert error.value.status_code == 409
    update.assert_not_awaited()


@pytest.mark.asyncio
async def test_partial_migration_can_be_retried_without_replacing_keys():
    records = [{"token": "hash-1"}, {"token": "hash-2"}]
    infos = {key["token"]: {"user_id": "owner", "team_id": None} for key in records}
    fail = True

    async def update(key, fields):
        if key == "hash-2" and fail:
            raise HTTPException(status_code=502, detail="LiteLLM unavailable")
        infos[key].update(fields)
        return infos[key]

    with (
        patch.object(migration.llm, "list_user_keys", new=AsyncMock(return_value=records)),
        patch.object(migration.llm, "get_key_info", new=AsyncMock(side_effect=lambda key: dict(infos[key]))),
        patch.object(migration.llm, "update_key", new=AsyncMock(side_effect=update)) as update_key,
        patch.object(migration.audit, "record"),
    ):
        with pytest.raises(HTTPException):
            await migration.migrate_user_keys("owner", "", "primary")
        fail = False
        assert await migration.migrate_user_keys("owner", "", "primary") == 1

    assert [call.args[0] for call in update_key.await_args_list] == ["hash-1", "hash-2", "hash-2"]
    assert all(info["team_id"] == "primary" for info in infos.values())


@pytest.mark.asyncio
async def test_migration_verifies_the_team_update():
    with (
        patch.object(migration.llm, "list_user_keys", new=AsyncMock(return_value=[{"token": "hash"}])),
        patch.object(migration.llm, "get_key_info", new=AsyncMock(return_value={"user_id": "owner", "team_id": None})),
        patch.object(migration.llm, "update_key", new=AsyncMock()),
        patch.object(migration.audit, "record") as audit,
    ):
        with pytest.raises(HTTPException) as error:
            await migration.migrate_user_keys("owner", "", "primary")
    assert error.value.status_code == 502
    audit.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("generic", [False, True])
@pytest.mark.parametrize("mapped", [False, True])
async def test_login_migrates_after_membership_sync_to_primary_team(monkeypatch, generic, mapped):
    state = auth.oidc_svc.generate_state(flow="generic" if generic else "oidc")
    monkeypatch.setattr(auth.settings, "generic_authorization_endpoint", "https://idp.example/authorize" if generic else "")
    monkeypatch.setattr(auth.settings, "oidc_group_team_mapping", {"Engineering": ["primary", "shared"]} if mapped else {})
    monkeypatch.setattr(auth.settings, "oidc_groups_claim", "groups")
    monkeypatch.setattr(auth.settings, "oidc_require_team_mapping", False)
    monkeypatch.setattr(auth.settings, "sso_default_team_id", "default")
    monkeypatch.setattr(auth.settings, "inherit_litellm_admin", False)
    claims = {"sub": "owner", "email": "owner@example.com", "groups": ["Engineering"]}
    # A key can be created after provisioning; an empty snapshot cannot skip migration.
    records = []
    events = []

    async def sync(*args):
        events.append("membership")

    async def migrate(*args):
        events.append("migration")

    with (
        patch.object(auth.oidc_svc, "validate_state", return_value=True),
        patch.object(auth.oidc_svc, "exchange_code", new=AsyncMock(return_value={"id_token": "id"})),
        patch.object(auth.oidc_svc, "verify_id_token", new=AsyncMock(return_value=claims)),
        patch.object(auth.generic_sso, "get_user_claims", new=AsyncMock(return_value=claims)),
        patch.object(auth.llm, "ensure_user_exists", new=AsyncMock(return_value={"keys": records})),
        patch.object(auth.llm, "sync_user_team_memberships", new=AsyncMock(side_effect=sync)),
        patch.object(migration, "migrate_user_keys", new=AsyncMock(side_effect=migrate)) as move,
    ):
        response = await auth.callback("code", state, state_cookie=state)

    assert response.status_code == 307
    assert events == ["membership", "migration"]
    move.assert_awaited_once_with("owner", "owner@example.com", "primary" if mapped else "default")


@pytest.mark.asyncio
async def test_login_does_not_issue_a_session_when_migration_fails(monkeypatch):
    state = auth.oidc_svc.generate_state(flow="generic")
    monkeypatch.setattr(auth.settings, "generic_authorization_endpoint", "https://idp.example/authorize")
    monkeypatch.setattr(auth.settings, "oidc_group_team_mapping", {})
    monkeypatch.setattr(auth.settings, "oidc_require_team_mapping", False)
    monkeypatch.setattr(auth.settings, "sso_default_team_id", "default")
    with (
        patch.object(auth.oidc_svc, "validate_state", return_value=True),
        patch.object(auth.generic_sso, "get_user_claims", new=AsyncMock(return_value={"sub": "owner"})),
        patch.object(auth.llm, "ensure_user_exists", new=AsyncMock(return_value={"keys": [{"token": "hash"}]})),
        patch.object(auth.llm, "sync_user_team_memberships", new=AsyncMock()),
        patch.object(migration, "migrate_user_keys", new=AsyncMock(side_effect=HTTPException(status_code=502, detail="Failed"))),
        patch.object(auth, "_set_session_cookie") as set_cookie,
        pytest.raises(HTTPException) as error,
    ):
        await auth.callback("code", state, state_cookie=state)
    assert error.value.status_code == 502
    set_cookie.assert_not_called()
