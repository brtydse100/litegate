"""Enforced hierarchical allowances: equal groupTotal shares for signed-in members.

A group is *budgeted* when it has a configured ``groupTotal`` or an envelope set
on the Budget planning page. Its envelope, minus budgeted child envelopes and
manual overrides, is shared equally by its participating direct members.
``perUser`` remains a ceiling. Members of unbudgeted groups keep ``perUser``.

Participants are users who signed in or already hold a key, so nothing is
reserved for people who never use LiteGate. A new participant changes every
share in the group; the 60-second reconciliation applies the new caps.
"""

import asyncio
import math
from dataclasses import replace
from datetime import datetime, timezone
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal

from app.config import settings
from app.organization import MembershipConflict, OrganizationNode
from fastapi import HTTPException

from app.services import budget_allocations as allocation, budget_store, database, litellm, organization_store

# Latest verified current-period spend per user, in micro-dollars. Shares never
# fall below consumed spend, so a join cannot hand out money already spent.
_spent: dict[str, int] = {}
_snapshot: dict | None = None
_primed = False


def create_table(db) -> None:
    db.execute("CREATE TABLE IF NOT EXISTS organization_participants (user_id TEXT PRIMARY KEY, since TEXT NOT NULL)")


def enforced() -> bool:
    return settings.hierarchical_budgets_enforced and bool(settings.organization_hierarchy.levels)


def invalidate() -> None:
    global _snapshot
    _snapshot = None


def mark_participant(user_id: str) -> None:
    with database.connect() as db:
        inserted = db.execute(
            "INSERT OR IGNORE INTO organization_participants VALUES (?, ?)", (user_id, datetime.now(timezone.utc).isoformat())
        ).rowcount
    if inserted:
        invalidate()


def participants() -> set[str]:
    with database.connect(read_only=True) as db:
        return {row[0] for row in db.execute("SELECT user_id FROM organization_participants")}


def _units(value, rounding) -> int:
    return int((Decimal(str(value)) * allocation.SCALE).to_integral_value(rounding=rounding))


def observe_spend(user_id: str, spend: float) -> None:
    # Callers invalidate once per pass; per-user invalidation would recompute
    # the whole allocation for every member.
    _spent[user_id] = _units(spend, ROUND_CEILING) if math.isfinite(spend) and spend > 0 else 0


async def observe(user_id: str, keys: list[dict]) -> None:
    """Record a member's current-period key spend; key holders participate."""
    observe_spend(user_id, litellm.total_key_spend(keys))
    if keys:
        await asyncio.to_thread(mark_participant, user_id)


async def observe_all(user_ids: list[str], semaphore: asyncio.Semaphore) -> None:
    """Give each reconciliation pass one consistent allocation snapshot.

    Only the first pass after startup lists every member's keys, so existing
    key holders count before any share is applied. Later passes reuse the spend
    and key holders recorded by the previous pass's own key listing, adding no
    LiteLLM requests; spend floors are therefore at most one pass old.
    """
    global _primed
    if not enforced():
        return
    if _primed:
        invalidate()
        return

    async def one(user_id: str):
        async with semaphore:
            try:
                await observe(user_id, await litellm.list_user_keys(user_id))
            except HTTPException:
                pass  # Keep the previous spend floor; the member retries next pass.

    await asyncio.gather(*(one(user_id) for user_id in user_ids))
    _primed = True
    invalidate()


def spent() -> dict[str, int]:
    return dict(_spent) if enforced() else {}


def members() -> tuple[dict, dict]:
    """Map participating, validly synchronized users to their direct group."""
    tree = settings.organization_hierarchy
    active = participants()
    memberships, emails = {}, {}
    for identity in organization_store.list_identities():
        if identity["user_id"] not in active or identity.get("sync_error"):
            continue
        try:
            node = tree.resolve(identity["user_id"], identity["groups"], email=identity["email"], source=identity["auth_source"])
        except MembershipConflict:
            continue
        if node:
            memberships[identity["user_id"]], emails[identity["user_id"]] = node.id, identity["email"]
    return memberships, emails


def budgeted(node: OrganizationNode, state: dict, memberships: dict) -> bool:
    """A configured total, a planning-page envelope, or a member override."""
    return (
        node.member.budget.groupTotal is not None
        or node.id in state["envelopes"]
        or any(group == node.id and state["overrides"].get(user) is not None for user, group in memberships.items())
    )


def allocations(state: dict, memberships: dict, *, strict: bool = True) -> dict:
    tree = settings.organization_hierarchy
    envelopes = {node.id: allocation.units(node.member.budget.groupTotal or 0) for node in tree.nodes.values()}
    envelopes.update({key: value for key, value in state["envelopes"].items() if key in tree.nodes})
    return allocation.allocate(tree, envelopes, state["overrides"], memberships, spent=spent(), strict=strict)


def _compute() -> dict:
    state = budget_store.read()
    memberships, _ = members()
    rows = allocations(state, memberships, strict=False)
    return {"state": state, "memberships": memberships, "rows": rows}


def allowance(node: OrganizationNode, user_id: str) -> OrganizationNode:
    """Return ``node`` with ``per_user`` replaced by the user's enforced share."""
    global _snapshot
    if not enforced():
        return node
    if _snapshot is None:
        _snapshot = _compute()
    if not budgeted(node, _snapshot["state"], _snapshot["memberships"]):
        return node
    if _snapshot["memberships"].get(user_id) != node.id:
        # Not yet a participant (no sign-in or key): nothing is reserved.
        value = 0
    else:
        share = _snapshot["rows"][node.id]["users"].get(user_id)
        # A deficit leaves automatic shares unknown; allow no new spend.
        value = share if share is not None else _spent.get(user_id, 0)
    if node.per_user is not None:
        value = min(value, _units(node.per_user, ROUND_FLOOR))
    return replace(node, per_user=allocation.dollars(value))
