from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from app.models import BulkKeyUpdateRequest, CurrentUser
from app.rate_limit import _key_ops
from app.routers.api_v1 import ApiActor, bulk_update_keys


def setup_function():
    _key_ops.clear()


@pytest.mark.asyncio
async def test_user_can_bulk_update_only_owned_keys():
    actor = ApiActor(CurrentUser(user_id="user-1", email="u@example.com"))
    payload = BulkKeyUpdateRequest(keys=["owned-key"], settings={"rpm_limit": 25})
    with (
        patch("app.routers.api_v1.llm.list_user_keys", new=AsyncMock(return_value=[{"token": "owned-key"}])),
        patch("app.routers.api_v1.llm.update_key", new=AsyncMock(return_value={})) as update,
    ):
        result = await bulk_update_keys(payload, actor)
    assert result["updated"] == 1
    update.assert_awaited_once_with("owned-key", {"rpm_limit": 25})


@pytest.mark.asyncio
async def test_user_cannot_bulk_update_unowned_key():
    actor = ApiActor(CurrentUser(user_id="user-1", email="u@example.com"))
    payload = BulkKeyUpdateRequest(keys=["someone-elses-key"], settings={"blocked": True})
    with patch("app.routers.api_v1.llm.list_user_keys", new=AsyncMock(return_value=[{"token": "owned-key"}])):
        with pytest.raises(HTTPException) as exc:
            await bulk_update_keys(payload, actor)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_key_proof_can_update_only_itself():
    actor = ApiActor(
        CurrentUser(user_id="key-holder", email="", auth_source="litellm_key"),
        proof_key="sk-proof",
    )
    payload = BulkKeyUpdateRequest(keys=["different-key"], settings={"tpm_limit": 100})
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
