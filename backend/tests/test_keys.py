from unittest.mock import AsyncMock, patch

import pytest

from app.models import CurrentUser
from app.rate_limit import _key_ops
from app.routers.keys import create_key, regenerate_key


def setup_function():
    _key_ops.clear()


@pytest.mark.asyncio
async def test_create_key_uses_primary_sso_team():
    user = CurrentUser(
        user_id="user-1",
        email="user@example.com",
        team_ids=["team-primary", "team-secondary"],
    )
    with (
        patch("app.routers.keys.llm.list_user_keys", new=AsyncMock(return_value=[])),
        patch(
            "app.routers.keys.llm.generate_key",
            new=AsyncMock(return_value={"key": "sk-new", "user_id": "user-1"}),
        ) as generate,
    ):
        result = await create_key(user)

    assert result.key == "sk-new"
    generate.assert_awaited_once_with("user-1", "user@example.com", "team-primary")


@pytest.mark.asyncio
async def test_regenerate_key_uses_primary_sso_team():
    user = CurrentUser(
        user_id="user-1",
        email="user@example.com",
        team_ids=["team-primary"],
    )
    with (
        patch(
            "app.routers.keys.llm.list_user_keys",
            new=AsyncMock(return_value=[{"token": "sk-old"}]),
        ),
        patch("app.routers.keys.llm.delete_key", new=AsyncMock()),
        patch(
            "app.routers.keys.llm.generate_key",
            new=AsyncMock(return_value={"key": "sk-new", "user_id": "user-1"}),
        ) as generate,
    ):
        result = await regenerate_key(user)

    assert result.key == "sk-new"
    generate.assert_awaited_once_with("user-1", "user@example.com", "team-primary")
