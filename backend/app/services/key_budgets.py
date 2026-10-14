"""Explicit administrator migration from user caps to individual key caps."""

import math

import httpx
from fastapi import HTTPException

from app.config import settings
from app.services import litellm
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
        if not isinstance(memberships, list):
            raise HTTPException(status_code=502, detail="Cannot verify the team-member budget on this LiteLLM version")
        matched = False
        for member in memberships:
            if isinstance(member, dict) and member.get("user_id") == user_id:
                matched = True
                budget = member.get("litellm_budget_table")
                if budget is not None and not isinstance(budget, dict):
                    raise HTTPException(status_code=502, detail="Cannot verify the team-member budget record")
                if (isinstance(budget, dict) and budget.get("max_budget") is not None) or (budget is None and member.get("budget_id")):
                    raise HTTPException(status_code=502, detail="LiteLLM kept the team-member budget")
                if "litellm_budget_table" not in member or (isinstance(budget, dict) and "max_budget" not in budget):
                    raise HTTPException(status_code=502, detail="Cannot verify the team-member budget fields")
        if not matched:
            raise HTTPException(status_code=502, detail="LiteLLM did not confirm the target team membership")
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
