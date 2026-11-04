"""Narrow identity contracts verified against the pinned LiteLLM endpoints."""

import httpx
from fastapi import HTTPException

from app.config import settings
from app.services.litellm_client import client, headers, transport_error

OWNER_FIELD = "litegate_organization_owner"


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
