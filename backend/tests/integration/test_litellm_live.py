"""Compatibility checks against a real LiteLLM proxy and PostgreSQL database."""

import os
from uuid import uuid4

import pytest

from app.services import litellm
from app.organization import OrganizationHierarchy
from app.services import organization_client as organization
from app.config import settings
from app.services import organization_sync, organization_store


pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_LITELLM_INTEGRATION") != "1",
    reason="requires the opt-in LiteLLM integration stack",
)


@pytest.mark.asyncio
async def test_user_team_and_key_contracts_against_litellm():
    suffix = uuid4().hex[:12]
    user_id = f"litegate-integration-{suffix}"
    email = f"{user_id}@example.invalid"
    team_id = f"team-{suffix}"
    key = ""
    team_created = False

    try:
        created_user = await litellm.create_user(user_id, email)
        assert created_user.get("user_id") == user_id
        user = await litellm.get_user(user_id)
        assert user is not None
        assert user.get("user_id") == user_id

        created_team = await litellm.create_team(
            {
                "team_id": team_id,
                "team_alias": f"LiteGate integration {suffix}",
                "models": [],
                "max_budget": 10,
            }
        )
        team_created = True
        assert created_team.get("team_id") == team_id
        assert (await litellm.get_team(team_id) or {}).get("team_id") == team_id

        await litellm.add_team_member(team_id, user_id)
        assert team_id in await litellm.list_user_team_ids(user_id)

        generated = await litellm.generate_key(
            user_id,
            email,
            team_id,
            key_alias=f"integration-{suffix}",
        )
        key = generated["key"]
        info = await litellm.get_key_info(key)
        assert info is not None
        assert info.get("user_id") == user_id
        assert info.get("team_id") == team_id

        reset = await litellm.reset_key_spend(key)
        assert reset.get("spend") == 0
        assert reset.get("previous_spend") == 0

        await litellm.update_key(key, {"key_alias": f"updated-{suffix}", "blocked": True})
        updated = await litellm.get_key_info(key)
        assert updated is not None
        assert updated.get("key_alias") == f"updated-{suffix}"
        assert updated.get("blocked") is True

        listed = await litellm.list_keys(page=1, size=100, user_id=user_id)
        assert any(item.get("user_id") == user_id for item in listed["keys"])

        updated_team = await litellm.update_team(team_id, {"team_alias": f"Updated {suffix}"})
        assert updated_team.get("team_alias") == f"Updated {suffix}"
    finally:
        if key:
            await litellm.delete_key(key)
        if team_created and await litellm.get_team(team_id):
            await litellm.delete_team(team_id)


@pytest.mark.asyncio
@pytest.mark.skipif(os.environ.get("RUN_LITELLM_ORGANIZATION_INTEGRATION") != "1", reason="requires current LiteLLM member-budget contracts")
async def test_managed_allowance_updates_preserve_windows_and_rotation_carries_spend(monkeypatch, tmp_path):
    suffix = uuid4().hex[:12]
    user_id, team_id = f"organization-{suffix}", f"organization-team-{suffix}"
    tree = OrganizationHierarchy.model_validate(
        {
            "levels": [
                {
                    "name": "Group",
                    "groups": [
                        {
                            "members": [
                                {"name": "Engineering", "litellmTeamId": team_id, "budget": {"perUser": 50, "groupTotal": 5000, "duration": "30d"}}
                            ]
                        }
                    ],
                },
                {
                    "name": "Squad",
                    "groups": [
                        {"parent": "Engineering", "members": [{"name": "Platform", "litellmTeamId": f"{team_id}-platform", "userIds": [user_id]}]}
                    ],
                },
            ]
        }
    )
    root = tree.roots[0]
    monkeypatch.setattr(settings, "organization_hierarchy", tree)
    monkeypatch.setattr(settings, "local_users_db_path", str(tmp_path / "integration-organization.db"))
    leaf = tree.resolve(user_id, [])
    keys = []
    try:
        await litellm.create_user(user_id, f"{user_id}@example.invalid")
        await organization_sync.remember(user_id, "", "explicit", [])
        generated = await organization_sync.generate_key(user_id, "", team_id)
        keys.append(generated["key"])
        first = await litellm.get_key_info(keys[0])
        assert first["team_id"] == leaf.team_id
        assert first["max_budget"] == 50
        assert first["budget_duration"] == "30d"
        assert first["budget_reset_at"]
        assert (await organization.team_info(team_id))["team_info"]["max_budget"] is None
        await litellm.update_key(keys[0], {"spend": 12})
        root.member.budget.perUser = 100
        tree = OrganizationHierarchy.model_validate(tree.model_dump(exclude_unset=True))
        monkeypatch.setattr(settings, "organization_hierarchy", tree)
        await organization_sync.synchronize_user(user_id)
        changed = await litellm.get_key_info(keys[0])
        assert changed["max_budget"] == 100
        assert changed["spend"] == 12
        assert changed["budget_reset_at"] == first["budget_reset_at"]
        replacement = await organization_sync.generate_key(user_id, "", team_id, initial_spend=12, key_alias=f"rotated-{suffix}")
        keys.append(replacement["key"])
        rotated = await litellm.get_key_info(replacement["key"])
        assert rotated["team_id"] == leaf.team_id
        assert rotated["max_budget"] == 100
        assert rotated["spend"] == 12
        await litellm.delete_key(keys.pop(0))
        await litellm.update_team(leaf.team_id, {"team_member_budget": 50, "team_member_rpm_limit": 120})
        await organization_sync.synchronize_user(user_id)
        default = (await organization.team_info(leaf.team_id))["team_info"]["team_member_budget_table"]
        assert default["max_budget"] is None
        assert default["rpm_limit"] == 120
        tree.roots[0].member.budget.perUser = None
        monkeypatch.setattr(settings, "organization_hierarchy", OrganizationHierarchy.model_validate(tree.model_dump(exclude_unset=True)))
        await organization_sync.synchronize_user(user_id)
        assert (await litellm.get_key_info(keys[0]))["max_budget"] is None
        info = await organization.team_info(leaf.team_id)
        assert organization.member_budget(info, user_id)["per_user"] is None
        assert organization_store.get(user_id)["team_id"] == leaf.team_id
    finally:
        for key in keys:
            await litellm.delete_key(key)
        for node in reversed(list(tree.nodes.values())):
            if await litellm.get_team(node.team_id):
                await litellm.delete_team(node.team_id)
