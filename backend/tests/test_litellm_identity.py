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
async def test_exact_email_scans_all_substring_pages(monkeypatch):
    pages = []

    def handler(request):
        page = int(request.url.params["page"])
        pages.append(page)
        assert request.url.params["user_email"] == "alice@example.com"
        assert request.url.params["sort_by"] == "user_id"
        users = (
            [{"user_id": str(index), "user_email": "extra-alice@example.com"} for index in range(100)]
            if page == 1
            else [{"user_id": "two", "user_email": " Alice@Example.COM "}]
        )
        return httpx.Response(200, json={"users": users, "total": 101, "page": page, "page_size": 100, "total_pages": 2})

    transport(monkeypatch, handler)
    assert [u["user_id"] for u in await remote.find_users_by_email(" ALICE@EXAMPLE.COM ")] == ["two"]
    assert pages == [1, 2]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        {"users": [], "total": 101, "page": 1, "page_size": 100, "total_pages": 2},
        {"users": [], "total": 10001, "page": 1, "page_size": 100, "total_pages": 101},
        {"users": [], "total": 1, "page": 2, "page_size": 100, "total_pages": 1},
        {"users": []},
    ],
)
async def test_incomplete_or_unbounded_search_fails_closed(monkeypatch, response):
    transport(monkeypatch, lambda _: httpx.Response(200, json=response))
    with pytest.raises(HTTPException):
        await remote.find_users_by_email("alice@example.com")


@pytest.mark.asyncio
async def test_duplicate_page_records_fail_closed(monkeypatch):
    transport(
        monkeypatch,
        lambda _: httpx.Response(
            200,
            json={
                "users": [{"user_id": "repeated", "user_email": "alice@example.com"}] * 2,
                "total": 2,
                "page": 1,
                "page_size": 100,
                "total_pages": 1,
            },
        ),
    )
    with pytest.raises(HTTPException):
        await remote.find_users_by_email("alice@example.com")


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


@pytest.mark.asyncio
async def test_creation_is_ordinary_keyless_with_ownership_evidence(monkeypatch):
    import json

    def handler(request):
        assert request.url.path == "/user/new"
        assert json.loads(request.content) == {
            "user_id": "reserved",
            "user_email": "alice@example.com",
            "auto_create_key": False,
            "user_role": "internal_user",
            "metadata": {"litegate_organization_owner": "intent"},
        }
        return httpx.Response(200, json={"user_id": "reserved"})

    transport(monkeypatch, handler)
    await remote.create_reserved_user("reserved", "alice@example.com", "intent")
