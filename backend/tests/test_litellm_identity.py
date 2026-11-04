from contextlib import asynccontextmanager

import httpx
import pytest
from fastapi import HTTPException

from app.services import litellm_identity as remote


def transport(monkeypatch, handler):
    @asynccontextmanager
    async def client():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as connection:
            yield connection

    monkeypatch.setattr(remote, "client", client)


@pytest.mark.asyncio
async def test_user_info_unwraps_and_rejects_phantom_user(monkeypatch):
    transport(monkeypatch, lambda _: httpx.Response(200, json={"user_id": "missing", "user_info": None, "keys": []}))
    assert await remote.get_user("missing") is None
    transport(
        monkeypatch,
        lambda _: httpx.Response(
            200,
            json={
                "user_id": "present",
                "user_info": {"user_id": "present", "user_email": "alice@example.com", "metadata": {"litegate_organization_owner": "token"}},
                "keys": [],
            },
        ),
    )
    assert (await remote.get_user("present"))["metadata"]["litegate_organization_owner"] == "token"
