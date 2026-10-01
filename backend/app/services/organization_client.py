"""LiteLLM contracts for organization budgets, keys, and daily aggregates."""

import asyncio
import math

import httpx
from fastapi import HTTPException

from app.config import settings
from app.organization import OrganizationNode
from app.services import key_secrets, litellm
from app.services.litellm_client import client, headers, transport_error


async def request(method: str, path: str, *, payload: dict | None = None, params: dict | None = None) -> dict:
    try:
        async with client() as pooled:
            response = await pooled.request(method, f"{settings.litellm_url}{path}", json=payload, params=params, headers=headers(), timeout=20)
        response.raise_for_status()
        value = response.json()
        if not isinstance(value, dict):
            raise HTTPException(status_code=502, detail="LiteLLM returned an invalid organization response")
        return value
    except httpx.TransportError as exc:
        transport_error(exc)
    except (ValueError, httpx.HTTPStatusError) as exc:
        status = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else "invalid JSON"
        raise HTTPException(status_code=502, detail=f"LiteLLM organization operation failed ({status})") from exc


async def team_info(team_id: str) -> dict:
    return await request("GET", "/team/info", params={"team_id": team_id, "key_limit": 1})


async def sync_root(root: OrganizationNode) -> dict:
    existing = await litellm.get_team(root.team_id)
    policy = {"max_budget": root.member.budget.groupTotal, "budget_duration": root.member.budget.duration}
    if existing is None:
        await litellm.create_team({"team_id": root.team_id, "team_alias": root.member.name, **policy})
    elif any(existing.get(key) != value for key, value in policy.items()):
        await litellm.update_team(root.team_id, {key: value for key, value in policy.items() if existing.get(key) != value})
    info = await team_info(root.team_id)
    actual = info.get("team_info")
    if not isinstance(actual, dict) or any(actual.get(key) != value for key, value in policy.items()):
        raise HTTPException(status_code=502, detail="LiteLLM did not apply the top-level budget policy")
    return info


def membership(info: dict, user_id: str) -> dict | None:
    return next((item for item in info.get("team_memberships", []) if item.get("user_id") == user_id), None)


async def sync_member(node: OrganizationNode, user_id: str, info: dict) -> None:
    member = membership(info, user_id)
    budget = member.get("litellm_budget_table") or {} if member else {}
    if member is None:
        await litellm.add_team_member(node.team_id, user_id)
    if member is None or budget.get("max_budget") != node.per_user or budget.get("budget_duration") != node.duration:
        patch = {"max_budget_in_team": node.per_user, "budget_duration": node.duration}
        if member is not None:
            patch = {key: value for key, value in patch.items() if budget.get("max_budget" if key == "max_budget_in_team" else key) != value}
        await request(
            "POST",
            "/team/member_update",
            payload={
                "team_id": node.team_id,
                "user_id": user_id,
                **patch,
            },
        )
        verified_info = await team_info(node.team_id)
        verified = membership(verified_info, user_id)
        actual = verified.get("litellm_budget_table") or {} if verified else {}
        if verified is None or actual.get("max_budget") != node.per_user or actual.get("budget_duration") != node.duration:
            raise HTTPException(status_code=502, detail="LiteLLM did not apply the per-user budget policy; check its version")


async def generate_key(user_id: str, email: str, team_id: str, **options) -> dict:
    name = email.split("@")[0] if email else user_id.split(":")[-1]
    payload = {
        "user_id": user_id,
        "team_id": team_id,
        "key_alias": options.get("key_alias") or f"{name}'s key",
        "max_budget": None,
        "budget_duration": None,
    }
    for field in ("tpm_limit", "rpm_limit", "duration"):
        value = getattr(settings, f"key_{field}")
        if value is not None:
            payload[field] = value
    if settings.key_models_list:
        payload["models"] = settings.key_models_list
    if options.get("initial_spend", 0) > 0:
        payload["spend"] = options["initial_spend"]
    result = await request("POST", "/key/generate", payload=payload)
    if not isinstance(result.get("key"), str) or not result["key"]:
        raise HTTPException(status_code=502, detail="LiteLLM did not return a key")
    try:
        # LiteLLM deployment defaults may add a key cap even to a null request.
        info = await litellm.get_key_info(result["key"])
        if not info or info.get("user_id") != user_id or info.get("team_id") != team_id:
            raise HTTPException(status_code=502, detail="Could not verify the managed key's ownership")
        if info.get("max_budget") is not None or info.get("budget_duration") is not None:
            await litellm.update_key(result["key"], {"max_budget": None, "budget_duration": None})
            verified = await litellm.get_key_info(result["key"])
            if not verified or verified.get("max_budget") is not None or verified.get("budget_duration") is not None:
                raise HTTPException(status_code=502, detail="LiteLLM's key defaults conflict with organization budgets")
        if settings.save_api_keys_in_db:
            await asyncio.to_thread(key_secrets.save, result["key"], user_id)
    except Exception:
        await litellm.delete_key(result["key"])
        raise
    return result


def finite_number(value, *, integer: bool = False) -> float | int:
    try:
        number = float(value or 0)
        if not math.isfinite(number) or number < 0:
            raise ValueError
        return int(number) if integer else number
    except (TypeError, ValueError, OverflowError):
        raise HTTPException(status_code=502, detail="LiteLLM returned invalid usage metrics")


async def daily_usage(user_id: str, start: str, end: str) -> list[dict]:
    data = await request(
        "GET",
        "/user/daily/activity",
        params={
            "user_id": user_id,
            "start_date": start,
            "end_date": end,
            "page": 1,
            "page_size": 1000,
        },
    )
    rows = data.get("results")
    metadata = data.get("metadata") or {}
    if not isinstance(metadata, dict):
        raise HTTPException(status_code=502, detail="LiteLLM returned an incomplete usage aggregate")
    pages = data.get("total_pages", metadata.get("total_pages", 1))
    if not isinstance(rows, list) or len(rows) > 1000 or not isinstance(pages, int) or pages > 1 or metadata.get("has_more"):
        raise HTTPException(status_code=502, detail="LiteLLM returned an incomplete usage aggregate")
    return rows
