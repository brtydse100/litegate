"""JSON file input uses the existing hierarchy semantics and settings precedence."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

import app.config as config


TREE = {
    "levels": [
        {
            "name": "Division",
            "groups": [
                {
                    "members": [
                        {
                            "name": "Engineering",
                            "litellmTeamId": "engineering",
                            "userIds": ["Alice@Example.com", "local:alice"],
                            "ssoGroups": ["engineers"],
                            "budget": {"perUser": 50, "groupTotal": 5000, "duration": "30d"},
                        }
                    ]
                }
            ],
        }
    ]
}


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "_BACKEND_DIR", tmp_path)
    monkeypatch.delenv("ORGANIZATION_HIERARCHY", raising=False)
    monkeypatch.delenv("ORGANIZATION_HIERARCHY_FILE", raising=False)


def write_tree(tmp_path, value=TREE):
    path = tmp_path / "organization.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def test_file_loads_existing_sso_email_group_and_budget_semantics(tmp_path):
    path = write_tree(tmp_path)
    tree = config.Settings(organization_hierarchy_file=str(path)).organization_hierarchy
    node = tree.resolve("subject", [], email="alice@example.com", source="sso")
    assert node.team_id == "engineering"
    assert node.per_user == 50
    assert node.duration == "30d"
    assert node.member.budget.groupTotal == 5000
    assert tree.resolve("subject", ["ENGINEERS"]) == node
    assert tree.resolve("local:alice", []) == node
    assert tree.resolve("subject", [], email="alice@example.com", source="local") is None


@pytest.mark.parametrize("inline", [{}, {"levels": []}])
def test_relative_path_uses_backend_directory_and_empty_inline_is_allowed(tmp_path, monkeypatch, inline):
    write_tree(tmp_path)
    other = tmp_path / "cwd"
    other.mkdir()
    monkeypatch.chdir(other)
    assert config.Settings(organization_hierarchy_file="organization.json", organization_hierarchy=inline).organization_hierarchy.levels


def test_nonempty_inline_conflicts_with_file(tmp_path):
    with pytest.raises(ValidationError, match="organization_hierarchy.*organization_hierarchy_file"):
        config.Settings(organization_hierarchy=TREE, organization_hierarchy_file=str(write_tree(tmp_path)))


@pytest.mark.parametrize(
    "content", ["{", "[]", "null", '{"organizationHierarchy": {"levels": []}}', '{"levels": "bad"}', '{"levels": [{"name": "x", "groups": []}]}']
)
def test_invalid_file_fails_actionably(tmp_path, content):
    path = tmp_path / "invalid.json"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(ValidationError, match="organization_hierarchy_file.*invalid.json"):
        config.Settings(organization_hierarchy_file=str(path))


@pytest.mark.parametrize("destination", ["missing.json", "."])
def test_missing_or_unreadable_file_fails(tmp_path, destination):
    with pytest.raises(ValidationError, match="organization_hierarchy_file"):
        config.Settings(organization_hierarchy_file=destination)


def test_permission_error_fails_actionably(tmp_path, monkeypatch):
    path = write_tree(tmp_path)
    original = Path.read_text

    def denied(self, *args, **kwargs):
        if self == path:
            raise PermissionError("permission denied")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", denied)
    with pytest.raises(ValidationError, match="organization_hierarchy_file.*permission denied"):
        config.Settings(organization_hierarchy_file=str(path))


def test_invalid_utf8_fails_actionably(tmp_path):
    path = tmp_path / "invalid.json"
    path.write_bytes(b"\xff")
    with pytest.raises(ValidationError, match="organization_hierarchy_file"):
        config.Settings(organization_hierarchy_file=str(path))


def test_environment_file_overrides_yaml_and_init_overrides_environment(tmp_path, monkeypatch):
    write_tree(tmp_path)
    (tmp_path / "config.yaml").write_text("organization_hierarchy_file: missing.json\n", encoding="utf-8")
    monkeypatch.setenv("ORGANIZATION_HIERARCHY_FILE", "organization.json")
    assert config.Settings().organization_hierarchy.levels
    assert not config.Settings(organization_hierarchy_file="").organization_hierarchy.levels


@pytest.mark.parametrize("alias", ["organizationHierarchy", "organization_hierarchy"])
def test_environment_empty_inline_overrides_yaml_before_conflict_detection(tmp_path, monkeypatch, alias):
    write_tree(tmp_path)
    (tmp_path / "config.yaml").write_text(json.dumps({alias: TREE, "organization_hierarchy_file": "organization.json"}), encoding="utf-8")
    monkeypatch.setenv("ORGANIZATION_HIERARCHY", '{"levels": []}')
    assert config.Settings().organization_hierarchy.levels


def test_empty_file_preserves_inline_environment_and_yaml(tmp_path, monkeypatch):
    monkeypatch.setenv("ORGANIZATION_HIERARCHY", json.dumps(TREE))
    assert config.Settings(organization_hierarchy_file="").organization_hierarchy.levels
    monkeypatch.delenv("ORGANIZATION_HIERARCHY")
    (tmp_path / "config.yaml").write_text(json.dumps({"organizationHierarchy": TREE}), encoding="utf-8")
    assert config.Settings().organization_hierarchy.levels


@pytest.mark.parametrize("value", [{}, {"levels": []}])
def test_empty_hierarchy_file_is_valid(tmp_path, value):
    assert not config.Settings(organization_hierarchy_file=str(write_tree(tmp_path, value))).organization_hierarchy.levels


def test_file_uses_existing_tree_semantic_validation(tmp_path):
    value = json.loads(json.dumps(TREE))
    del value["levels"][0]["groups"][0]["members"][0]["litellmTeamId"]
    with pytest.raises(ValidationError, match="requires litellmTeamId"):
        config.Settings(organization_hierarchy_file=str(write_tree(tmp_path, value)))


def test_utf8_file_is_loaded_once_per_settings_construction(tmp_path):
    value = json.loads(json.dumps(TREE))
    value["levels"][0]["groups"][0]["members"][0]["name"] = "?quipe"
    path = tmp_path / "organization.json"
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    configured = config.Settings(organization_hierarchy_file=str(path))
    path.write_text('{"levels": []}', encoding="utf-8")
    assert configured.organization_hierarchy.resolve("local:alice", []).member.name == "?quipe"
    assert not config.Settings(organization_hierarchy_file=str(path)).organization_hierarchy.levels
