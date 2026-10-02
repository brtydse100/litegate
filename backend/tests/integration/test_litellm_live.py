"""Compatibility checks against a real LiteLLM proxy and PostgreSQL database."""

import os
from uuid import uuid4

import pytest

from app.services import litellm
from app.organization import OrganizationHierarchy
from app.services import organization_client as organization


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
async def test_managed_user_allowance_and_rotation_preserve_the_budget_window():
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
                }
            ]
        }
    )
    root = tree.roots[0]
    keys = []
    try:
        await litellm.create_user(user_id, f"{user_id}@example.invalid")
        info = await organization.sync_root(root)
        await organization.sync_member(root, user_id, info)
        first = organization.membership(await organization.team_info(team_id), user_id)
        first_budget = first["litellm_budget_table"]
        assert first_budget["max_budget"] == 50
        assert first_budget["budget_duration"] == "30d"
        assert first_budget["budget_reset_at"]
        generated = await organization.generate_key(user_id, "", team_id)
        keys.append(generated["key"])
        await litellm.delete_key(keys.pop())
        replacement = await organization.generate_key(user_id, "", team_id)
        keys.append(replacement["key"])
        rotated = organization.membership(await organization.team_info(team_id), user_id)
        assert rotated["spend"] == first["spend"]
        assert rotated["litellm_budget_table"]["budget_reset_at"] == first_budget["budget_reset_at"]
        root.member.budget.perUser = 100
        tree = OrganizationHierarchy.model_validate(tree.model_dump(exclude_unset=True))
        updated_root = tree.roots[0]
        await organization.sync_member(updated_root, user_id, await organization.team_info(team_id))
        changed = organization.membership(await organization.team_info(team_id), user_id)
        assert changed["litellm_budget_table"]["max_budget"] == 100
        assert changed["litellm_budget_table"]["budget_reset_at"] == first_budget["budget_reset_at"]
        assert changed["spend"] == first["spend"]
        # Managed roots must remove a fallback that would cap a null allowance.
        await litellm.update_team(team_id, {"team_member_budget": 50, "team_member_rpm_limit": 120})
        verified_root = await organization.sync_root(updated_root)
        default = verified_root["team_info"]["team_member_budget_table"]
        assert default["max_budget"] is None
        assert default["rpm_limit"] == 120
        updated_root.member.budget.perUser = None
        unlimited_tree = OrganizationHierarchy.model_validate(tree.model_dump(exclude_unset=True))
        unlimited = unlimited_tree.roots[0]
        await organization.sync_member(unlimited, user_id, await organization.team_info(team_id))
        info = await organization.team_info(team_id)
        assert organization.member_budget(info, user_id)["per_user"] is None
        assert organization.membership(info, user_id)["spend"] == first["spend"]
        assert organization.membership(info, user_id)["litellm_budget_table"]["budget_reset_at"] == first_budget["budget_reset_at"]
    finally:
        for key in keys:
            await litellm.delete_key(key)
        if await litellm.get_team(team_id):
            await litellm.delete_team(team_id)
