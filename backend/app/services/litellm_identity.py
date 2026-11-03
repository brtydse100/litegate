"""Narrow identity contracts verified against the pinned LiteLLM endpoints."""

import httpx
from fastapi import HTTPException

from app.config import settings
from app.services.litellm_client import client, headers, transport_error

OWNER_FIELD = "litegate_organization_owner"
MAX_LOOKUP_USERS = 10_000
PAGE_SIZE = 100


async def _request(method: str, path: str, **kwargs) -> httpx.Response:
    try:
        async with client() as connection:
            response = await connection.request(method, f"{settings.litellm_url}{path}", headers=headers(), timeout=15, **kwargs)
        return response
    except httpx.TransportError as exc:
        transport_error(exc)


def _check(response: httpx.Response) -> dict:
    if response.is_error:
        raise HTTPException(502, f"LiteLLM identity operation returned {response.status_code}")
    try:
        data = response.json()
    except ValueError as exc:
        raise HTTPException(502, "LiteLLM identity response is invalid") from exc
    if not isinstance(data, dict):
        raise HTTPException(502, "LiteLLM identity response is invalid")
    return data


async def get_user(user_id: str) -> dict | None:
    response = await _request("GET", "/user/info", params={"user_id": user_id})
    if response.status_code == 404:
        return None
    data = _check(response)
    info = data.get("user_info")
    if info is None:
        return None
    if not isinstance(info, dict) or info.get("user_id") != user_id:
        raise HTTPException(502, "LiteLLM identity response did not identify the requested user")
    return info


async def find_users_by_email(email: str) -> list[dict]:
    email = email.strip().casefold()
    matches: dict[str, dict] = {}
    expected_total = None
    scanned = 0
    page = 1
    while True:
        data = _check(await _request("GET", "/user/list", params={
            "user_email": email, "page": page, "page_size": PAGE_SIZE, "sort_by": "user_id", "sort_order": "asc",
        }))
        total, total_pages, users = data.get("total"), data.get("total_pages"), data.get("users")
        if (
            type(total) is not int or total < 0 or total > MAX_LOOKUP_USERS
            or type(total_pages) is not int or total_pages != (total + PAGE_SIZE - 1) // PAGE_SIZE
            or data.get("page") != page or data.get("page_size") != PAGE_SIZE or not isinstance(users, list)
            or len(users) != min(PAGE_SIZE, max(0, total - scanned))
            or (expected_total is not None and total != expected_total)
        ):
            raise HTTPException(502, "LiteLLM email lookup was incomplete or exceeded the safety limit")
        expected_total = total
        for user in users:
            if not isinstance(user, dict) or not isinstance(user.get("user_id"), str):
                raise HTTPException(502, "LiteLLM email lookup returned an invalid user")
            if str(user.get("user_email") or "").strip().casefold() == email:
                matches[user["user_id"]] = user
        scanned += len(users)
        if page >= total_pages:
            return list(matches.values())
        page += 1


async def create_reserved_user(user_id: str, email: str, ownership_token: str) -> None:
    _check(await _request("POST", "/user/new", json={
        "user_id": user_id, "user_email": email, "auto_create_key": False,
        "user_role": "internal_user", "metadata": {OWNER_FIELD: ownership_token},
    }))
