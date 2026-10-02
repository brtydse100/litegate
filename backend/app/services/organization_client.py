"""LiteLLM contracts for organization budgets, keys, and daily aggregates."""

import asyncio
import math

import httpx
from fastapi import HTTPException

from app.config import settings
from app.organization import OrganizationNode
from app.services import key_cleanup, key_secrets, litellm
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
    if default_member_budget(info) is not None:
        await litellm.update_team(root.team_id, {"team_member_budget": None})
        info = await team_info(root.team_id)
    actual = info.get("team_info")
    if not isinstance(actual, dict) or any(actual.get(key) != value for key, value in policy.items()):
        raise HTTPException(status_code=502, detail="LiteLLM did not apply the top-level budget policy")
    if default_member_budget(info) is not None:
        raise HTTPException(status_code=502, detail="LiteLLM did not clear the managed team's default member budget")
    return info


def membership(info: dict, user_id: str) -> dict | None:
    return next((item for item in info.get("team_memberships", []) if item.get("user_id") == user_id), None)


def default_member_budget(info: dict) -> float | None:
    team = info.get("team_info") or {}
    budget = team.get("team_member_budget_table")
    if budget is None:
        if (team.get("metadata") or {}).get("team_member_budget_id"):
            raise HTTPException(status_code=502, detail="Could not verify LiteLLM's default team-member budget")
        return None
    if not isinstance(budget, dict):
        raise HTTPException(status_code=502, detail="LiteLLM returned an invalid default team-member budget")
    value = budget.get("max_budget")
    return finite_number(value) if value is not None and finite_number(value) > 0 else None


def member_budget(info: dict, user_id: str) -> dict:
    member = membership(info, user_id)
    if member is None:
        raise HTTPException(status_code=502, detail="Could not read your managed LiteLLM membership")
    budget = member.get("litellm_budget_table") or {}
    value = budget.get("max_budget")
    return {
        "per_user": finite_number(value) if value is not None else default_member_budget(info),
        "duration": budget.get("budget_duration"),
        "spend": finite_number(member.get("spend")),
    }


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
        info = verified_info
    actual = member_budget(info, user_id)
    if actual["per_user"] != node.per_user or actual["duration"] != node.duration:
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
    except BaseException:
        await key_cleanup.revoke_created_key(result["key"])
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
    rows, expected_pages = [], None
    page_size, max_pages = 1000, 20
    limit_error = f"Usage exceeds {max_pages} upstream pages for one user; select a shorter date range"
    try:
        async with asyncio.timeout(60):
            for page in range(1, max_pages + 1):
                data = await request(
                    "GET",
                    "/user/daily/activity",
                    params={"user_id": user_id, "start_date": start, "end_date": end, "page": page, "page_size": page_size},
                )
                batch, metadata = data.get("results"), data.get("metadata") or {}
                if not isinstance(batch, list) or len(batch) > page_size or not isinstance(metadata, dict):
                    raise HTTPException(status_code=502, detail="LiteLLM returned an incomplete usage aggregate")
                pages = data.get("total_pages", metadata.get("total_pages"))
                more = metadata.get("has_more", False)
                actual_page = metadata.get("page", data.get("page", page))
                if (
                    type(actual_page) is not int
                    or actual_page != page
                    or type(more) is not bool
                    or (pages is not None and (type(pages) is not int or pages < 0 or (pages > 0 and page > pages) or (pages == 0 and batch)))
                    or (expected_pages is not None and pages != expected_pages)
                ):
                    raise HTTPException(status_code=502, detail="LiteLLM returned invalid analytics pagination")
                if pages is not None:
                    expected_pages = pages
                    if pages > max_pages:
                        raise HTTPException(status_code=422, detail=limit_error)
                    more = more or page < pages
                if more and not batch:
                    raise HTTPException(status_code=502, detail="LiteLLM returned an incomplete usage aggregate")
                rows.extend(batch)
                if not more:
                    return rows
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail="LiteLLM analytics exceeded the 60-second report deadline") from exc
    raise HTTPException(status_code=422, detail=limit_error)
