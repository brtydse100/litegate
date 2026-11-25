"""People get LiteLLM's view-only role, so every key goes through LiteGate.

LiteLLM's default ``internal_user`` role lets a person's own key, or a LiteLLM
UI session, create new personal keys without any of LiteGate's budgets.
``internal_user_viewer`` can still use its keys for model requests and view
its usage, but cannot create, update or delete keys; LiteGate keeps managing
keys with the master key. Only the plain ``internal_user`` role is changed:
administrators and other roles are left exactly as configured.
"""

import asyncio
import logging

from fastapi import HTTPException

from app.services import audit, litellm, local_users, organization_store, sso_identity

VIEWER = "internal_user_viewer"
SELF_SERVICE = "internal_user"
STARTUP_CONCURRENCY = 5

_logger = logging.getLogger(__name__)


def role_of(user: dict | None) -> str | None:
    """The role in a /user/info response (or a bare user record)."""
    if not isinstance(user, dict):
        return None
    details = user.get("user_info") if isinstance(user.get("user_info"), dict) else user
    role = details.get("user_role")
    return role if isinstance(role, str) else None


async def restrict(user_id: str, user: dict | None) -> bool:
    """Switch a self-service user to the viewer role. True when it changed.

    Failures are logged and retried at the next sign-in or startup; they never
    block the sign-in itself.
    """
    # A user record without a role is treated by LiteLLM as internal_user.
    if not isinstance(user, dict) or role_of(user) not in (SELF_SERVICE, None):
        return False
    try:
        await litellm.update_user_role(user_id, VIEWER)
    except HTTPException as exc:
        _logger.warning("Could not switch LiteLLM user %s to the viewer role: %s", user_id, exc.detail)
        return False
    details = user.get("user_info") if isinstance(user.get("user_info"), dict) else user
    details["user_role"] = VIEWER
    await asyncio.to_thread(
        audit.record,
        actor_id="system:litegate",
        actor_email="",
        action="litellm.user_role_restricted",
        target=user_id,
        details={"from": SELF_SERVICE, "to": VIEWER},
    )
    return True


def known_user_ids() -> list[str]:
    """People LiteGate signs in: local accounts, SSO bindings and organization members."""
    ids = {user["user_id"] for user in local_users.list_users()}
    ids.update(sso_identity.bound_user_ids())
    ids.update(identity["user_id"] for identity in organization_store.list_identities())
    return sorted(ids)


async def restrict_known_users() -> int:
    """One startup pass over the people LiteGate knows; returns how many changed."""
    semaphore = asyncio.Semaphore(STARTUP_CONCURRENCY)

    async def one(user_id: str) -> bool:
        async with semaphore:
            try:
                return await restrict(user_id, await litellm.get_user(user_id))
            except HTTPException as exc:
                _logger.warning("Could not read LiteLLM user %s for the viewer role: %s", user_id, exc.detail)
                return False

    try:
        changed = sum(await asyncio.gather(*(one(user_id) for user_id in await asyncio.to_thread(known_user_ids))))
    except Exception:
        # Sign-ins still switch each person; startup must not fail over this.
        _logger.exception("Startup pass for LiteLLM viewer roles failed")
        return 0
    if changed:
        _logger.info("Switched %d LiteLLM users to the viewer role", changed)
    return changed
