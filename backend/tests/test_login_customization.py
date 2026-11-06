import httpx
import pytest

from app import config
from app.main import app
from app.routers import auth


@pytest.mark.parametrize("login_text,logo_url", [("", ""), ("Welcome to Example\nUse your work account. <b>Help</b>", "/logo.svg")])
async def test_public_auth_config_exposes_only_login_options(monkeypatch, login_text, logo_url):
    configured = config.Settings(
        litellm_master_key="test-master-key",
        jwt_secret="test-secret-at-least-32-characters",
        login_text=login_text,
        logo_url=logo_url,
        local_users_enabled=True,
        oidc_issuer_url="",
    )
    monkeypatch.setattr(auth, "settings", configured)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.get("/api/auth/config")

    assert response.status_code == 200
    assert response.json() == {
        "sso_enabled": False,
        "local_enabled": True,
        "login_text": login_text,
        "logo_url": logo_url,
    }


def test_login_customization_defaults_yaml_and_environment_precedence(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "_BACKEND_DIR", tmp_path)
    monkeypatch.delenv("LOGIN_TEXT", raising=False)
    monkeypatch.delenv("LOGO_URL", raising=False)
    assert config.Settings().login_text == ""

    (tmp_path / "config.yaml").write_text('login_text: |\n  Welcome to Example\n  Use your work account.\nlogo_url: "/logo.svg"\n')
    configured = config.Settings()
    assert configured.login_text == "Welcome to Example\nUse your work account.\n"
    assert configured.logo_url == "/logo.svg"

    monkeypatch.setenv("LOGIN_TEXT", "Environment welcome")
    monkeypatch.setenv("LOGO_URL", "https://images.example.com/logo.png")
    configured = config.Settings()
    assert configured.login_text == "Environment welcome"
    assert configured.logo_url == "https://images.example.com/logo.png"

    monkeypatch.setenv("LOGIN_TEXT", "")
    monkeypatch.setenv("LOGO_URL", "")
    configured = config.Settings()
    assert configured.login_text == ""
    assert configured.logo_url == ""
