import httpx
import pytest

from app.main import app


@pytest.mark.asyncio
async def test_cookie_authenticated_cross_site_mutation_is_rejected():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        client.cookies.set("litegate_session", "signed-session")
        response = await client.post(
            "/api/auth/logout",
            headers={"Origin": "https://attacker.example"},
        )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_same_host_cookie_mutation_is_allowed():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        client.cookies.set("litegate_session", "signed-session")
        response = await client.post(
            "/api/auth/logout",
            headers={"Origin": "http://testserver"},
        )

    assert response.status_code == 200
    assert response.json() == {"signed_out": True}
