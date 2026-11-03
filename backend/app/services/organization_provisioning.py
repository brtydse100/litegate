"""Sequential, recoverable provisioning with explicit identity confirmation."""

import asyncio
import logging
from collections.abc import Callable
from weakref import WeakValueDictionary

from fastapi import HTTPException

from app.config import settings
from app.services import audit, litellm
from app.services import litellm_identity as remote
from app.services import sso_identity as store
from app.services.organization_mapping import OrganizationMapping, get_mapping

_logger = logging.getLogger(__name__)
_locks: WeakValueDictionary[str, asyncio.Lock] = WeakValueDictionary()


def _identity_lock() -> asyncio.Lock:
    lock = _locks.get("identity")
    if lock is None:
        lock = asyncio.Lock()
        _locks["identity"] = lock
    return lock


def _conflict(message: str) -> None:
    raise HTTPException(409, message)


def _audit(action: str, target: str, outcome: str = "success", **details) -> None:
    audit.record(actor_id="organization-mapping", actor_email="", action=action, target=target, outcome=outcome, details=details)


def _verify_owned(user: dict, reservation: dict) -> None:
    metadata = user.get("metadata") or {}
    if (
        user.get("user_id") != reservation["user_id"]
        or str(user.get("user_email") or "").strip().casefold() != reservation["email"]
        or user.get("user_role") != "internal_user"
        or not isinstance(metadata, dict)
        or metadata.get(remote.OWNER_FIELD) != reservation["ownership_token"]
    ):
        _conflict("The reserved LiteLLM account does not match durable LiteGate ownership evidence")


def _ordinary_candidate(user: dict, email: str) -> None:
    if user.get("user_role") != "internal_user" or store.local_conflict(email, user.get("user_id", "")):
        _conflict("Configured email conflicts with a local or administrative account; confirm the SSO subject explicitly")
    if str(user.get("user_id", "")).startswith("litegate-org:"):
        _conflict("Configured email belongs to a reservation without matching ownership evidence")


async def _bound_user(binding: dict) -> str:
    user = await remote.get_user(binding["user_id"])
    if user is None:
        _conflict("The canonical SSO account is missing; restore it before retrying")
    reservation = store.reservation(binding["provider"], binding["email"])
    if reservation and reservation["user_id"] == binding["user_id"]:
        _verify_owned(user, reservation)
    return binding["user_id"]


async def _ensure_owned(reservation: dict) -> str:
    if reservation["status"] == "superseded":
        _conflict("Superseded reservation has no canonical identity binding")
    user = await remote.get_user(reservation["user_id"])
    if user is None:
        # Intent/token were committed before this write. A duplicate or uncertain
        # response fails this pass; the next pass recovers only by exact ID/token.
        await remote.create_reserved_user(reservation["user_id"], reservation["email"], reservation["ownership_token"])
        user = await remote.get_user(reservation["user_id"])
        if user is None:
            raise HTTPException(502, "LiteLLM did not persist the reserved user")
    _verify_owned(user, reservation)
    store.mark_reservation(reservation["provider"], reservation["email"], "reserved")
    return reservation["user_id"]


async def _provision_email(provider: str, email: str) -> str | None:
    binding = store.binding_for_email(provider, email)
    if binding:
        return await _bound_user(binding)
    if store.local_conflict(email):
        _conflict("Configured email belongs to a local account")
    reservation = store.reservation(provider, email)
    candidates = await remote.find_users_by_email(email)
    ordinary = [user for user in candidates if not reservation or user["user_id"] != reservation["user_id"]]
    reserved_match = reservation and any(user["user_id"] == reservation["user_id"] for user in candidates)
    if len(ordinary) > 1 or (ordinary and (reserved_match or (reservation and reservation["status"] == "reserved"))):
        _conflict("Configured email has ambiguous LiteLLM accounts; authenticate the legacy SSO identity first")
    if ordinary:
        _ordinary_candidate(ordinary[0], email)
        reservation = store.reserve(provider, email)
        store.mark_reservation(provider, email, "pending", ordinary[0]["user_id"])
        _audit("organization.identity_pending", email)
        return None
    reservation = reservation or store.reserve(provider, email)
    return await _ensure_owned(reservation)


async def provision_members(mapping: OrganizationMapping) -> None:
    if not mapping.member_emails() and not mapping.referenced_team_ids():
        return
    if mapping.member_emails() and not settings.sso_enabled:
        _conflict("Email organization mapping requires a configured SSO provider before provisioning")
    if any(settings.organization_hierarchy.is_managed_team(team_id) for team_id in mapping.referenced_team_ids()):
        _conflict("Email organization mapping must not reference teams governed by organization_hierarchy")
    store.initialize_identity_store()
    provider = store.provider_authority()
    pending = provisioned = 0
    try:
        # Read every referenced team before any user or membership writes.
        for team_id in mapping.referenced_team_ids():
            if await litellm.get_team(team_id) is None:
                raise HTTPException(409, f"Organization mapping references missing LiteLLM team: {team_id}")
        async with _identity_lock():
            for email in mapping.member_emails():
                user_id = await _provision_email(provider, email)
                if user_id is None:
                    pending += 1
                    continue
                await litellm.sync_user_team_memberships(user_id, email, mapping.team_ids(email, []))
                _audit("organization.provisioned", user_id)
                provisioned += 1
    except Exception:
        _audit("organization.provisioning_failed", "startup", "failure")
        raise
    _logger.info("Organization provisioning completed: %s provisioned, %s pending identity confirmation", provisioned, pending)


async def resolve_sso_user_id(provider: str, subject: str, email: str, *, validate_user_id: Callable[[str], None] | None = None) -> str:
    binding = store.lookup_binding(provider, subject)
    if binding:
        return await _bound_user(binding)
    email = email.strip().casefold()
    if email and store.binding_for_email(provider, email):
        _conflict("Configured email is already bound to a different SSO subject")
    if not email or email not in get_mapping().member_emails():
        return subject
    async with _identity_lock():
        try:
            binding = store.lookup_binding(provider, subject)
            if binding:
                return await _bound_user(binding)
            claimed = store.binding_for_email(provider, email)
            if claimed:
                _conflict("Configured email is already bound to a different SSO subject")
            if store.local_conflict(email, subject) or subject.startswith("litegate-org:"):
                _conflict("SSO identity conflicts with a local account or reserved namespace")
            existing = await remote.get_user(subject)
            reservation = store.reservation(provider, email)
            candidates = await remote.find_users_by_email(email)
            unrelated = [u for u in candidates if u["user_id"] != subject and (not reservation or u["user_id"] != reservation["user_id"])]
            if existing:
                if unrelated:
                    _conflict("Configured email also belongs to an unrelated LiteLLM account")
                canonical = subject
            else:
                if unrelated:
                    _conflict("Existing email candidate requires its authenticated legacy SSO subject")
                canonical = await _ensure_owned(reservation or store.reserve(provider, email))
            if validate_user_id is not None:
                validate_user_id(canonical)
            store.bind(provider, subject, email, canonical)
            _audit("organization.identity_bound", canonical)
            return canonical
        except store.IdentityConflict as exc:
            _audit("organization.identity_failed", subject, "failure")
            raise HTTPException(409, str(exc)) from exc
        except Exception:
            _audit("organization.identity_failed", subject, "failure")
            raise
