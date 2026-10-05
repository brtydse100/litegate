"""Observable configuration, mapping, and budget inheritance contracts."""

from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.config import Settings
from app.organization import MembershipConflict, OrganizationHierarchy


def example():
    return {
        "levels": [
            {
                "name": "Division",
                "groups": [
                    {
                        "members": [
                            {
                                "name": "Engineering",
                                "litellmTeamId": "engineering",
                                "ssoGroups": ["engineers"],
                                "budget": {"duration": "30d", "groupTotal": 5000, "perUser": 200},
                            },
                            {"name": "Marketing", "litellmTeamId": "marketing", "budget": {"perUser": 25}},
                        ]
                    }
                ],
            },
            {
                "name": "Business Unit",
                "groups": [
                    {
                        "parent": "Engineering",
                        "members": [
                            {"name": "Digital", "ssoGroups": ["digital"], "budget": {"perUser": 50}},
                        ],
                    },
                    {"parent": "Marketing", "members": [{"name": "Campaigns"}]},
                ],
            },
            {
                "name": "Squad",
                "groups": [
                    {
                        "parent": "Digital",
                        "members": [
                            {"name": "squad1", "ssoGroups": ["squad1", "external-squad1"], "budget": {"perUser": 100}},
                            {"name": "squad2", "ssoGroups": ["squad2"], "userIds": ["local:alice"]},
                            {"name": "unlimited", "ssoGroups": ["unlimited"], "budget": {"perUser": None}},
                            {"name": "blocked", "ssoGroups": ["blocked"], "budget": {"perUser": 0}},
                        ],
                    }
                ],
            },
        ]
    }


def test_closest_budget_wins_and_multiple_matches_resolve_one_path():
    tree = OrganizationHierarchy.model_validate(example())
    node = tree.resolve("user", ["ENGINEERS", "digital", "External-Squad1"])
    assert node.path == ("Engineering", "Digital", "squad1")
    assert node.per_user == 100
    assert node.duration == "30d"
    assert node.team_id == "engineering"
    assert tree.roots[0].member.budget.groupTotal == 5000
    assert tree.resolve("local:alice", []).per_user == 50


def test_explicit_null_disables_cap_and_zero_is_not_unlimited():
    tree = OrganizationHierarchy.model_validate(example())
    assert tree.resolve("u", ["unlimited"]).per_user is None
    assert tree.resolve("u", ["blocked"]).per_user == 0
    assert tree.resolve("unmapped", []) is None


def test_incompatible_group_matches_are_rejected():
    tree = OrganizationHierarchy.model_validate(example())
    with pytest.raises(MembershipConflict, match="one organizational path"):
        tree.resolve("user", ["squad1", "squad2"])


@pytest.mark.parametrize(
    "change",
    [
        lambda v: v["levels"][1]["groups"][0].update(parent="missing"),
        lambda v: v["levels"][0]["groups"][0].update(parent="Digital"),
        lambda v: v["levels"][0]["groups"][0]["members"][1].update(litellmTeamId="engineering"),
        lambda v: v["levels"][0]["groups"][0]["members"][0].pop("litellmTeamId"),
        lambda v: v["levels"][1].update(name="Division"),
        lambda v: v["levels"][2]["groups"][0]["members"][0]["budget"].update(groupTotal=100),
        lambda v: v["levels"][2]["groups"][0]["members"][0].update(litellmTeamId="extra-team"),
        lambda v: v["levels"][2]["groups"][0]["members"][1].update(name="squad1"),
        lambda v: v["levels"][2]["groups"][0]["members"][1].update(ssoGroups=["squad1"]),
        lambda v: v["levels"][0]["groups"][0]["members"][0]["budget"].update(perUser=-1),
        lambda v: v["levels"][0]["groups"][0]["members"][0]["budget"].update(duration="monthly"),
        lambda v: v["levels"][0]["groups"][0]["members"][0].update(ssoGroups=[""]),
    ],
)
def test_invalid_configuration_fails_before_serving_requests(change):
    value = deepcopy(example())
    change(value)
    with pytest.raises(ValidationError):
        OrganizationHierarchy.model_validate(value)


def test_any_level_label_can_be_used():
    value = example()
    for index, label in enumerate(["Department", "Branch", "Team"]):
        value["levels"][index]["name"] = label
    assert OrganizationHierarchy.model_validate(value).resolve("u", ["squad1"]).per_user == 100


def test_environment_json_loads_hierarchy(monkeypatch):
    import json

    monkeypatch.setenv("ORGANIZATION_HIERARCHY", json.dumps(example()))
    assert Settings().organization_hierarchy.resolve("u", ["squad1"]).per_user == 100
