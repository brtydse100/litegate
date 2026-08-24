"""Public HTTP contracts for the reset-spend endpoint."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi import HTTPException

from app.main import app
from app.rate_limit import _key_ops
from app.routers import auth


def _client() -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app, client=("192.0.2.10", 12345))
    return httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
        follow_redirects=False,
    )


@pytest.fixture(autouse=True)
def clear_key_throttle():
    _key_ops.clear()


@pytest.mark.asyncio
async def test_non_admin_spend_reset_is_denied_before_litellm_is_called():
    token = auth._make_jwt("user-1", "user@example.com")
    with patch("app.routers.api_v1.llm.reset_key_spend", new=AsyncMock()) as reset:
        async with _client() as client:
            response = await client.post(
                "/api/v1/keys/reset-spend",
                json={"keys": ["sk-owned", "sk-other"]},
                headers={"Authorization": f"Bearer {token}"},
            )

    assert response.status_code == 403
    assert "sk-owned" not in str(response.request.url)
    assert "sk-other" not in str(response.request.url)
    reset.assert_not_awaited()


@pytest.mark.asyncio
async def test_admin_can_reset_multiple_keys_through_public_api():
    token = auth._make_jwt("admin-1", "admin@example.com", role="admin")
    with (
        patch(
            "app.routers.api_v1.llm.reset_key_spend",
            new=AsyncMock(return_value={"spend": 0.0}),
        ) as reset,
        patch("app.routers.api_v1._record_audit", new=AsyncMock()),
    ):
        async with _client() as client:
            response = await client.post(
                "/api/v1/keys/reset-spend",
                json={"keys": ["key-1", "key-2"]},
                headers={"Authorization": f"Bearer {token}"},
            )

    assert response.status_code == 200
    assert response.json() == {
        "reset": 2,
        "failed": 0,
        "results": [
            {"key": "key-1", "reset": True},
            {"key": "key-2", "reset": True},
        ],
    }
    assert reset.await_count == 2


@pytest.mark.asyncio
async def test_single_item_keys_array_keeps_bulk_response_contract():
    token = auth._make_jwt("admin-1", "admin@example.com", role="admin")
    with (
        patch(
            "app.routers.api_v1.llm.reset_key_spend",
            new=AsyncMock(return_value={"spend": 0.0, "previous_spend": 8.75}),
        ),
        patch("app.routers.api_v1._record_audit", new=AsyncMock()),
    ):
        async with _client() as client:
            response = await client.post(
                "/api/v1/keys/reset-spend",
                json={"keys": ["key-1"]},
                headers={"Authorization": f"Bearer {token}"},
            )

    assert response.status_code == 200
    assert response.json() == {
        "reset": 1,
        "failed": 0,
        "results": [{"key": "key-1", "reset": True}],
    }


@pytest.mark.asyncio
async def test_admin_can_reset_spend_with_legacy_single_key_payload():
    token = auth._make_jwt("admin-1", "admin@example.com", role="admin")
    with (
        patch(
            "app.routers.api_v1.llm.reset_key_spend",
            new=AsyncMock(return_value={"spend": 0.0, "previous_spend": 8.75}),
        ) as reset,
        patch("app.routers.api_v1._record_audit", new=AsyncMock()),
    ):
        async with _client() as client:
            response = await client.post(
                "/api/v1/keys/reset-spend",
                json={"key": "key-1"},
                headers={"Authorization": f"Bearer {token}"},
            )

    assert response.status_code == 200
    assert response.json() == {"reset": True, "spend": 0.0, "previous_spend": 8.75}
    reset.assert_awaited_once_with("key-1")


@pytest.mark.asyncio
async def test_legacy_single_key_reset_preserves_downstream_error_response():
    token = auth._make_jwt("admin-1", "admin@example.com", role="admin")
    with (
        patch(
            "app.routers.api_v1.llm.reset_key_spend",
            new=AsyncMock(side_effect=HTTPException(status_code=502, detail="LiteLLM returned 500")),
        ),
        patch("app.routers.api_v1._record_audit", new=AsyncMock()) as audit,
    ):
        async with _client() as client:
            response = await client.post(
                "/api/v1/keys/reset-spend",
                json={"key": "key-1"},
                headers={"Authorization": f"Bearer {token}"},
            )

    assert response.status_code == 502
    assert response.json() == {"detail": "LiteLLM returned 500"}
    audit.assert_not_awaited()


@pytest.mark.asyncio
async def test_reset_spend_rejects_ambiguous_request_shapes():
    token = auth._make_jwt("admin-1", "admin@example.com", role="admin")
    with patch("app.routers.api_v1.llm.reset_key_spend", new=AsyncMock()) as reset:
        async with _client() as client:
            response = await client.post(
                "/api/v1/keys/reset-spend",
                json={"key": "key-1", "keys": ["key-2"]},
                headers={"Authorization": f"Bearer {token}"},
            )

    assert response.status_code == 422
    reset.assert_not_awaited()
