"""Shared HTTP transport and dependency health for LiteLLM."""

import contextvars
import json
from contextlib import asynccontextmanager, contextmanager

import httpx
from fastapi import HTTPException

from app.config import settings

_shared_client: httpx.AsyncClient | None = None
# Team records read during one reconciliation step; any write empties it.
_team_cache: contextvars.ContextVar[dict | None] = contextvars.ContextVar("team_info_cache", default=None)


async def _forget_on_write(request: httpx.Request) -> None:
    cache = _team_cache.get()
    if cache and request.method != "GET":
        cache.clear()


@contextmanager
def team_cache():
    """Reuse team reads within a block; an unhooked test client disables it."""
    hooked = _shared_client is None or _forget_on_write in _shared_client.event_hooks.get("request", [])
    token = _team_cache.set({} if hooked else None)
    try:
        yield
    finally:
        _team_cache.reset(token)


def cached_teams() -> dict | None:
    return _team_cache.get()


def headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {settings.litellm_master_key}"}


async def start_client() -> None:
    global _shared_client
    if _shared_client is None:
        _shared_client = httpx.AsyncClient(
            verify=settings.ssl_verify,
            base_url=settings.litellm_url.rstrip("/"),
            headers=headers(),
            timeout=httpx.Timeout(15.0, connect=5.0),
            limits=httpx.Limits(max_connections=50, max_keepalive_connections=20),
            event_hooks={"request": [_forget_on_write]},
        )


async def close_client() -> None:
    global _shared_client
    if _shared_client is not None:
        await _shared_client.aclose()
        _shared_client = None


@asynccontextmanager
async def client():
    """Use the application pool, with an isolated fallback for unit tests."""
    if _shared_client is not None:
        yield _shared_client
        return
    async with httpx.AsyncClient(verify=settings.ssl_verify, event_hooks={"request": [_forget_on_write]}) as isolated:
        yield isolated


async def get_bounded_json(path: str, *, max_bytes: int, timeout: float, params: dict | None = None):
    """Stream a GET without redirects and stop once the body exceeds ``max_bytes``."""
    async with (
        client() as pooled,
        pooled.stream(
            "GET", f"{settings.litellm_url.rstrip('/')}{path}", params=params, headers=headers(), timeout=timeout, follow_redirects=False
        ) as response,
    ):
        response.raise_for_status()
        content = bytearray()
        async for chunk in response.aiter_bytes():
            content.extend(chunk)
            if len(content) > max_bytes:
                raise ValueError("LiteLLM response too large")
    return json.loads(content)


def transport_error(_: httpx.TransportError) -> None:
    raise HTTPException(status_code=503, detail=f"Cannot reach LiteLLM at {settings.litellm_url}")


async def healthcheck() -> dict:
    """Check LiteLLM reachability and master-key acceptance."""
    try:
        async with client() as pooled:
            response = await pooled.get(
                f"{settings.litellm_url}/key/list",
                params={"page": 1, "size": 1, "return_full_object": "false"},
                headers=headers(),
                timeout=5,
            )
        if response.status_code in {401, 403}:
            return {"ok": False, "detail": "LiteLLM rejected the configured master key"}
        response.raise_for_status()
        return {"ok": True, "detail": "Connected"}
    except httpx.TransportError:
        return {"ok": False, "detail": f"Cannot reach LiteLLM at {settings.litellm_url}"}
    except httpx.HTTPStatusError as exc:
        return {"ok": False, "detail": f"LiteLLM returned {exc.response.status_code}"}
