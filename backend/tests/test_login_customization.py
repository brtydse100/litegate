import httpx
import pytest

from app import config, main
from app.main import app
from app.routers import auth


@pytest.mark.parametrize("login_text,logo_url", [("", ""), ("Welcome to Example\nUse your work account. <b>Help</b>", "/logo.svg")])
async def test_public_auth_config_exposes_only_login_options(monkeypatch, login_text, logo_url):
    configured = config.Settings(
        litellm_master_key="test-master-key",
        jwt_secret="test-secret-at-least-32-characters",
        login_text=login_text,
        my_key_text="Only for signed-in My key page",
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
    monkeypatch.delenv("MY_KEY_TEXT", raising=False)
    monkeypatch.delenv("LOGO_URL", raising=False)
    assert config.Settings().login_text == ""
    assert config.Settings().my_key_text == ""

    (tmp_path / "config.yaml").write_text(
        'login_text: |\n  Welcome to Example\n  Use your work account.\nmy_key_text: |\n  Keep your key safe.\n  Contact support for help.\nlogo_url: "/logo.svg"\n'
    )
    configured = config.Settings()
    assert configured.login_text == "Welcome to Example\nUse your work account.\n"
    assert configured.logo_url == "/logo.svg"
    assert configured.my_key_text == "Keep your key safe.\nContact support for help.\n"

    monkeypatch.setenv("LOGIN_TEXT", "Environment welcome")
    monkeypatch.setenv("MY_KEY_TEXT", "Environment key guidance")
    monkeypatch.setenv("LOGO_URL", "https://images.example.com/logo.png")
    configured = config.Settings()
    assert configured.login_text == "Environment welcome"
    assert configured.my_key_text == "Environment key guidance"
    assert configured.logo_url == "https://images.example.com/logo.png"

    monkeypatch.setenv("LOGIN_TEXT", "")
    monkeypatch.setenv("MY_KEY_TEXT", "")
    monkeypatch.setenv("LOGO_URL", "")
    configured = config.Settings()
    assert configured.login_text == ""
    assert configured.my_key_text == ""
    assert configured.logo_url == ""


@pytest.mark.parametrize("message", ["", " \n ", "Keep your key safe.\n<b>Contact support</b>"])
async def test_public_portal_config_exposes_my_key_message_without_login_text(monkeypatch, message):
    monkeypatch.setattr(main.settings, "my_key_text", message)
    monkeypatch.setattr(main.settings, "login_text", "Separate login welcome")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.get("/api/portal-config")

    assert response.status_code == 200
    assert response.json()["my_key_text"] == message
    assert "login_text" not in response.json()
