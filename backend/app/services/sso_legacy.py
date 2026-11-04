"""Claim only durable 2.15.0 identity records; never create reservations."""

import asyncio
from collections.abc import Callable
from fastapi import HTTPException
from app.services import audit, litellm_identity as remote, sso_identity as store

_lock = asyncio.Lock()


def _conflict(message: str) -> None:
    raise HTTPException(409, message)


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


async def _bound_user(binding: dict) -> str:
    user = await remote.get_user(binding["user_id"])
    if user is None:
        _conflict("The canonical SSO account is missing; restore it before retrying")
    reservation = store.reservation(binding["provider"], binding["email"])
    if reservation and reservation["user_id"] == binding["user_id"]:
        _verify_owned(user, reservation)
    return binding["user_id"]


async def _resolve_sso_user_id(provider: str, subject: str, email: str, *, validate_user_id: Callable[[str], None] | None = None) -> str:
    async with _lock:
        binding = store.lookup_binding(provider, subject)
        if binding:
            return await _bound_user(binding)
        email = email.strip().casefold()
        if email and store.binding_for_email(provider, email):
            _conflict("Configured email is already bound to a different SSO subject")
        reservation = store.reservation(provider, email) if email else None
        if not reservation:
            return subject
        if store.local_conflict(email, subject) or subject.startswith("litegate-org:"):
            _conflict("SSO identity conflicts with a local account or reserved namespace")
        existing = await remote.get_user(subject)
        if existing:
            canonical = subject
        elif reservation["status"] in {"intent", "reserved"}:
            owned = await remote.get_user(reservation["user_id"])
            if owned is None:
                _conflict("The legacy reservation has no durable remote ownership evidence")
            _verify_owned(owned, reservation)
            canonical = reservation["user_id"]
        else:
            _conflict("Legacy pending email candidate requires its authenticated existing SSO subject")
        if validate_user_id:
            validate_user_id(canonical)
        try:
            store.bind(provider, subject, email, canonical)
        except store.IdentityConflict as exc:
            raise HTTPException(409, str(exc)) from exc
        audit.record(actor_id="organization-mapping", actor_email="", action="organization.identity_bound", target=canonical)
        return canonical


async def resolve_sso_user_id(provider: str, subject: str, email: str, *, validate_user_id: Callable[[str], None] | None = None) -> str:
    try:
        return await _resolve_sso_user_id(provider, subject, email, validate_user_id=validate_user_id)
    except Exception:
        audit.record(actor_id="organization-mapping", actor_email="", action="organization.identity_failed", target=subject, outcome="failure")
        raise
