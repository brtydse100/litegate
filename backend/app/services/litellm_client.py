"""Shared HTTP transport and dependency health for LiteLLM."""

from contextlib import asynccontextmanager

import httpx
from fastapi import HTTPException

from app.config import settings

_shared_client: httpx.AsyncClient | None = None


def headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {settings.litellm_master_key}"}


async def start_client() -> None:
    global _shared_client
    if _shared_client is None:
        _shared_client = httpx.AsyncClient(
            base_url=settings.litellm_url.rstrip("/"),
            headers=headers(),
            timeout=httpx.Timeout(15.0, connect=5.0),
            limits=httpx.Limits(max_connections=50, max_keepalive_connections=20),
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
    async with httpx.AsyncClient() as isolated:
        yield isolated


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
