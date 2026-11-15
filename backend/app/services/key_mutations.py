"""Coordinate administrative key mutations with personal key rotation."""

from contextlib import asynccontextmanager

from fastapi import HTTPException

from app.services import litellm, organization_sync


@asynccontextmanager
async def locked_key(key: str):
    info = await litellm.get_key_info(key)
    if not info:
        raise HTTPException(status_code=404, detail="Key not found")
    owner = info.get("user_id")
    async with organization_sync.lock_for("user" if owner else "key", owner or key):
        current = await litellm.get_key_info(key)
        if not current or current.get("user_id") != owner:
            raise HTTPException(status_code=409, detail="Key was replaced, deleted or changed owner; refresh the key list and retry")
        yield current
