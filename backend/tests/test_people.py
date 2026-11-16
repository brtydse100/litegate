from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.models import CurrentUser
from app.routers.api_actor import ApiActor, get_api_actor
from app.services import litellm_client


@pytest.fixture
def transport():
    def factory(data, requests):
        @asynccontextmanager
        async def pooled():
            async def respond(request):
                requests.append(request)
                return httpx.Response(200, json=data)

            async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
                yield client

        return pooled

    return factory


@pytest.mark.asyncio
async def test_directory_includes_sso_without_keys_and_strips_private_fields(transport):
    from app.services import people

    data = {
        "users": [
            {
                "user_id": "sso-id",
                "user_email": "sso@example.com",
                "user_role": "internal_user",
                "sso_user_id": "subject",
                "key_count": 0,
                "password": "hidden",
                "metadata": {"token": "hidden"},
            }
        ],
        "total": 1,
        "total_pages": 1,
        "page": 1,
        "page_size": 25,
    }
    requests = []
    with patch.object(litellm_client, "client", transport(data, requests)):
        result = await people.directory(page=1, size=25, search="sso@")
    assert result == {
        "users": [{"user_id": "sso-id", "email": "sso@example.com", "upstream_role": "internal_user"}],
        "total": 1,
        "total_pages": 1,
        "page": 1,
        "size": 25,
    }
    assert requests[0].url.path == "/user/list"
    assert requests[0].url.params["user_email"] == "sso@"
    assert requests[0].url.params["page_size"] == "25"
    assert "key" not in str(result)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "override", [{"total": True}, {"page": 2}, {"page_size": 100}, {"total_pages": 10}, {"users": []}, {"users": [{"user_id": ""}]}]
)
async def test_directory_rejects_invalid_or_incomplete_upstream(override, transport):
    from fastapi import HTTPException
    from app.services import people

    data = {"users": [{"user_id": "u"}], "total": 1, "total_pages": 1, "page": 1, "page_size": 25, **override}
    with patch.object(litellm_client, "client", transport(data, [])):
        with pytest.raises(HTTPException) as failure:
            await people.directory(page=1, size=25, search="")
    assert failure.value.status_code == 502


@pytest.mark.parametrize("role,source,expected", [("user", "sso", 403), ("user", "litellm_key", 403), ("admin", "sso", 200)])
def test_directory_authorization_before_remote_query(role, source, expected):
    from app.routers import people

    app = FastAPI()
    app.include_router(people.router, prefix="/api/v1")
    actor = ApiActor(CurrentUser(user_id="u", email="u@example.com", role=role, auth_source=source))
    app.dependency_overrides[get_api_actor] = lambda: actor
    with patch.object(people.people, "directory", AsyncMock(return_value={"users": []})) as directory:
        response = TestClient(app).get("/api/v1/people")
    assert response.status_code == expected
    assert directory.await_count == int(expected == 200)


def test_directory_query_bounds():
    from app.routers import people

    app = FastAPI()
    app.include_router(people.router, prefix="/api/v1")
    app.dependency_overrides[get_api_actor] = lambda: ApiActor(CurrentUser(user_id="a", email="", role="admin"))
    with patch.object(people.people, "directory", AsyncMock(return_value={})) as directory:
        for query in ("size=101", "page=0", "search=" + "a" * 201):
            assert TestClient(app).get("/api/v1/people?" + query).status_code == 422
        directory.assert_not_awaited()
