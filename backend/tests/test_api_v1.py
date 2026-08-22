from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from app.models import ApiKeyCreateRequest, BulkKeyUpdateRequest, CurrentUser, KeyDeleteRequest
from app.rate_limit import _key_ops
from app.routers.api_v1 import (
    ApiActor,
    api_create_key,
    api_delete_key,
    api_list_key_identifiers,
    api_me,
    bulk_update_keys,
)


def setup_function():
    _key_ops.clear()


@pytest.mark.asyncio
async def test_api_me_includes_mapped_teams():
    actor = ApiActor(
        CurrentUser(user_id="user-1", email="u@example.com", team_ids=["team-primary"])
    )

    result = await api_me(actor)

    assert result["team_ids"] == ["team-primary"]


@pytest.mark.asyncio
async def test_user_cannot_bulk_update_keys():
    actor = ApiActor(CurrentUser(user_id="user-1", email="u@example.com"))
    payload = BulkKeyUpdateRequest(keys=["owned-key"], settings={"rpm_limit": 25})
    with patch("app.routers.api_v1.llm.update_key", new=AsyncMock(return_value={})) as update:
        with pytest.raises(HTTPException) as exc:
            await bulk_update_keys(payload, actor)
    assert exc.value.status_code == 403
    update.assert_not_awaited()


@pytest.mark.asyncio
async def test_key_proof_cannot_bulk_update_keys():
    actor = ApiActor(
        CurrentUser(user_id="key-holder", email="", auth_source="litellm_key"),
        proof_key="sk-proof",
    )
    payload = BulkKeyUpdateRequest(keys=["sk-proof"], settings={"tpm_limit": 100})
    with pytest.raises(HTTPException) as exc:
        await bulk_update_keys(payload, actor)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_admin_can_update_multiple_keys():
    actor = ApiActor(CurrentUser(user_id="admin", email="a@example.com", role="admin"))
    payload = BulkKeyUpdateRequest(keys=["key-1", "key-2"], settings={"models": ["gpt-4o"]})
    with patch("app.routers.api_v1.llm.update_key", new=AsyncMock(return_value={})) as update:
        result = await bulk_update_keys(payload, actor)
    assert result["updated"] == 2
    assert update.await_count == 2


@pytest.mark.asyncio
async def test_admin_can_list_all_key_identifiers():
    actor = ApiActor(CurrentUser(user_id="admin", email="a@example.com", role="admin"))
    with patch(
        "app.routers.api_v1.llm.list_key_identifiers",
        new=AsyncMock(return_value=["key-1", "key-2"]),
    ):
        result = await api_list_key_identifiers(actor)
    assert result == {"keys": ["key-1", "key-2"], "total": 2}


@pytest.mark.asyncio
async def test_user_cannot_list_all_key_identifiers():
    actor = ApiActor(CurrentUser(user_id="user-1", email="u@example.com"))
    with pytest.raises(HTTPException) as exc:
        await api_list_key_identifiers(actor)
    assert exc.value.status_code == 403


def test_bulk_update_accepts_more_than_one_page_of_keys():
    payload = BulkKeyUpdateRequest(
        keys=[f"key-{index}" for index in range(125)],
        settings={"rpm_limit": 25},
    )
    assert len(payload.keys) == 125


@pytest.mark.asyncio
async def test_portal_user_api_key_uses_primary_sso_team():
    actor = ApiActor(
        CurrentUser(
            user_id="user-1",
            email="u@example.com",
            team_ids=["team-primary", "team-secondary"],
        )
    )
    with (
        patch("app.routers.api_v1.llm.list_user_keys", new=AsyncMock(return_value=[])),
        patch(
            "app.routers.api_v1.llm.generate_key",
            new=AsyncMock(return_value={"key": "sk-new", "user_id": "user-1"}),
        ) as generate,
    ):
        result = await api_create_key(None, actor)

    assert result.key == "sk-new"
    generate.assert_awaited_once_with("user-1", "u@example.com", "team-primary")


@pytest.mark.asyncio
async def test_admin_api_does_not_apply_own_team_to_another_user():
    actor = ApiActor(
        CurrentUser(
            user_id="admin",
            email="admin@example.com",
            role="admin",
            team_ids=["team-admin"],
        )
    )
    payload = ApiKeyCreateRequest(user_id="other-user", email="other@example.com")
    with (
        patch("app.routers.api_v1.llm.list_user_keys", new=AsyncMock(return_value=[])),
        patch(
            "app.routers.api_v1.llm.generate_key",
            new=AsyncMock(return_value={"key": "sk-new", "user_id": "other-user"}),
        ) as generate,
    ):
        await api_create_key(payload, actor)

    generate.assert_awaited_once_with("other-user", "other@example.com", None)


@pytest.mark.asyncio
async def test_litellm_key_can_delete_itself_but_not_another_key():
    actor = ApiActor(
        CurrentUser(user_id="user-1", email="", auth_source="litellm_key"),
        proof_key="sk-self",
    )
    with patch("app.routers.api_v1.llm.delete_key", new=AsyncMock()) as delete:
        result = await api_delete_key(KeyDeleteRequest(key="sk-self"), actor)
        with pytest.raises(HTTPException) as exc:
            await api_delete_key(KeyDeleteRequest(key="sk-other"), actor)

    assert result == {"deleted": True}
    assert exc.value.status_code == 403
    delete.assert_awaited_once_with("sk-self")
