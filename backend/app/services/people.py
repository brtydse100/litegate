"""Bounded read-only directory; LiteLLM remains the source of registered people."""

import asyncio
import json

import httpx
from fastapi import HTTPException

from app.config import settings
from app.services.litellm_client import client, headers

MAX_RESPONSE_BYTES = 2 * 1024 * 1024
ERROR = "LiteLLM people directory is unavailable or returned an invalid page"


def _text(value, *, required=False, limit=512):
    if value is None and not required:
        return None
    if not isinstance(value, str) or len(value) > limit or (required and not value.strip()):
        raise ValueError("Invalid directory field")
    return value


def _page(data, page, size):
    if not isinstance(data, dict):
        raise ValueError("Invalid directory")
    total, pages, batch = data.get("total"), data.get("total_pages"), data.get("users")
    if (
        type(total) is not int
        or not 0 <= total <= 1_000_000_000
        or type(pages) is not int
        or pages != (total + size - 1) // size
        or type(data.get("page")) is not int
        or data["page"] != page
        or type(data.get("page_size")) is not int
        or data["page_size"] != size
        or not isinstance(batch, list)
        or len(batch) != min(size, max(0, total - (page - 1) * size))
    ):
        raise ValueError("Invalid directory pagination")
    rows, seen = [], set()
    for value in batch:
        if not isinstance(value, dict):
            raise ValueError("Invalid person")
        user_id = _text(value.get("user_id"), required=True)
        if user_id in seen:
            raise ValueError("Duplicate person")
        seen.add(user_id)
        rows.append({"user_id": user_id, "email": _text(value.get("user_email")), "upstream_role": _text(value.get("user_role"), limit=100)})
    return {"users": rows, "total": total, "total_pages": pages, "page": page, "size": size}


async def directory(*, page: int, size: int, search: str) -> dict:
    params = {"page": page, "page_size": size, "sort_by": "user_id", "sort_order": "asc"}
    if search:
        params["user_email"] = search
    try:
        async with asyncio.timeout(20):
            async with (
                client() as pooled,
                pooled.stream(
                    "GET", f"{settings.litellm_url.rstrip('/')}/user/list", params=params, headers=headers(), timeout=15, follow_redirects=False
                ) as response,
            ):
                response.raise_for_status()
                content = bytearray()
                async for chunk in response.aiter_bytes():
                    content.extend(chunk)
                    if len(content) > MAX_RESPONSE_BYTES:
                        raise ValueError("Directory page too large")
            return _page(json.loads(content), page, size)
    except (httpx.HTTPError, ValueError, TypeError, RecursionError, TimeoutError):
        raise HTTPException(status_code=502, detail=ERROR) from None
