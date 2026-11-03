"""Opt-in ownership, duplicate-email, and keyless contracts for pinned LiteLLM."""

import os
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.services import litellm
from app.services import litellm_identity as remote

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_LITELLM_INTEGRATION") != "1",
    reason="requires the opt-in pinned LiteLLM integration stack",
)


@pytest.mark.asyncio
async def test_ordinary_keyless_creation_roundtrips_ownership_and_rejects_duplicate_email():
    suffix = uuid4().hex[:12]
    user_id = f"litegate-org:integration-{suffix}"
    email = f"identity-{suffix}@example.invalid"
    marker = uuid4().hex
    team_id = f"identity-team-{suffix}"
    team_created = False
    try:
        await remote.create_reserved_user(user_id, email, marker)
        user = await remote.get_user(user_id)
        assert user["user_id"] == user_id
        assert user["user_email"] == email
        assert user["user_role"] == "internal_user"
        assert user["metadata"][remote.OWNER_FIELD] == marker
        assert (await litellm.get_user(user_id))["keys"] == []
        assert [u["user_id"] for u in await remote.find_users_by_email(email.upper())] == [user_id]
        with pytest.raises(HTTPException):
            await remote.create_reserved_user(f"other-{suffix}", email, "other-marker")
        assert await remote.get_user(f"other-{suffix}") is None
        assert (await remote.get_user(user_id))["metadata"][remote.OWNER_FIELD] == marker
        await litellm.create_team({"team_id": team_id, "team_alias": f"Identity integration {suffix}"})
        team_created = True
        await litellm.sync_user_team_memberships(user_id, email, [team_id])
        await litellm.sync_user_team_memberships(user_id, email, [team_id])
        assert team_id in await litellm.list_user_team_ids(user_id)
        assert (await litellm.get_user(user_id))["keys"] == []
    finally:
        if team_created:
            await litellm.delete_team(team_id)
        # Keep the user row: the feature never deletes or transfers user records.
