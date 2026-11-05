"""Discover operator assignments; remote email is never an SSO identity claim."""

import asyncio
import logging

from fastapi import HTTPException

from app.config import settings
from app.services import litellm, local_users, organization_client as upstream, organization_store as store

_logger = logging.getLogger(__name__)


def email_of(user: dict) -> str:
    value = user.get("user_email")
    return value.strip().casefold() if isinstance(value, str) else ""


def user_info(value, user_id: str) -> dict | None:
    if value is None:
        return None
    user = value.get("user_info", value) if isinstance(value, dict) else None
    if not isinstance(user, dict) or user.get("user_id") != user_id:
        raise HTTPException(502, "Organization discovery could not verify the requested user ID")
    return user


async def existing_user(user_id: str) -> dict | None:
    try:
        return user_info(await litellm.get_user(user_id), user_id)
    except ValueError as exc:
        raise HTTPException(502, "Organization discovery returned invalid user JSON; assignment skipped") from exc


async def email_match(email: str) -> dict | None:
    """Read the complete substring search with stable ordering, then match exactly."""
    rows, seen = [], set()
    expected = None
    try:
        async with asyncio.timeout(60):
            for page in range(1, 101):
                data = await upstream.request(
                    "GET",
                    "/user/list",
                    params={
                        "user_email": email,
                        "page": page,
                        "page_size": 100,
                        "sort_by": "user_id",
                        "sort_order": "asc",
                    },
                )
                if not isinstance(data, dict):
                    raise HTTPException(502, "Organization email discovery returned an invalid response")
                batch = data.get("users")
                total, pages = data.get("total"), data.get("total_pages")
                if (
                    type(total) is not int
                    or total < 0
                    or type(pages) is not int
                    or pages != (total + 99) // 100
                    or pages > 100
                    or data.get("page") != page
                    or data.get("page_size") != 100
                    or not isinstance(batch, list)
                    or len(batch) != min(100, max(0, total - (page - 1) * 100))
                    or (expected is not None and expected != (total, pages))
                ):
                    raise HTTPException(502, "Organization email discovery returned an incomplete scan (limit: 100 pages)")
                expected = total, pages
                for user in batch:
                    identifier = user.get("user_id") if isinstance(user, dict) else None
                    if not isinstance(identifier, str) or not identifier or identifier in seen:
                        raise HTTPException(502, "Organization email discovery returned invalid or duplicate users")
                    seen.add(identifier)
                    if email_of(user) == email:
                        rows.append(user)
                if page >= pages:
                    break
            else:
                raise HTTPException(502, "Organization email discovery exceeded 100 pages")
    except TimeoutError as exc:
        raise HTTPException(502, "Organization email discovery timed out; assignment skipped") from exc
    if len(rows) > 1:
        raise HTTPException(409, "Organization email matches multiple LiteLLM users; configure an exact user ID")
    return rows[0] if rows else None


async def refresh(identities: list[dict], lock_for, resolve) -> set[str]:
    """Revalidate remote-derived assignments BEFORE any known-user synchronization."""
    selectors = {value for node in settings.organization_hierarchy.nodes.values() for value in node.member.userIds}
    known = {item["user_id"]: item for item in identities}
    blocked = {item["user_id"] for item in identities if item["auth_source"] == "configured_email"}
    semaphore = asyncio.Semaphore(5)
    local = await asyncio.to_thread(local_users.list_users)
    exact = set()
    # Fail closed while remote validation is in flight, including an interrupted pass.
    for user_id in list(blocked):
        async with lock_for("user", user_id):
            current = await asyncio.to_thread(store.get, user_id)
            if current and current["auth_source"] == "configured_email":
                await asyncio.to_thread(store.failed, user_id, "Configured email assignment is awaiting remote revalidation")
            else:
                blocked.discard(user_id)

    async def discover_id(selector):
        async with semaphore:
            if selector in known and known[selector]["auth_source"] != "configured_email":
                exact.add(selector)
                return
            try:
                user = await existing_user(selector)
                if user is not None:
                    async with lock_for("user", selector):
                        previous = await asyncio.to_thread(store.get, selector)
                        if previous is None:
                            await asyncio.to_thread(store.remember, selector, email_of(user), "explicit", [])
                        elif previous["auth_source"] == "configured_email":
                            await asyncio.to_thread(store.remember, selector, email_of(user), "explicit", [])
                            await asyncio.to_thread(store.validated, selector)
                        blocked.discard(selector)
                        exact.add(selector)
            except HTTPException as exc:
                # A failed exact-ID lookup must not fall back to an email scan.
                exact.add(selector)
                _logger.warning("Organization selector %s discovery failed: %s", selector, exc.detail)

    await asyncio.gather(*(discover_id(value) for value in sorted(selectors)))

    async def discover_email(email):
        async with semaphore:
            try:
                candidate = await email_match(email)
                if candidate is None:
                    raise HTTPException(409, "Configured organization email has no existing LiteLLM user; retrying later")
                user_id = candidate["user_id"]
                async with lock_for("user", user_id):
                    user = await existing_user(user_id)
                    if user is None or email_of(user) != email:
                        raise HTTPException(409, "Organization email changed during discovery; assignment skipped")
                    previous = await asyncio.to_thread(store.get, user_id)
                    if previous and previous["auth_source"] != "configured_email":
                        return  # Verified accepted/rejected claims and local identities remain authoritative.
                    if (
                        user_id.startswith("local:")
                        or "admin" in str(user.get("user_role", "")).casefold()
                        or any(item["user_id"] == user_id or item["email"].strip().casefold() == email for item in local)
                    ):
                        raise HTTPException(409, "Email-only organization assignment targets a local/admin account; configure an exact user ID")
                    resolve(user_id, [], email=email, source="configured_email")
                    await asyncio.to_thread(store.remember, user_id, email, "configured_email", [])
                    await asyncio.to_thread(store.validated, user_id)
                    blocked.discard(user_id)
            except HTTPException as exc:
                _logger.warning("Organization email %s discovery failed: %s", email, exc.detail)
                for identity in identities:
                    if identity["auth_source"] == "configured_email" and identity["email"] == email:
                        async with lock_for("user", identity["user_id"]):
                            current = await asyncio.to_thread(store.get, identity["user_id"])
                            if current and current["auth_source"] == "configured_email":
                                await asyncio.to_thread(store.failed, identity["user_id"], str(exc.detail))

    emails = {value.strip().casefold() for value in selectors - exact if "@" in value}
    await asyncio.gather(*(discover_email(email) for email in sorted(emails)))
    for user_id in blocked:
        identity = await asyncio.to_thread(store.get, user_id)
        if not identity.get("sync_error"):
            await asyncio.to_thread(store.failed, user_id, "Configured email assignment could not be revalidated; review selectors and remote email")
    return blocked
