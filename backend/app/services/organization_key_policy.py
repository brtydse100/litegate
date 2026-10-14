"""Verified lowest-team key allowances; ancestor budgets are reporting targets."""

import asyncio

from fastapi import HTTPException

from app.config import settings
from app.organization import OrganizationNode, MembershipConflict
from app.services import litellm, organization_client as upstream, organization_store as store


def key_policy(node: OrganizationNode) -> dict:
    return {"team_id": node.team_id, "max_budget": node.per_user, "budget_duration": node.duration}


def matches(key: dict, node: OrganizationNode) -> bool:
    return all(field in key and key[field] == value for field, value in key_policy(node).items())


async def guard_ancestor_restrictions(node: OrganizationNode, user_id: str, keys: list[dict]) -> None:
    """Require an operator review rather than silently dropping native controls."""
    source_teams = {key.get("team_id") for key in keys if key.get("team_id") != node.team_id}
    limits = ("rpm_limit", "tpm_limit", "max_parallel_requests")
    policies = (
        "models",
        "allowed_models",
        "model_rpm_limit",
        "model_tpm_limit",
        "model_aliases",
        "guardrails",
        "permissions",
        "object_permission",
        "object_permission_id",
    )
    for ancestor in settings.organization_hierarchy.nodes.values():
        if ancestor.team_id == node.team_id or node.path[: len(ancestor.path)] != ancestor.path:
            continue
        info = await upstream.team_info(ancestor.team_id)
        team = info.get("team_info")
        if not isinstance(team, dict):
            raise HTTPException(status_code=502, detail="Could not verify ancestor team restrictions")
        member = upstream.membership(info, user_id) if ancestor.team_id in source_teams else None
        if ancestor.team_id in source_teams:
            if member is not None:
                upstream.member_budget(info, user_id)  # Reject unhydrated linked policy records.
            else:
                roster = team.get("members_with_roles")
                if not isinstance(roster, list) or any(item.get("user_id") == user_id for item in roster):
                    raise HTTPException(status_code=502, detail="Could not verify the source team member's restrictions")
        records = [team, member or {}, (member or {}).get("litellm_budget_table") or {}]
        if any(
            record.get("blocked") or any(record.get(field) is not None for field in limits) or any(record.get(field) for field in policies)
            for record in records
        ):
            raise HTTPException(
                status_code=409,
                detail="Review ancestor team restrictions in LiteLLM before using a lowest-level team; model, blocking and rate policies are not inherited",
            )


async def apply_key(node: OrganizationNode, key: dict) -> None:
    identifier = key.get("token") or key.get("api_key") or key.get("key")
    if not identifier:
        raise HTTPException(status_code=502, detail="Cannot synchronize a managed key without its identifier")
    changes = {field: value for field, value in key_policy(node).items() if field not in key or key[field] != value}
    if changes:
        await litellm.update_key(identifier, changes)
        verified = await litellm.get_key_info(identifier)
        if not verified or not matches(verified, node):
            raise HTTPException(status_code=502, detail="Could not verify the managed key's budget policy")


async def finish_team(node: OrganizationNode) -> dict:
    """Clear old native shared caps only after every affected key is protected."""
    info = await upstream.team_info(node.team_id)
    team = info.get("team_info")
    if not isinstance(team, dict) or "max_budget" not in team:
        raise HTTPException(status_code=502, detail="Could not verify the managed team's policy")
    changes = {field: value for field, value in {"max_budget": None, "budget_duration": node.duration}.items() if team.get(field) != value}
    if upstream.default_member_budget(info) is not None:
        changes["team_member_budget"] = None
    if not changes:
        return info
    if team["max_budget"] is not None or "team_member_budget" in changes:
        for page in range(1, 51):
            result = await litellm.list_keys_filtered(page=page, size=100, team_id=node.team_id)
            for key in result["keys"]:
                owner = key.get("user_id") or ""
                identity = await asyncio.to_thread(store.get, owner)
                try:
                    assigned = settings.organization_hierarchy.resolve(owner, identity["groups"] if identity else [])
                except MembershipConflict as exc:
                    raise HTTPException(status_code=409, detail="Resolve conflicting team memberships before removing a shared cap") from exc
                if not assigned or assigned.team_id != node.team_id or not matches(key, assigned):
                    raise HTTPException(status_code=409, detail="Protect or migrate every key in this team before removing its old shared budget")
            if result.get("total_pages", 1) <= page:
                break
        else:
            raise HTTPException(status_code=422, detail="Team policy migration supports at most 5000 keys")
    await litellm.update_team(node.team_id, changes)
    verified = await upstream.team_info(node.team_id)
    actual = verified.get("team_info")
    if (
        not isinstance(actual, dict)
        or actual.get("max_budget") is not None
        or actual.get("budget_duration") != node.duration
        or upstream.default_member_budget(verified) is not None
    ):
        raise HTTPException(status_code=502, detail="LiteLLM did not remove the managed team's old shared budget")
    return verified


async def normalize_individual_caps(node: OrganizationNode, user_id: str) -> None:
    """Do not remove a user's ceiling while another credential is unprotected."""
    keys = await litellm.list_user_keys(user_id)
    if not keys or any(not matches(key, node) for key in keys):
        raise HTTPException(status_code=409, detail="Verify all of this user's key allowances before removing individual user budgets")
    info = await finish_team(node)
    await upstream.sync_member(node, user_id, info)
    user = await litellm.get_user(user_id)
    record = user.get("user_info", user) if isinstance(user, dict) else None
    if not isinstance(record, dict) or "max_budget" not in record:
        raise HTTPException(status_code=502, detail="Could not verify the personal user budget")
    if record["max_budget"] is not None:
        await upstream.request("POST", "/user/update", payload={"user_id": user_id, "max_budget": None})
        user = await litellm.get_user(user_id)
        record = user.get("user_info", user) if isinstance(user, dict) else None
        if not isinstance(record, dict) or "max_budget" not in record or record["max_budget"] is not None:
            raise HTTPException(status_code=502, detail="LiteLLM did not remove the separate personal user budget")
