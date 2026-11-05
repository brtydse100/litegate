"""Opt-in real subject keyless creation contract for pinned LiteLLM."""

import os
from uuid import uuid4
import pytest
from app.services import litellm
from app.services import litellm_identity as remote

pytestmark = pytest.mark.skipif(os.environ.get("RUN_LITELLM_INTEGRATION") != "1", reason="requires the opt-in pinned LiteLLM integration stack")


@pytest.mark.asyncio
async def test_actual_subject_created_without_key():
    suffix = uuid4().hex[:12]
    subject = f"sso-integration-{suffix}"
    email = f"identity-{suffix}@example.invalid"
    await litellm.ensure_user_exists(subject, email)
    assert (await remote.get_user(subject))["user_email"] == email
    assert (await litellm.get_user(subject))["keys"] == []
    # Keep the synthetic row in the disposable integration database.


@pytest.mark.asyncio
async def test_email_search_pagination_and_no_login_migration(monkeypatch, tmp_path):
    from unittest.mock import AsyncMock
    from app.config import settings
    from app.organization import OrganizationHierarchy
    from app.services import organization_client as upstream, organization_discovery as discovery
    from app.services import organization_sync as sync, organization_store as store

    suffix = uuid4().hex[:12]
    subject, email, team = f"startup-{suffix}", f"startup-{suffix}@example.invalid", f"startup-team-{suffix}"
    await litellm.ensure_user_exists(subject, email)
    # Pin real response metadata and case-insensitive substring behavior with page_size=1.
    result = await upstream.request(
        "GET", "/user/list", params={"user_email": email.upper(), "page": 1, "page_size": 1, "sort_by": "user_id", "sort_order": "asc"}
    )
    assert result["page"] == 1 and result["page_size"] == 1 and result["total"] == 1 and result["total_pages"] == 1
    assert result["users"][0]["user_id"] == subject
    assert (await discovery.email_match(email))["user_id"] == subject
    key = (await litellm.generate_key(subject, email, key_alias=f"startup-{suffix}"))["key"]
    try:
        await litellm.update_key(key, {"spend": 42})
        before = await litellm.get_key_info(key)
        monkeypatch.setattr(settings, "local_users_db_path", str(tmp_path / "startup.db"))
        monkeypatch.setattr(
            settings,
            "organization_hierarchy",
            OrganizationHierarchy.model_validate(
                {
                    "levels": [
                        {
                            "name": "Group",
                            "groups": [{"members": [{"name": "Startup", "litellmTeamId": team, "userIds": [email], "budget": {"perUser": 100}}]}],
                        }
                    ]
                }
            ),
        )
        # Creation is setup only; the reconciliation itself cannot create or replace credentials.
        monkeypatch.setattr(litellm, "ensure_user_exists", AsyncMock(side_effect=AssertionError("no user creation")))
        monkeypatch.setattr(litellm, "generate_key", AsyncMock(side_effect=AssertionError("no key creation")))
        await sync.reconcile()
        identity = store.get(subject)
        assert identity is not None
        assert identity["sync_error"] is None, identity["sync_error"]
        after = await litellm.get_key_info(key)
        assert identity["auth_source"] == "configured_email"
        assert after["team_id"] == team and after["max_budget"] == 100 and after["spend"] == 42
        assert after["key_alias"] == before["key_alias"] and after["models"] == before["models"]
        assert len(await litellm.list_user_keys(subject)) == 1
    finally:
        await litellm.delete_key(key)
        if await litellm.get_team(team):
            await litellm.delete_team(team)
