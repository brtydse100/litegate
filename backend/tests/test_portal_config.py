import httpx
import pytest

from app.main import app
from app.config import settings


@pytest.mark.parametrize(
    "url",
    [
        "",
        "https://litellm.example.com/ui/model_hub",
        "https://litellm.example.com/proxy/ui/model_hub/?view=public#models",
        "https://litellm.example.com/",
    ],
)
async def test_portal_config_preserves_configured_hub_destination(monkeypatch, url):
    monkeypatch.setattr(settings, "litellm_ui_url", url)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.get("/api/portal-config")

    assert response.status_code == 200
    assert response.json()["litellm_ui_url"] == url
