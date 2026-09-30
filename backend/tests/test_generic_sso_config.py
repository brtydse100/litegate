import pytest
from pydantic import ValidationError

from app.config import Settings


FIELDS = {
    "generic_client_id": "litegate",
    "generic_client_secret": "test-provider-secret",
    "generic_authorization_endpoint": "https://idp.example/authorize",
    "generic_token_endpoint": "https://idp.example/token",
    "generic_userinfo_endpoint": "https://idp.example/userinfo",
}


def configured(**overrides):
    return Settings(litellm_master_key="sk-test", jwt_secret="x" * 32, **({"root_url": "https://portal.example"} | FIELDS | overrides))


def test_generic_yaml_settings_and_environment_override(tmp_path, monkeypatch):
    import app.config as cfg_module

    monkeypatch.setattr(cfg_module, "_BACKEND_DIR", tmp_path)
    content = "\n".join(f"{key}: {value}" for key, value in FIELDS.items())
    (tmp_path / "config.yaml").write_text(content + "\ngeneric_user_id_attribute: employee_id\ngeneric_user_email_attribute: mail\n")
    settings = Settings(root_url="https://portal.example")
    assert settings.sso_enabled and settings.generic_sso_enabled
    assert settings.oidc_issuer_url == ""
    assert settings.generic_user_id_attribute == "employee_id"
    assert settings.generic_user_email_attribute == "mail"
    monkeypatch.setenv("GENERIC_USER_ID_ATTRIBUTE", "sub")
    monkeypatch.setenv("GENERIC_CLIENT_USE_PKCE", "true")
    monkeypatch.setenv("GENERIC_INCLUDE_CLIENT_ID", "false")
    assert Settings(root_url="https://portal.example").generic_user_id_attribute == "sub"
    assert Settings(root_url="https://portal.example").generic_client_use_pkce is True
    assert Settings(root_url="https://portal.example").generic_include_client_id is False


def test_generic_configuration_can_be_supplied_entirely_by_litellm_environment_variables(tmp_path, monkeypatch):
    import app.config as cfg_module

    monkeypatch.setattr(cfg_module, "_BACKEND_DIR", tmp_path)
    for field, value in FIELDS.items():
        monkeypatch.setenv(field.upper(), value)
    monkeypatch.setenv("ROOT_URL", "https://portal.example")
    assert Settings().generic_sso_enabled
    assert Settings().generic_client_id == "litegate"


@pytest.mark.parametrize("field", list(FIELDS))
def test_partial_generic_configuration_fails_at_startup(field):
    with pytest.raises(ValidationError, match="together"):
        configured(**{field: ""})


def test_generic_and_oidc_modes_cannot_be_combined():
    with pytest.raises(ValidationError, match="not both"):
        configured(oidc_issuer_url="https://oidc.example")
    with pytest.raises(ValidationError, match="not both"):
        configured(
            oidc_authorization_endpoint="https://oidc.example/auth",
            oidc_token_endpoint="https://oidc.example/token",
            oidc_jwks_uri="https://oidc.example/keys",
        )


@pytest.mark.parametrize(
    "endpoint",
    ["http://idp.example/userinfo", "https://user:password@idp.example/userinfo", "https://idp.example/userinfo#fragment", "invalid"],
)
def test_generic_provider_urls_require_secure_transport(endpoint):
    with pytest.raises(ValidationError, match="HTTPS"):
        configured(generic_userinfo_endpoint=endpoint)


def test_generic_callback_defaults_to_root_url_and_can_be_overridden():
    assert configured().generic_callback_uri == "https://portal.example/api/auth/callback"
    assert configured(root_url="https://portal.example/").generic_callback_uri == "https://portal.example/api/auth/callback"
    assert configured(generic_redirect_uri="https://callback.example/api/auth/callback").generic_callback_uri.startswith("https://callback.example/")
    assert configured(generic_userinfo_endpoint="http://localhost:9999/userinfo").generic_sso_enabled


@pytest.mark.parametrize("path", ["", ".sub", "identity..sub", "identity."])
def test_invalid_user_attributes_fail_at_startup(path):
    with pytest.raises(ValidationError, match="field paths"):
        configured(generic_user_id_attribute=path)


def test_generic_defaults_and_disabled_sso():
    settings = Settings(litellm_master_key="sk-test", jwt_secret="x" * 32)
    assert not settings.sso_enabled
    settings = configured()
    assert settings.generic_user_id_attribute == "sub"
    assert settings.generic_user_email_attribute == "email"
    assert settings.generic_client_use_pkce is False
    assert settings.generic_include_client_id is True
