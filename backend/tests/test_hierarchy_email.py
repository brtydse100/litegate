"""Email assignment uses the existing hierarchy resolver and persisted identity."""

import pytest
from fastapi import HTTPException
from app.organization import OrganizationHierarchy, MembershipConflict
from app.config import settings
from app.services import organization_store as store, organization_sync as sync
from tests.test_organization_config import example


def hierarchy():
    data = example()
    data["levels"][2]["groups"][0]["members"][0]["userIds"] = [" Alice@Example.com ", "Exact-ID"]
    return OrganizationHierarchy.model_validate(data)


def test_email_normalization_and_single_path():
    tree = hierarchy()
    assert tree.resolve("subject", ["engineers"], email=" ALICE@example.COM ", source="sso").path[-1] == "squad1"
    assert tree.resolve("subject", [], email="alice@example.com", source="local") is None
    assert tree.resolve("Exact-ID", []).path[-1] == "squad1"
    assert tree.resolve("exact-id", []) is None
    with pytest.raises(MembershipConflict):
        tree.resolve("subject", ["squad2"], email="alice@example.com", source="sso")


@pytest.mark.asyncio
async def test_stored_sso_email_controls_policy_and_removal(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "local_users_db_path", str(tmp_path / "identity.db"))
    monkeypatch.setattr(settings, "organization_hierarchy", hierarchy())
    node = await sync.record_identity("subject", " ALICE@example.com ", "sso", [])
    assert node.path[-1] == "squad1"
    identity = store.get("subject")
    assert sync.resolve_identity(identity) == node
    await sync.record_identity("local:user", "alice@example.com", "local", [])
    assert store.get("local:user") is None
    with pytest.raises(HTTPException):
        await sync.record_identity("subject", "removed@example.com", "sso", [])
    assert store.get("subject")["email"] == "removed@example.com"


@pytest.mark.asyncio
@pytest.mark.parametrize("required", [True, False])
@pytest.mark.parametrize("verified", [True, False, None])
@pytest.mark.parametrize("assignment", ["individual", "group", "combined", "conflict", "none"])
async def test_generic_policy_through_callback(monkeypatch, tmp_path, required, verified, assignment):
    from tests.test_generic_sso import mock_provider
    from app.routers import auth
    from app.services import oidc
    from unittest.mock import AsyncMock

    tree = hierarchy()
    monkeypatch.setattr(settings, "organization_hierarchy", tree)
    monkeypatch.setattr(settings, "local_users_db_path", str(tmp_path / "claims.db"))
    for key, value in {
        "generic_authorization_endpoint": "https://idp.example/auth",
        "generic_client_id": "client",
        "generic_token_endpoint": "https://idp.example/token",
        "generic_userinfo_endpoint": "https://idp.example/userinfo",
        "generic_user_id_attribute": "sub",
        "generic_user_email_attribute": "email",
        "generic_require_verified_email": required,
        "oidc_group_team_mapping": {},
        "oidc_require_team_mapping": False,
        "sso_default_team_id": "",
        "inherit_litellm_admin": False,
    }.items():
        monkeypatch.setattr(settings, key, value)
    groups = {"individual": [], "group": ["squad1"], "combined": ["engineers"], "conflict": ["squad2"], "none": []}[assignment]
    email = " ALICE@EXAMPLE.COM " if assignment in {"individual", "combined", "conflict"} else "other@example.com"
    claims = {"sub": "subject", "email": email, "groups": groups}
    if verified is not None:
        claims["email_verified"] = verified
    mock_provider(monkeypatch, userinfo=claims)
    ensure = AsyncMock(return_value={"user_id": "subject"})
    monkeypatch.setattr(auth.llm, "ensure_user_exists", ensure)
    monkeypatch.setattr(auth.llm, "sync_user_team_memberships", AsyncMock())
    # Remote policy synchronization has its own integration tests. Claims remain real SQLite.
    monkeypatch.setattr(sync, "synchronize_user", AsyncMock(return_value=None))
    state = oidc.generate_state("generic")
    if (required and verified is False) or assignment == "conflict":
        with pytest.raises(HTTPException) as error:
            await auth.callback("code", state, state_cookie=state)
        assert error.value.status_code == 403
        ensure.assert_not_awaited()
    else:
        response = await auth.callback("code", state, state_cookie=state)
        assert response.status_code == 307
        assert ensure.await_args.args == ("subject", email.strip().casefold())
        identity = store.get("subject")
        assert (identity is not None) == (assignment != "none")
        if identity:
            assert sync.resolve_identity(identity).path[-1] == "squad1"


@pytest.mark.asyncio
async def test_reconciliation_does_not_lookup_configured_emails(monkeypatch, tmp_path):
    from unittest.mock import AsyncMock

    monkeypatch.setattr(settings, "organization_hierarchy", hierarchy())
    monkeypatch.setattr(settings, "local_users_db_path", str(tmp_path / "empty.db"))
    lookup = AsyncMock(return_value=None)
    monkeypatch.setattr(sync.litellm, "get_user", lookup)
    monkeypatch.setattr(sync.upstream, "sync_root", AsyncMock())
    monkeypatch.setattr(sync.key_policy, "finish_team", AsyncMock())
    await sync.reconcile()
    assert {call.args[0] for call in lookup.await_args_list} == {"Exact-ID", "local:alice"}
    assert store.get("alice@example.com") is None


@pytest.mark.parametrize("key,value", [("organization_mapping", {"groups": {"old": {}}}), ("organization_mapping_file", "organization.json")])
def test_removed_settings_fail_with_migration_guidance(monkeypatch, key, value):
    from app.config import Settings

    with pytest.raises(ValueError, match="migrate email assignments"):
        Settings(**{key: value})
    monkeypatch.setenv(key.upper(), str(value))
    with pytest.raises(ValueError, match="migrate email assignments"):
        Settings()


@pytest.mark.asyncio
async def test_usage_resolves_stored_email_not_groups_only(monkeypatch, tmp_path):
    from app.services import organization_reports as reports

    monkeypatch.setattr(settings, "local_users_db_path", str(tmp_path / "reports.db"))
    monkeypatch.setattr(settings, "organization_hierarchy", hierarchy())
    store.remember("subject", "ALICE@example.com", "sso", [])
    values, errors = await reports.identities()
    assert len(values) == 1
    assert values[0][1].path[-1] == "squad1"
    assert errors == []
