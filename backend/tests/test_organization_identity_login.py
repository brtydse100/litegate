"""Real durable binding and managed-policy interactions during SSO login."""

from copy import deepcopy
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.organization import OrganizationHierarchy
from app.routers import auth
from app.services import local_users, organization_store, organization_sync
from app.services import organization_provisioning as provisioning, sso_identity as identities


@pytest.fixture
def identity_login(monkeypatch, tmp_path):
    monkeypatch.setattr(auth.settings, "local_users_db_path", str(tmp_path / "identity.db"))
    monkeypatch.setattr(auth.settings, "oidc_issuer_url", "https://idp.example")
    monkeypatch.setattr(auth.settings, "oidc_client_id", "portal")
    monkeypatch.setattr(auth.settings, "oidc_require_team_mapping", False)
    monkeypatch.setattr(auth.settings, "oidc_group_team_mapping", {})
    monkeypatch.setattr(auth.settings, "sso_default_team_id", "")
    monkeypatch.setattr(auth.settings, "organization_mapping_file", "")
    monkeypatch.setattr(
        auth.settings, "organization_mapping", {"groups": {"email-team": {"team_id": "email-team", "members": ["alice@example.com"]}}}
    )
    local_users.init_db()
    identities.initialize_identity_store()
    users = {}
    monkeypatch.setattr(provisioning.remote, "get_user", AsyncMock(side_effect=lambda user_id: deepcopy(users.get(user_id))))
    monkeypatch.setattr(provisioning.remote, "find_users_by_email", AsyncMock(side_effect=lambda email: list(deepcopy(users).values())))
    monkeypatch.setattr(auth.llm, "ensure_user_exists", AsyncMock(return_value={}))
    claims = {"sub": "subject", "email": "alice@example.com", "groups": []}
    monkeypatch.setattr(auth.oidc_svc, "exchange_code", AsyncMock(return_value={"id_token": "token"}))
    monkeypatch.setattr(auth.oidc_svc, "verify_id_token", AsyncMock(return_value=claims))
    monkeypatch.setattr(auth.generic_sso, "get_user_claims", AsyncMock(return_value=claims))
    return claims, users


def reserve_user(users, provider):
    reservation = identities.reserve(provider, "alice@example.com")
    users[reservation["user_id"]] = {
        "user_id": reservation["user_id"],
        "user_email": "alice@example.com",
        "user_role": "internal_user",
        "metadata": {provisioning.remote.OWNER_FIELD: reservation["ownership_token"]},
    }
    identities.mark_reservation(provider, "alice@example.com", "reserved")
    return reservation["user_id"]


async def rejected_callback(generic):
    state = auth.oidc_svc.generate_state("generic" if generic else "oidc")
    with pytest.raises(HTTPException) as error:
        await auth.callback("code", state, state_cookie=state)
    return error.value


@pytest.mark.asyncio
@pytest.mark.parametrize("generic", [False, True])
async def test_rejected_groups_replace_canonical_claims_and_block_old_sessions(monkeypatch, identity_login, generic):
    claims, users = identity_login
    monkeypatch.setattr(auth.settings, "generic_authorization_endpoint", "https://idp.example/auth" if generic else "")
    hierarchy = OrganizationHierarchy.model_validate(
        {
            "levels": [
                {
                    "name": "division",
                    "groups": [
                        {
                            "members": [
                                {"name": "a", "litellmTeamId": "a", "ssoGroups": ["a"]},
                                {"name": "b", "litellmTeamId": "b", "ssoGroups": ["b"]},
                            ]
                        }
                    ],
                }
            ]
        }
    )
    monkeypatch.setattr(auth.settings, "organization_hierarchy", hierarchy)
    provider = identities.provider_authority()
    canonical = reserve_user(users, provider)
    identities.bind(provider, "subject", claims["email"], canonical)
    organization_store.remember(canonical, claims["email"], "sso", ["a"])
    claims["groups"] = ["a", "b"]
    assert (await rejected_callback(generic)).status_code == 403
    assert organization_store.get(canonical)["groups"] == ["a", "b"]
    assert organization_store.get("subject") is None
    with pytest.raises(HTTPException) as error:
        await organization_sync.prepare_user(canonical, claims["email"])
    assert error.value.status_code == 403
    auth.llm.ensure_user_exists.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("generic", [False, True])
async def test_explicit_path_rejection_does_not_commit_canonical_binding(monkeypatch, identity_login, generic):
    claims, users = identity_login
    monkeypatch.setattr(auth.settings, "generic_authorization_endpoint", "https://idp.example/auth" if generic else "")
    hierarchy = OrganizationHierarchy.model_validate(
        {"levels": [{"name": "division", "groups": [{"members": [{"name": "managed", "litellmTeamId": "managed", "userIds": ["subject"]}]}]}]}
    )
    monkeypatch.setattr(auth.settings, "organization_hierarchy", hierarchy)
    provider = identities.provider_authority()
    reserve_user(users, provider)
    assert (await rejected_callback(generic)).status_code == 409
    assert identities.lookup_binding(provider, "subject") is None
    assert organization_store.get("subject") is None
    auth.llm.ensure_user_exists.assert_not_awaited()
