"""The signed-in user's organization key status, as shown on their key page."""

import asyncio

from fastapi import HTTPException

from app.config import settings
from app.models import CurrentUser
from app.services import litellm, organization_key_policy as key_policy, organization_store as store
from app.services.organization_sync import resolve, resolve_identity


async def personal_policy(user: CurrentUser, keys: list[dict] | None = None) -> dict | None:
    if not settings.organization_hierarchy.levels:
        return None
    identity = await asyncio.to_thread(store.get, user.user_id)
    error = identity.get("sync_error") if identity else None
    try:
        node = resolve_identity(identity) if identity else resolve(user.user_id, [])
    except HTTPException as exc:
        node, error = None, str(exc.detail)
    team_id = next((key["team_id"] for key in keys or [] if settings.organization_hierarchy.is_managed_team(key.get("team_id"))), None)
    team_id = team_id or (identity.get("team_id") if identity else None) or (node.team_id if node else None)
    if team_id is None:
        return None
    root = next((root for root in settings.organization_hierarchy.nodes.values() if root.team_id == team_id), None)
    valid = node is not None and node.team_id == team_id
    result = {
        "path": list(node.path) if valid else list(root.path) if root else [],
        "per_user": None,
        "duration": None,
        "spend": None,
        "budget_available": False,
        "sync_error": error,
        "notice": None,
    }
    if identity is None and node is None:
        # Missing context, e.g. a new database after a restart without persistence:
        # group claims only arrive at sign-in. Nothing was removed.
        result["notice"] = "Sign out and sign in again to restore your organization details. Your key keeps working meanwhile."
    elif node is not None and not valid:
        # Moved: the key follows on the next synchronization pass.
        result["path"] = list(node.path)
        result["notice"] = f"You were moved to {' / '.join(node.path)}. Your key moves there within about a minute."
    elif not valid:
        result["sync_error"] = error or "Your organization mapping was removed; contact an administrator"
    if any(key.get("team_id") != team_id for key in keys or []):
        result["sync_error"] = result["sync_error"] or "Your key's team assignment is not synchronized; its user allowance is unavailable"
        return result
    try:
        if not keys or any("max_budget" not in key or "budget_duration" not in key for key in keys):
            raise HTTPException(status_code=502, detail="The key's current allowance is unavailable")
        actual = {"per_user": keys[0]["max_budget"], "duration": keys[0]["budget_duration"], "spend": litellm.total_key_spend(keys)}
        result.update(actual, budget_available=True)
        if valid and any(not key_policy.matches(key, node) for key in keys):
            result["sync_error"] = result["sync_error"] or "Your enforced allowance differs from organizationHierarchy; contact an administrator"
    except HTTPException as exc:
        result["sync_error"] = result["sync_error"] or str(exc.detail)
    return result
