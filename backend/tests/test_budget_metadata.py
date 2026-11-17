"""Unknown source policy must not release another group's allowance."""

from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.services import budget_pass, litellm
from tests.test_budget_enforcement import org, join


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "info, status",
    [
        ({"user_id": "ann", "spend": 0, "team_id": "sales"}, 409),
        ({"user_id": "ann", "spend": 0}, 502),
        ({"user_id": "other", "spend": 0, "team_id": "eng"}, 502),
    ],
)
async def test_incomplete_team_metadata_never_allows_unverified_transfer(org, monkeypatch, info, status):
    org()
    join("ann")
    key = {"token": "original", "user_id": "ann", "spend": 0, "max_budget": 90}
    monkeypatch.setattr(litellm, "list_user_keys", AsyncMock(side_effect=lambda user: [key] if user == "ann" else []))
    lookup = AsyncMock(return_value=info)
    monkeypatch.setattr(litellm, "get_key_info", lookup)
    update = AsyncMock()
    operation = AsyncMock()
    monkeypatch.setattr(litellm, "update_key", update)
    with pytest.raises(HTTPException) as exc:
        await budget_pass.serialized(operation)()
    assert exc.value.status_code == status
    lookup.assert_awaited_once_with("original")
    update.assert_not_awaited()
    operation.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("hydrate", [True, False])
async def test_verified_null_team_is_distinct_from_missing_metadata(org, monkeypatch, hydrate):
    org()
    join("ann")
    key = {"token": "original", "user_id": "ann", "spend": 0, "max_budget": 90}
    if not hydrate:
        key["team_id"] = None
    monkeypatch.setattr(litellm, "list_user_keys", AsyncMock(side_effect=lambda user: [key] if user == "ann" else []))
    lookup = AsyncMock(return_value={**key, "token": "untrusted-replacement", "team_id": None})
    monkeypatch.setattr(litellm, "get_key_info", lookup)

    @budget_pass.serialized
    async def operation():
        observed = (await budget_pass.keys("ann"))[0]
        assert "team_id" in observed and observed["team_id"] is None
        assert observed["token"] == "original"

    await operation()
    assert lookup.await_count == int(hydrate)
