"""Compatibility checks against a real LiteLLM proxy and PostgreSQL database."""

import os
from uuid import uuid4

import pytest

from app.services import litellm


pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_LITELLM_INTEGRATION") != "1",
    reason="requires the opt-in LiteLLM integration stack",
)


@pytest.mark.asyncio
async def test_user_team_and_key_contracts_against_litellm():
    suffix = uuid4().hex[:12]
    user_id = f"litegate-integration-{suffix}"
    email = f"{user_id}@example.invalid"
    team_id = f"team-{suffix}"
    key = ""
    team_created = False

    try:
        created_user = await litellm.create_user(user_id, email)
        assert created_user.get("user_id") == user_id
        user = await litellm.get_user(user_id)
        assert user is not None
        assert user.get("user_id") == user_id

        created_team = await litellm.create_team(
            {
                "team_id": team_id,
                "team_alias": f"LiteGate integration {suffix}",
                "models": [],
                "max_budget": 10,
            }
        )
        team_created = True
        assert created_team.get("team_id") == team_id
        assert (await litellm.get_team(team_id) or {}).get("team_id") == team_id

        await litellm.add_team_member(team_id, user_id)
        assert team_id in await litellm.list_user_team_ids(user_id)

        generated = await litellm.generate_key(
            user_id,
            email,
            team_id,
            key_alias=f"integration-{suffix}",
        )
        key = generated["key"]
        info = await litellm.get_key_info(key)
        assert info is not None
        assert info.get("user_id") == user_id
        assert info.get("team_id") == team_id

        reset = await litellm.reset_key_spend(key)
        assert reset.get("spend") == 0
        assert reset.get("previous_spend") == 0

        await litellm.update_key(key, {"key_alias": f"updated-{suffix}", "blocked": True})
        updated = await litellm.get_key_info(key)
        assert updated is not None
        assert updated.get("key_alias") == f"updated-{suffix}"
        assert updated.get("blocked") is True

        listed = await litellm.list_keys(page=1, size=100, user_id=user_id)
        assert any(item.get("user_id") == user_id for item in listed["keys"])

        updated_team = await litellm.update_team(team_id, {"team_alias": f"Updated {suffix}"})
        assert updated_team.get("team_alias") == f"Updated {suffix}"
    finally:
        if key:
            await litellm.delete_key(key)
        if team_created and await litellm.get_team(team_id):
            await litellm.delete_team(team_id)
