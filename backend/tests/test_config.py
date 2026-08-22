import os
import pytest


def test_yaml_list_is_loaded_without_mutating_environment(tmp_path, monkeypatch):
    (tmp_path / "config.yaml").write_text(
        "key_models:\n  - gpt-4\n  - gpt-3.5-turbo\n"
    )
    monkeypatch.setenv("LITELLM_MASTER_KEY", "sk-test")
    monkeypatch.setenv("JWT_SECRET", "x" * 32)
    monkeypatch.delenv("KEY_MODELS", raising=False)

    import app.config as cfg_module
    monkeypatch.setattr(cfg_module, "_BACKEND_DIR", tmp_path)
    configured = cfg_module.Settings(
        litellm_master_key="sk-test",
        jwt_secret="x" * 32,
    )

    assert configured.key_models_list == ["gpt-4", "gpt-3.5-turbo"]
    assert "KEY_MODELS" not in os.environ


def test_yaml_mapping_is_loaded_as_structured_data(tmp_path, monkeypatch):
    (tmp_path / "config.yaml").write_text(
        "oidc_group_team_mapping:\n"
        "  Engineering: team-engineering\n"
        "  Platform:\n"
        "    - team-platform\n"
        "    - team-shared\n"
    )
    monkeypatch.delenv("OIDC_GROUP_TEAM_MAPPING", raising=False)

    import app.config as cfg_module
    monkeypatch.setattr(cfg_module, "_BACKEND_DIR", tmp_path)
    configured = cfg_module.Settings(
        litellm_master_key="sk-test",
        jwt_secret="x" * 32,
    )

    assert configured.oidc_group_team_mapping == {
        "Engineering": "team-engineering",
        "Platform": ["team-platform", "team-shared"],
    }


def test_environment_takes_precedence_over_yaml(tmp_path, monkeypatch):
    (tmp_path / "config.yaml").write_text('litellm_master_key: "from-yaml"\n')
    monkeypatch.setenv("LITELLM_MASTER_KEY", "from-env")
    monkeypatch.setenv("JWT_SECRET", "x" * 32)

    import app.config as cfg_module
    monkeypatch.setattr(cfg_module, "_BACKEND_DIR", tmp_path)
    configured = cfg_module.Settings(jwt_secret="x" * 32)

    assert configured.litellm_master_key == "from-env"


def test_key_models_list_parses_json(monkeypatch):
    monkeypatch.setenv("LITELLM_MASTER_KEY", "sk-test")
    monkeypatch.setenv("JWT_SECRET", "x" * 32)
    monkeypatch.setenv("KEY_MODELS", '["gpt-4","gpt-3.5-turbo"]')

    # Re-import to pick up patched env
    import importlib
    import app.config as cfg_module
    importlib.reload(cfg_module)

    assert cfg_module.settings.key_models_list == ["gpt-4", "gpt-3.5-turbo"]


def test_key_models_list_empty_default(monkeypatch):
    monkeypatch.setenv("LITELLM_MASTER_KEY", "sk-test")
    monkeypatch.setenv("JWT_SECRET", "x" * 32)
    monkeypatch.setenv("KEY_MODELS", "[]")

    import importlib
    import app.config as cfg_module
    importlib.reload(cfg_module)

    assert cfg_module.settings.key_models_list == []


def test_admin_identity_supports_nested_group_claim(monkeypatch):
    monkeypatch.setenv("LITELLM_MASTER_KEY", "sk-test")
    monkeypatch.setenv("JWT_SECRET", "x" * 32)
    monkeypatch.setenv("ADMIN_GROUPS", "Platform Admins,LLM Operators")
    monkeypatch.setenv("OIDC_GROUPS_CLAIM", "realm_access.roles")

    import importlib
    import app.config as cfg_module
    importlib.reload(cfg_module)

    assert cfg_module.settings.is_admin_identity(
        "user@example.com", {"realm_access": {"roles": ["viewer", "llm operators"]}}
    )
    assert not cfg_module.settings.is_admin_identity(
        "user@example.com", {"realm_access": {"roles": ["viewer"]}}
    )


def test_group_team_mapping_is_case_insensitive_ordered_and_deduplicated():
    from app.config import Settings

    configured = Settings(
        litellm_master_key="sk-test",
        jwt_secret="x" * 32,
        oidc_groups_claim="realm_access.roles",
        oidc_group_team_mapping={
            "Platform": ["team-platform", "team-shared"],
            "ENGINEERING": ["team-shared", "team-engineering"],
            "Finance": "team-finance",
        },
    )

    claims = {"realm_access": {"roles": [" engineering ", "platform", "PLATFORM"]}}
    assert configured.oidc_groups(claims) == ["engineering", "platform"]
    assert configured.mapped_team_ids(claims) == [
        "team-platform",
        "team-shared",
        "team-engineering",
    ]


def test_group_team_mapping_supports_single_string_claim_and_team():
    from app.config import Settings

    configured = Settings(
        litellm_master_key="sk-test",
        jwt_secret="x" * 32,
        oidc_group_team_mapping={"Research": "team-research"},
    )

    assert configured.mapped_team_ids({"groups": "research"}) == ["team-research"]


def test_security_warnings_flag_weak_remote_deployment_settings():
    from app.config import Settings

    configured = Settings(
        litellm_master_key="sk-test",
        jwt_secret="change-me",
        root_url="http://litegate.example.com",
        local_auth_username="admin",
        local_auth_password="changeme",
        management_api_key="short-key",
    )

    warnings = configured.security_warnings
    assert len(warnings) == 4
    assert any("JWT_SECRET" in warning for warning in warnings)
    assert any("HTTPS" in warning for warning in warnings)


def test_security_warnings_accept_strong_local_settings():
    from app.config import Settings

    configured = Settings(
        litellm_master_key="sk-test",
        jwt_secret="x" * 32,
        root_url="http://localhost:8080",
        local_auth_username="admin",
        local_auth_password="a-strong-local-password",
        management_api_key="m" * 32,
    )

    assert configured.security_warnings == []


def test_security_warnings_reject_a_weak_previous_session_secret():
    from app.config import Settings

    configured = Settings(
        litellm_master_key="sk-test",
        jwt_secret="x" * 32,
        jwt_previous_secrets="short-old-secret",
        root_url="http://localhost:8080",
    )

    assert any("JWT_PREVIOUS_SECRETS" in warning for warning in configured.security_warnings)
