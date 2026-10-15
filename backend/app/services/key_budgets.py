"""Explicit administrator migration from user caps to individual key caps."""

import asyncio
import math

import httpx
from fastapi import HTTPException

from app.config import settings
from app.services import litellm, organization_client, organization_store, organization_sync
from app.services.litellm_client import client, headers, transport_error


async def _request(method: str, path: str, **kwargs) -> dict:
    try:
        async with client() as upstream:
            response = await upstream.request(method, f"{settings.litellm_url}{path}", headers=headers(), timeout=10, **kwargs)
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                raise HTTPException(status_code=502, detail="LiteLLM returned an invalid budget response")
            return data
    except httpx.TransportError as exc:
        transport_error(exc)
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=f"LiteLLM budget operation returned {exc.response.status_code}")


async def _remove_individual_caps(user_id: str, team_id: str | None) -> None:
    if team_id:
        await _request("POST", "/team/member_update", json={"team_id": team_id, "user_id": user_id, "max_budget_in_team": None})
        team = await _request("GET", "/team/info", params={"team_id": team_id})
        memberships = team.get("team_memberships")
        if not isinstance(memberships, list) or any(not isinstance(member, dict) for member in memberships):
            raise HTTPException(status_code=502, detail="Cannot verify the team-member budget on this LiteLLM version")
        if organization_client.member_budget(team, user_id)["per_user"] is not None:
            raise HTTPException(status_code=502, detail="LiteLLM kept the team-member budget")
    await _request("POST", "/user/update", json={"user_id": user_id, "max_budget": None})
    user = await litellm.get_user(user_id)
    info = user.get("user_info", user) if isinstance(user, dict) else None
    if not isinstance(info, dict) or "max_budget" not in info or info["max_budget"] is not None:
        raise HTTPException(status_code=502, detail="LiteLLM did not confirm removal of the personal user budget")


async def update_key(key: str, changes: dict, *, use_key_budget_only: bool = False) -> dict:
    if not use_key_budget_only:
        return await litellm.update_key(key, changes)
    info = await litellm.get_key_info(key)
    if not info or not info.get("user_id"):
        raise HTTPException(status_code=422, detail="The key must have an owner before removing user budgets")
    async with organization_sync.lock_for("user", info["user_id"]):
        current = await litellm.get_key_info(key)
        if not current or current.get("user_id") != info["user_id"]:
            raise HTTPException(status_code=409, detail="Key ownership changed; retry the migration")
        await organization_sync.guard_key(key, changes, use_key_budget_only=True)
        return await _migrate_key(key, changes, current)


async def _migrate_key(key: str, changes: dict, info: dict) -> dict:
    budget = changes.get("max_budget", info.get("max_budget"))
    if not isinstance(budget, (int, float)) or not math.isfinite(budget) or budget < 0:
        raise HTTPException(status_code=422, detail="Set a finite key budget before removing separate user budgets")
    user = await litellm.get_user(info["user_id"])
    owner_keys = user.get("keys") if isinstance(user, dict) else None
    if not isinstance(owner_keys, list) or len(owner_keys) != 1:
        raise HTTPException(status_code=422, detail="Key-budget migration requires exactly one key for this owner; user budgets were kept")

    result = await litellm.update_key(key, changes) if changes else {}
    # Establish the key cap before removing either individual ceiling. No spend,
    # role, rate limit, model policy or shared team budget is changed.
    confirmed = await litellm.get_key_info(key)
    if not confirmed or confirmed.get("max_budget") != budget:
        raise HTTPException(status_code=502, detail="Key settings saved, but LiteLLM did not confirm the key budget; user budgets were kept")
    try:
        await _remove_individual_caps(info["user_id"], info.get("team_id"))
    except HTTPException as exc:
        raise HTTPException(
            status_code=exc.status_code, detail=f"Key settings saved; user-budget migration is incomplete. Retry this key. {exc.detail}"
        )
    return result


async def preserve_rotation_budget(user_id: str, existing: list[dict], replacement: str) -> None:
    """Keep a known individual key cap until its replacement is verified."""
    if len(existing) != 1:
        return
    source = existing[0]
    budget = source.get("max_budget")
    if not isinstance(budget, (int, float)) or not math.isfinite(budget) or budget < 0:
        return
    identity = await asyncio.to_thread(organization_store.get, user_id)
    if organization_sync.resolve(user_id, identity["groups"] if identity else []) is not None:
        return
    info = await litellm.get_key_info(replacement)
    if not info or info.get("user_id") != user_id:
        raise HTTPException(status_code=502, detail="Could not verify the replacement key")
    changes = {"max_budget": budget, "budget_duration": source.get("budget_duration")}
    await litellm.update_key(replacement, changes)
    verified = await litellm.get_key_info(replacement)
    if not verified or verified.get("user_id") != user_id or any(verified.get(field) != value for field, value in changes.items()):
        raise HTTPException(status_code=502, detail="LiteLLM did not preserve the replacement key budget")
