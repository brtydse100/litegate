"""Preserve key controls before revoking credentials during personal rotation."""

import asyncio
from datetime import datetime, timezone

from fastapi import HTTPException

from app.services import litellm, organization_store, organization_sync

# Budget/team policy is owned by organizationHierarchy for managed users.
CONTROLS = (
    "blocked",
    "models",
    "rpm_limit",
    "tpm_limit",
    "max_parallel_requests",
    "expires",
    "allowed_routes",
    "allowed_cache_controls",
    "aliases",
    "config",
    "permissions",
    "guardrails",
    "model_rpm_limit",
    "model_tpm_limit",
    "enforced_params",
    "metadata",
    "object_permission_id",
    "object_permission",
    "mcp_rpm_limit",
    "tag_rpm_limit",
    "policies",
    "prompts",
    "budget_fallbacks",
)


def requires_assistance(keys: list[dict]) -> bool:
    return any(key.get("model_max_budget") or key.get("budget_limits") for key in keys)


async def snapshot(user_id: str, existing: list[dict]) -> dict:
    identity = await asyncio.to_thread(organization_store.get, user_id)
    node = organization_sync.resolve_identity(identity) if identity else organization_sync.resolve(user_id, [])
    fields = CONTROLS if node else (*CONTROLS, "team_id", "max_budget", "budget_duration")
    policies = [{field: key[field] for field in fields if field in key} for key in existing]
    if policies and any(policy != policies[0] for policy in policies[1:]):
        raise HTTPException(status_code=409, detail="Keys with different policies require administrator-assisted rotation; original keys were kept")
    return policies[0] if policies else {}


def same(field: str, actual, expected) -> bool:
    if field == "expires" and actual and expected:
        try:
            # LiteLLM accepts a relative duration with whole-second precision.
            return 0 <= (timestamp(expected) - timestamp(actual)).total_seconds() < 2
        except (TypeError, ValueError):
            return False
    return actual == expected


def timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed


async def preserve(user_id: str, policy: dict, replacement: str) -> dict | None:
    if not policy:
        return
    info = await litellm.get_key_info(replacement)
    if not info or info.get("user_id") != user_id:
        raise HTTPException(status_code=502, detail="Could not verify the replacement key's ownership")
    changes = {field: value for field, value in policy.items() if not same(field, info.get(field), value)}
    if "expires" in changes:
        expires = changes.pop("expires")
        if expires is None:
            changes["duration"] = None
        else:
            try:
                seconds = int((timestamp(expires) - datetime.now(timezone.utc)).total_seconds()) - 1
            except (TypeError, ValueError):
                raise HTTPException(status_code=502, detail="Could not verify the source key's expiration") from None
            if seconds <= 0:
                raise HTTPException(status_code=409, detail="This key has expired or is about to expire; ask an administrator to replace it")
            changes["duration"] = f"{seconds}s"
    if changes:
        await litellm.update_key(replacement, changes)
        info = await litellm.get_key_info(replacement)
    if not info or info.get("user_id") != user_id or any(not same(field, info.get(field), value) for field, value in policy.items()):
        raise HTTPException(status_code=502, detail="LiteLLM did not preserve replacement key restrictions; original keys were kept")
    return info
