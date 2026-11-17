"""Administrative key deletion/reset must not erase enforced group accounting."""

from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.config import settings
from app.models import BulkKeyResetSpendRequest, CurrentUser, KeyDeleteRequest
from app.organization import OrganizationHierarchy
from app.routers import api_v1, keys
from app.routers.api_actor import ApiActor
from app.services import budget_key_guards as guards, litellm, organization_store


@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setattr(settings, "hierarchical_budgets_enforced", True)
    monkeypatch.setattr(
        settings,
        "organization_hierarchy",
        OrganizationHierarchy.model_validate(
            {
                "levels": [
                    {
                        "name": "Group",
                        "groups": [{"members": [{"name": "Engineering", "litellmTeamId": "eng", "userIds": ["ann"], "budget": {"groupTotal": 90}}]}],
                    }
                ]
            }
        ),
    )
    monkeypatch.setattr(litellm, "get_key_info", AsyncMock(return_value={"user_id": "ann", "team_id": "eng"}))
    monkeypatch.setattr(api_v1, "check_key_rate_limit", lambda user: None)
    monkeypatch.setattr(keys, "check_key_rate_limit", lambda user: None)
    return CurrentUser(user_id="ann", email="ann@example.invalid", role="admin")


@pytest.mark.parametrize("count", [2, 3])
def test_multiple_keys_cannot_each_receive_the_entire_share(enabled, count):
    with pytest.raises(HTTPException) as error:
        guards.guard_single_key([{}] * count)
    assert error.value.status_code == 409


def test_one_existing_key_blocks_additional_credentials(enabled):
    with pytest.raises(HTTPException) as error:
        guards.guard_new_key([{}])
    assert error.value.status_code == 409
    guards.guard_single_key([{}])
    guards.guard_new_key([])


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ["api", "owner"])
async def test_admin_cannot_delete_enforced_key(enabled, monkeypatch, route):
    deletion = AsyncMock()
    monkeypatch.setattr(litellm, "delete_key", deletion)
    monkeypatch.setattr(litellm, "list_user_keys", AsyncMock(return_value=[{"token": "key"}]))
    with pytest.raises(HTTPException) as error:
        if route == "api":
            await api_v1.api_delete_key(KeyDeleteRequest(key="key"), ApiActor(enabled))
        else:
            await keys._delete_owned_key("key", enabled)
    assert error.value.status_code == 409
    deletion.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [{"key": "key"}, {"keys": ["key"]}])
async def test_admin_cannot_reset_enforced_spend(enabled, monkeypatch, payload):
    reset = AsyncMock()
    monkeypatch.setattr(litellm, "reset_key_spend", reset)
    body = BulkKeyResetSpendRequest.model_validate(payload)
    try:
        result = await api_v1.api_reset_key_spend(body, ApiActor(enabled))
    except HTTPException as error:
        assert body.uses_legacy_single_key and error.status_code == 409
    else:
        assert result["failed"] == 1 and result["reset"] == 0
    reset.assert_not_awaited()


@pytest.mark.asyncio
async def test_ordinary_user_still_fails_authorization_before_metadata_lookup(enabled, monkeypatch):
    lookup = AsyncMock()
    monkeypatch.setattr(litellm, "get_key_info", lookup)
    with pytest.raises(HTTPException) as error:
        await api_v1.api_delete_key(KeyDeleteRequest(key="key"), ApiActor(CurrentUser(user_id="ann", email="ann@example.invalid")))
    assert error.value.status_code == 403
    lookup.assert_not_awaited()


@pytest.mark.asyncio
async def test_disabled_guards_preserve_existing_behavior(enabled, monkeypatch):
    monkeypatch.setattr(settings, "hierarchical_budgets_enforced", False)
    lookup = AsyncMock()
    monkeypatch.setattr(litellm, "get_key_info", lookup)
    await guards.guard_erase_key("key")
    guards.guard_single_key([{}, {}])
    guards.guard_new_key([{}])
    lookup.assert_not_awaited()


@pytest.mark.asyncio
async def test_unmanaged_key_is_not_blocked_but_stored_managed_identity_is(enabled, monkeypatch):
    monkeypatch.setattr(litellm, "get_key_info", AsyncMock(return_value={"user_id": "outside", "team_id": "external"}))
    await guards.guard_erase_key("outside-key")
    organization_store.remember("outside", "outside@example.invalid", "sso", [])
    organization_store.bind_team("outside", "eng")
    with pytest.raises(HTTPException) as error:
        await guards.guard_erase_key("outside-key")
    assert error.value.status_code == 409


@pytest.mark.asyncio
async def test_missing_owner_metadata_cannot_authorize_destructive_operation(enabled, monkeypatch):
    monkeypatch.setattr(litellm, "get_key_info", AsyncMock(return_value={"team_id": "external"}))
    with pytest.raises(HTTPException) as error:
        await guards.guard_erase_key("key")
    assert error.value.status_code == 502


@pytest.mark.asyncio
async def test_explicit_managed_user_is_protected_even_before_first_login(enabled, monkeypatch):
    monkeypatch.setattr(litellm, "get_key_info", AsyncMock(return_value={"user_id": "ann", "team_id": "external"}))
    with pytest.raises(HTTPException) as error:
        await guards.guard_erase_key("key")
    assert error.value.status_code == 409
