import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException


@pytest.mark.asyncio
async def test_get_user_returns_none_on_404():
    mock_response = MagicMock()
    mock_response.status_code = 404

    with patch("httpx.AsyncClient") as mock_client_class:
        instance = AsyncMock()
        instance.get = AsyncMock(return_value=mock_response)
        mock_client_class.return_value.__aenter__ = AsyncMock(return_value=instance)
        mock_client_class.return_value.__aexit__ = AsyncMock(return_value=False)

        from app.services.litellm import get_user
        result = await get_user("missing-user")
        assert result is None


@pytest.mark.asyncio
async def test_get_user_raises_503_on_transport_error():
    with patch("httpx.AsyncClient") as mock_client_class:
        instance = AsyncMock()
        instance.get = AsyncMock(side_effect=httpx.ConnectError("refused"))
        mock_client_class.return_value.__aenter__ = AsyncMock(return_value=instance)
        mock_client_class.return_value.__aexit__ = AsyncMock(return_value=False)

        from app.services.litellm import get_user
        with pytest.raises(HTTPException) as exc:
            await get_user("any-user")
        assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_get_user_raises_502_on_http_status_error():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock(
        side_effect=httpx.HTTPStatusError("401", request=MagicMock(), response=MagicMock(status_code=401))
    )

    with patch("httpx.AsyncClient") as mock_client_class:
        instance = AsyncMock()
        instance.get = AsyncMock(return_value=mock_response)
        mock_client_class.return_value.__aenter__ = AsyncMock(return_value=instance)
        mock_client_class.return_value.__aexit__ = AsyncMock(return_value=False)

        from app.services.litellm import get_user
        with pytest.raises(HTTPException) as exc:
            await get_user("any-user")
        assert exc.value.status_code == 502


@pytest.mark.asyncio
async def test_ensure_user_exists_returns_none_on_error():
    with patch("app.services.litellm.get_user", side_effect=HTTPException(status_code=503, detail="down")):
        from app.services.litellm import ensure_user_exists
        result = await ensure_user_exists("user-1", "user@example.com")
        assert result is None


@pytest.mark.asyncio
async def test_generate_key_sets_alias_from_email():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json = MagicMock(return_value={"key": "sk-abc", "user_id": "u1"})

    captured: dict = {}

    async def fake_post(url, json, headers, timeout):
        captured.update(json)
        return mock_response

    with patch("httpx.AsyncClient") as mock_client_class:
        instance = AsyncMock()
        instance.post = fake_post
        mock_client_class.return_value.__aenter__ = AsyncMock(return_value=instance)
        mock_client_class.return_value.__aexit__ = AsyncMock(return_value=False)

        from app.services.litellm import generate_key
        await generate_key("user-1", "alice@example.com")

    assert captured.get("key_alias") == "alice's key"
