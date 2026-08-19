import os
import json
import pytest


def test_yaml_list_converted_to_json(tmp_path, monkeypatch):
    (tmp_path / "config.yaml").write_text(
        "key_models:\n  - gpt-4\n  - gpt-3.5-turbo\n"
    )
    monkeypatch.setenv("LITELLM_MASTER_KEY", "sk-test")
    monkeypatch.setenv("JWT_SECRET", "x" * 32)
    monkeypatch.delenv("KEY_MODELS", raising=False)

    import app.config as cfg_module
    monkeypatch.setattr(cfg_module, "_BACKEND_DIR", tmp_path)
    cfg_module._load_yaml_config()

    parsed = json.loads(os.environ["KEY_MODELS"])
    assert parsed == ["gpt-4", "gpt-3.5-turbo"]


def test_yaml_skips_keys_already_in_env(tmp_path, monkeypatch):
    (tmp_path / "config.yaml").write_text('litellm_master_key: "from-yaml"\n')
    monkeypatch.setenv("LITELLM_MASTER_KEY", "from-env")
    monkeypatch.setenv("JWT_SECRET", "x" * 32)

    import app.config as cfg_module
    monkeypatch.setattr(cfg_module, "_BACKEND_DIR", tmp_path)
    cfg_module._load_yaml_config()

    assert os.environ["LITELLM_MASTER_KEY"] == "from-env"


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
