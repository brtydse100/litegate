"""Organization memberships compose with both authenticated SSO flows."""

from http.cookies import SimpleCookie
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.dependencies import decode_portal_token
from app.routers import auth


@pytest.fixture
def login(monkeypatch):
    monkeypatch.setattr(
        auth.settings,
        "organization_mapping",
        {
            "groups": {
                "company": {"team_id": "company"},
                "engineering": {"team_id": "engineering", "parent": "company"},
                "platform": {"team_id": "platform", "parent": "engineering", "members": ["alice@example.com"]},
            }
        },
    )
    monkeypatch.setattr(auth.settings, "organization_mapping_file", "")
    monkeypatch.setattr(auth.settings, "oidc_group_team_mapping", {})
    monkeypatch.setattr(auth.settings, "oidc_require_team_mapping", True)
    monkeypatch.setattr(auth.settings, "sso_default_team_id", "default")
    monkeypatch.setattr(auth.settings, "inherit_litellm_admin", False)
    claims = {"sub": "subject", "email": "Alice@Example.com", "groups": ["existing-group"]}
    resolver = AsyncMock(return_value="canonical")
    ensure = AsyncMock(return_value={"keys": [{"token": "owned-hash"}]})
    sync = AsyncMock()
    migrate = AsyncMock()
    monkeypatch.setattr(auth, "resolve_sso_user_id", resolver, raising=False)
    monkeypatch.setattr(auth, "provider_authority", lambda: "provider", raising=False)
    monkeypatch.setattr(auth.llm, "ensure_user_exists", ensure)
    monkeypatch.setattr(auth.llm, "sync_user_team_memberships", sync)
    # Assigned once the migration module is included by this feature.
    from app.services import key_team_migration

    monkeypatch.setattr(key_team_migration, "migrate_user_keys", migrate)
    monkeypatch.setattr(auth.oidc_svc, "exchange_code", AsyncMock(return_value={"id_token": "verified-token"}))
    monkeypatch.setattr(auth.oidc_svc, "verify_id_token", AsyncMock(return_value=claims))
    monkeypatch.setattr(auth.generic_sso, "get_user_claims", AsyncMock(return_value=claims))
    return claims, resolver, ensure, sync, migrate


async def callback(monkeypatch, generic):
    monkeypatch.setattr(auth.settings, "generic_authorization_endpoint", "https://idp.example/authorize" if generic else "")
    state = auth.oidc_svc.generate_state("generic" if generic else "oidc")
    return await auth.callback("code", state, state_cookie=state)


@pytest.mark.asyncio
@pytest.mark.parametrize("generic", [False, True])
async def test_email_hierarchy_uses_canonical_identity_and_migrates(monkeypatch, login, generic):
    _, resolver, ensure, sync, migrate = login
    response = await callback(monkeypatch, generic)
    assert resolver.await_args.args == ("provider", "subject", "Alice@Example.com")
    ensure.assert_awaited_once_with("canonical", "Alice@Example.com")
    sync.assert_awaited_once_with("canonical", "Alice@Example.com", ["platform", "engineering", "company", "default"])
    migrate.assert_awaited_once_with("canonical", "Alice@Example.com", "platform")
    cookie = SimpleCookie(response.headers.getlist("set-cookie")[0])
    user = decode_portal_token(cookie["litegate_session"].value)
    assert user.user_id == "canonical"
    assert user.team_ids == ["platform", "engineering", "company", "default"]
    assert user.role == "user"


@pytest.mark.asyncio
async def test_old_sso_primary_wins_and_inherits_ancestors(monkeypatch, login):
    monkeypatch.setattr(auth.settings, "oidc_group_team_mapping", {"existing-group": ["engineering", "shared"]})
    await callback(monkeypatch, False)
    login[3].assert_awaited_once_with("canonical", "Alice@Example.com", ["engineering", "shared", "platform", "company", "default"])
    assert login[4].await_args.args[2] == "engineering"


@pytest.mark.asyncio
async def test_default_alone_does_not_satisfy_required_mapping(monkeypatch, login):
    login[0]["email"] = "unknown@example.com"
    with pytest.raises(HTTPException) as error:
        await callback(monkeypatch, False)
    assert error.value.status_code == 403
    login[2].assert_not_awaited()


@pytest.mark.asyncio
async def test_unverified_email_never_grants_mapping_or_claims_reservation(monkeypatch, login):
    login[0]["email_verified"] = False
    with pytest.raises(HTTPException) as error:
        await callback(monkeypatch, False)
    assert error.value.status_code == 403
    login[1].assert_not_awaited()
    login[2].assert_not_awaited()


@pytest.mark.asyncio
async def test_key_migration_failure_prevents_session(monkeypatch, login):
    login[4].side_effect = HTTPException(status_code=502, detail="retry migration")
    with pytest.raises(HTTPException) as error:
        await callback(monkeypatch, False)
    assert error.value.status_code == 502


@pytest.mark.asyncio
async def test_mapping_removed_still_resolves_established_identity(monkeypatch, login):
    monkeypatch.setattr(auth.settings, "organization_mapping", {})
    monkeypatch.setattr(auth.settings, "oidc_require_team_mapping", False)
    await callback(monkeypatch, False)
    login[2].assert_awaited_once_with("canonical", "Alice@Example.com")


@pytest.mark.asyncio
async def test_existing_budget_hierarchy_keeps_primary_and_key_policy(monkeypatch, login):
    from app.organization import OrganizationHierarchy

    hierarchy = OrganizationHierarchy.model_validate(
        {
            "levels": [
                {"name": "division", "groups": [{"members": [{"name": "managed", "litellmTeamId": "governed", "ssoGroups": ["existing-group"]}]}]}
            ]
        }
    )
    monkeypatch.setattr(auth.settings, "organization_hierarchy", hierarchy)
    node = hierarchy.resolve("canonical", ["existing-group"])
    monkeypatch.setattr(auth.organization_sync, "record_identity", AsyncMock(return_value=node))
    monkeypatch.setattr(auth.organization_sync, "synchronize_user", AsyncMock(return_value=node))
    await callback(monkeypatch, False)
    assert login[3].await_args.args[2] == ["governed", "platform", "engineering", "company", "default"]
    login[4].assert_not_awaited()


@pytest.mark.asyncio
async def test_canonical_binding_cannot_silently_drop_explicit_hierarchy_path(monkeypatch, login):
    from app.organization import OrganizationHierarchy

    hierarchy = OrganizationHierarchy.model_validate(
        {"levels": [{"name": "division", "groups": [{"members": [{"name": "managed", "litellmTeamId": "governed", "userIds": ["subject"]}]}]}]}
    )
    monkeypatch.setattr(auth.settings, "organization_hierarchy", hierarchy)
    with pytest.raises(HTTPException) as error:
        await callback(monkeypatch, False)
    assert error.value.status_code == 409
    login[2].assert_not_awaited()
