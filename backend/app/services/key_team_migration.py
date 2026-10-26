"""Assign existing personal keys to the primary configured SSO team."""

import asyncio

from fastapi import HTTPException

from app.services import audit, organization_sync
from app.services import litellm as llm


async def migrate_user_keys(user_id: str, email: str, team_id: str) -> int:
    """Move owned keys to the configured team; repeated logins resume partial moves."""
    async with organization_sync.lock_for("user", user_id):
        keys = await llm.list_user_keys(user_id)
        return await _migrate_user_keys(user_id, email, team_id, keys)


async def _migrate_user_keys(user_id: str, email: str, team_id: str, keys: list[dict | str]) -> int:
    if len(keys) > 500:
        raise HTTPException(status_code=409, detail="User has more than the safe migration limit of 500 keys")
    moved = 0
    for key in keys:
        if isinstance(key, dict):
            identifier = key.get("token") or key.get("api_key") or key.get("key")
        else:
            identifier = key
        if not identifier:
            continue
        # Membership/configuration changes may race login; recheck the live record.
        info = await llm.get_key_info(identifier)
        if not info or info.get("user_id") != user_id or info.get("team_id") == team_id:
            continue
        await llm.update_key(identifier, {"team_id": team_id})
        updated = await llm.get_key_info(identifier)
        if not updated or updated.get("user_id") != user_id or updated.get("team_id") != team_id:
            raise HTTPException(status_code=502, detail="Could not verify key team migration. Please retry signing in.")
        await asyncio.to_thread(
            audit.record,
            actor_id=user_id,
            actor_email=email,
            action="key.team_migrate",
            target=user_id,
            details={"destination_team_id": team_id, "keys_moved": 1},
        )
        moved += 1
    return moved
