import json
import pytest
from app.services.organization_mapping import load_mapping

DATA = {
    "groups": {
        "company": {"team_id": "c"},
        "engineering": {"team_id": "e", "parent": "company", "members": ["Alice@Example.com"]},
        "platform": {"team_id": "p", "parent": "engineering", "members": [" alice@example.com "]},
    }
}


def test_hierarchy_order_and_sso_primary(tmp_path):
    path = tmp_path / "mapping.json"
    path.write_text(json.dumps(DATA), encoding="utf-8")
    for mapping in (load_mapping(DATA, ""), load_mapping({}, str(path))):
        assert mapping.member_emails() == ["alice@example.com"]
        assert mapping.team_ids("ALICE@example.com", []) == ["p", "e", "c"]
        assert mapping.team_ids("alice@example.com", ["outside", "e"]) == ["outside", "e", "p", "c"]
        assert mapping.team_ids("other@example.com", ["e"]) == ["e", "c"]


@pytest.mark.parametrize(
    "groups",
    [
        {"a": {"team_id": "a", "parent": "missing"}},
        {"a": {"team_id": "a", "parent": "a"}},
        {"a": {"team_id": "a"}, "b": {"team_id": "a"}},
        {"a": {"team_id": "a", "extra": 1}},
        {"a": {"team_id": "a", "members": ["invalid"]}},
        {"a": {"team_id": " "}},
    ],
)
def test_invalid_hierarchies_rejected(groups):
    with pytest.raises(ValueError):
        load_mapping({"groups": groups}, "")


def test_conflicting_sources_are_rejected(tmp_path):
    path = tmp_path / "mapping.json"
    path.write_text("{}")
    with pytest.raises(ValueError):
        load_mapping(DATA, str(path))


def test_file_snapshot_does_not_reload_without_restart(tmp_path, monkeypatch):
    from app.services import organization_mapping as service

    settings = service.settings

    path = tmp_path / "snapshot.json"
    path.write_text(json.dumps(DATA), encoding="utf-8")
    monkeypatch.setattr(settings, "organization_mapping", {})
    monkeypatch.setattr(settings, "organization_mapping_file", str(path))
    assert hasattr(service, "get_mapping"), "startup and login need one shared mapping snapshot"
    snapshot = service.get_mapping()
    path.write_text("{}", encoding="utf-8")
    assert service.get_mapping() is snapshot
    assert snapshot.team_ids("alice@example.com", []) == ["p", "e", "c"]


def test_root_members_never_inherit_children_and_equal_depth_uses_order():
    mapping = load_mapping(
        {
            "groups": {
                "root": {"team_id": "root", "members": ["root@example.com"]},
                "z-first": {"team_id": "first", "parent": "root", "members": ["both@example.com"]},
                "a-second": {"team_id": "second", "parent": "root", "members": ["both@example.com"]},
            }
        },
        "",
    )
    assert mapping.team_ids("root@example.com", []) == ["root"]
    assert mapping.team_ids("both@example.com", []) == ["first", "second", "root"]


@pytest.mark.parametrize("data", [[], {"extra": {}}, {"groups": []}, {"groups": {"bad": {"team_id": "x", "members": "a@example.com"}}}])
def test_invalid_mapping_shape_is_rejected(data):
    with pytest.raises(ValueError):
        load_mapping(data, "")


def test_missing_and_malformed_files_are_rejected(tmp_path):
    path = tmp_path / "bad.json"
    with pytest.raises(ValueError):
        load_mapping({}, str(path))
    path.write_text("{broken", encoding="utf-8")
    with pytest.raises(ValueError):
        load_mapping({}, str(path))


def test_levels_json_and_inline_match_flat_resolution(tmp_path):
    data = {
        "levels": [
            {"name": "companies", "groups": {"company": DATA["groups"]["company"]}},
            {"name": "departments", "groups": {"engineering": DATA["groups"]["engineering"]}},
            {
                "name": "teams",
                "groups": {
                    "platform": DATA["groups"]["platform"],
                    "support": {"team_id": "support", "parent": "engineering", "members": ["support@example.com"]},
                },
            },
        ]
    }
    path = tmp_path / "levels.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    for mapping in (load_mapping(data, ""), load_mapping({}, str(path))):
        assert mapping.team_ids("alice@example.com", []) == ["p", "e", "c"]
        assert mapping.team_ids("alice@example.com", ["outside", "e"]) == ["outside", "e", "p", "c"]
        assert mapping.team_ids("support@example.com", []) == ["support", "e", "c"]
        assert mapping.member_emails() == ["alice@example.com", "support@example.com"]
        assert mapping.referenced_team_ids() == ["c", "e", "p", "support"]


def test_levels_keep_array_order_for_equal_depth_assignments():
    data = {
        "levels": [
            {"name": "z-first", "groups": {"first": {"team_id": "first", "members": ["both@example.com"]}}},
            {"name": "a-second", "groups": {"second": {"team_id": "second", "members": ["both@example.com"]}}},
        ]
    }
    assert load_mapping(data, "").team_ids("both@example.com", []) == ["first", "second"]
    assert load_mapping({"levels": []}, "").referenced_team_ids() == []


@pytest.mark.parametrize(
    "data",
    [
        {"levels": {}},
        {"levels": [None]},
        {"levels": [{"groups": {}}]},
        {"levels": [{"name": " ", "groups": {}}]},
        {"levels": [{"name": "teams", "groups": []}]},
        {"levels": [{"name": "teams", "groups": {}, "extra": True}]},
        {"levels": [{"name": "Teams", "groups": {}}, {"name": " teams ", "groups": {}}]},
        {"levels": [{"name": "one", "groups": {"a": {"team_id": "a"}}}, {"name": "two", "groups": {"a": {"team_id": "b"}}}]},
        {"levels": [], "groups": {}},
        {"groups": {"levels": []}},
    ],
)
def test_invalid_or_ambiguous_levels_are_rejected(data):
    with pytest.raises(ValueError):
        load_mapping(data, "")
