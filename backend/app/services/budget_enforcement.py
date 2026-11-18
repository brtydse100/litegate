"""Enforced hierarchical allowances: equal groupTotal shares for signed-in members.

A group is *budgeted* when it has a configured ``groupTotal``, an envelope set on
the Budget planning page, or a manual override for one of its members. Its
amount, minus budgeted child envelopes and manual overrides, is shared equally
by its participating direct members. ``perUser`` remains a ceiling. Members of
unbudgeted groups keep ``perUser``.

Participants are users who signed in or already hold a key, so nothing is
reserved for people who never use LiteGate. A new participant changes every
share in the group; the 60-second reconciliation applies the new caps.

Shares come from a snapshot. Each reconciliation pass pins one snapshot for
all of its members, so a sign-in or budget edit during a pass cannot make the
pass disagree with itself. Shares are recomputed every pass from current spend
(so restarts and period resets are reflected), but keys are only rewritten when
a share actually changes.
"""

import asyncio
import contextvars
import itertools
import math
import threading
from dataclasses import replace
from datetime import datetime, timezone
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal

from fastapi import HTTPException

from app.config import settings
from app.organization import MembershipConflict, OrganizationNode
from app.services import budget_allocations as allocation, budget_store, database, litellm, organization_store

# Latest verified current-period spend per user, in micro-dollars. A snapshot
# copies it when built; shares never fall below that consumed spend.
_spent: dict[str, int] = {}
_snapshot: dict | None = None
_primed = False
_tickets = itertools.count(1)
_lock = threading.Lock()
# Users marked by this process, so a key holder recorded after a snapshot was
# built is never mistaken for a non-participant and capped at zero.
_marked: set[str] = set()
_pinned: contextvars.ContextVar[dict | None] = contextvars.ContextVar("budget_snapshot", default=None)


def create_table(db) -> None:
    db.execute("CREATE TABLE IF NOT EXISTS organization_participants (user_id TEXT PRIMARY KEY, since TEXT NOT NULL)")


def enforced() -> bool:
    return settings.hierarchical_budgets_enforced and bool(settings.organization_hierarchy.levels)


def mark_participant(user_id: str) -> None:
    with database.connect() as db:
        db.execute("INSERT OR IGNORE INTO organization_participants VALUES (?, ?)", (user_id, datetime.now(timezone.utc).isoformat()))
    _marked.add(user_id)


def participants() -> set[str]:
    with database.connect(read_only=True) as db:
        return {row[0] for row in db.execute("SELECT user_id FROM organization_participants")}


def _units(value, rounding) -> int:
    return int((Decimal(str(value)) * allocation.SCALE).to_integral_value(rounding=rounding))


def observe_spend(user_id: str, spend: float) -> None:
    _spent[user_id] = _units(spend, ROUND_CEILING) if math.isfinite(spend) and spend > 0 else 0


async def observe(user_id: str, keys: list[dict]) -> None:
    """Record a member's current-period key spend; key holders participate."""
    if not enforced():
        return
    # An absent key is not evidence that its budget period reset.
    if keys:
        observe_spend(user_id, litellm.total_key_spend(keys))
        await asyncio.to_thread(mark_participant, user_id)


async def observe_all(user_ids: list[str], semaphore: asyncio.Semaphore) -> None:
    """Record existing key holders once, before any share is applied.

    Only the first pass after startup lists every member's keys. Later passes
    rely on the spend and key holders the regular sync already reads, adding no
    LiteLLM requests.
    """
    global _primed
    if not enforced() or _primed:
        return

    async def one(user_id: str):
        async with semaphore:
            try:
                await observe(user_id, await litellm.list_user_keys(user_id))
            except HTTPException:
                pass  # Keep the previous spend floor; the member retries next pass.

    await asyncio.gather(*(one(user_id) for user_id in user_ids))
    _primed = True


def spent() -> dict[str, int]:
    return dict(_spent) if enforced() else {}


def members() -> tuple[dict, dict]:
    """Map participating users to their direct group.

    Transient synchronization errors do not remove anyone: dropping a member
    would cap their key at zero and enlarge everyone else's share.
    """
    tree = settings.organization_hierarchy
    active = participants()
    memberships, emails = {}, {}
    for identity in organization_store.list_identities():
        if identity["user_id"] not in active:
            continue
        try:
            node = tree.resolve(identity["user_id"], identity["groups"], email=identity["email"], source=identity["auth_source"])
        except MembershipConflict:
            continue
        if node:
            memberships[identity["user_id"]], emails[identity["user_id"]] = node.id, identity["email"]
    return memberships, emails


def budgeted_nodes(state: dict, memberships: dict) -> set[str]:
    """Groups with a configured total, a planning-page envelope, or a member override."""
    tree = settings.organization_hierarchy
    result = {node.id for node in tree.nodes.values() if node.member.budget.groupTotal is not None}
    result.update(node_id for node_id in state["envelopes"] if node_id in tree.nodes)
    result.update(group for user, group in memberships.items() if state["overrides"].get(user) is not None)
    return result


def allocations(state: dict, memberships: dict, *, strict: bool = True, floors: dict | None = None) -> dict:
    tree = settings.organization_hierarchy
    envelopes = {node.id: allocation.units(node.member.budget.groupTotal or 0) for node in tree.nodes.values()}
    envelopes.update({key: value for key, value in state["envelopes"].items() if key in tree.nodes})
    return allocation.allocate(tree, envelopes, state["overrides"], memberships, spent=spent() if floors is None else floors, strict=strict)


def refresh() -> dict:
    """Return a current snapshot, replacing it when shares or spend floors change.

    Shares are recomputed from current members, budgets and spend every time,
    so a restart, a spend change or a period reset is reflected. The snapshot
    object changes with accounting; keys are only written when their caps differ.
    Safe to call from worker threads: each call takes a ticket, and an older
    build finishing late never replaces a newer one.
    """
    global _snapshot
    ticket = next(_tickets)
    state = budget_store.read()
    memberships, _ = members()
    floors = spent()
    budgeted = budgeted_nodes(state, memberships)
    rows = allocations(state, memberships, strict=False, floors=floors)
    active = participants()
    with _lock:
        current = _snapshot
        if current is not None and current["ticket"] > ticket:
            return current
        if current is not None and (current["rows"], current["budgeted"], current["memberships"], current["participants"], current["floors"]) == (
            rows,
            budgeted,
            memberships,
            active,
            floors,
        ):
            current["ticket"] = ticket
            return current
        _snapshot = {
            "ticket": ticket,
            "state": state,
            "memberships": memberships,
            "participants": active,
            "floors": floors,
            "budgeted": budgeted,
            "rows": rows,
        }
        return _snapshot


def membership(user_id: str) -> str | None:
    """The member's group in the latest snapshot, before any change being applied."""
    snapshot = _snapshot
    return snapshot["memberships"].get(user_id) if snapshot else None


async def refresh_async() -> None:
    if enforced():
        await asyncio.to_thread(refresh)


async def pin() -> contextvars.Token | None:
    """Freeze one snapshot for the rest of the current reconciliation pass."""
    if not enforced():
        return None
    if _pinned.get() is not None:
        return None
    return _pinned.set(await asyncio.to_thread(refresh))


def unpin(token: contextvars.Token | None) -> None:
    if token is not None:
        _pinned.reset(token)


def allowance(node: OrganizationNode, user_id: str) -> OrganizationNode:
    """Return ``node`` with ``per_user`` replaced by the user's enforced share."""
    if not enforced():
        return node
    snapshot = _pinned.get()
    pinned = snapshot is not None
    if snapshot is None:
        snapshot = _snapshot or refresh()
    if node.id not in snapshot["budgeted"]:
        return node
    if snapshot["memberships"].get(user_id) != node.id:
        if user_id not in snapshot["participants"] and user_id not in _marked:
            value = 0  # No sign-in or key yet: nothing is reserved.
        elif not pinned and refresh() is not snapshot:
            return allowance(node, user_id)
        else:
            # Membership changed after the snapshot was built. Never cap a
            # participant at zero: keep the key's current cap and retry.
            raise HTTPException(409, "Organization membership changed during synchronization; retrying next pass")
    else:
        share = snapshot["rows"][node.id]["users"].get(user_id)
        # A deficit leaves automatic shares unknown; allow no new spend.
        value = share if share is not None else snapshot["floors"].get(user_id, 0)
    if node.per_user is not None:
        value = min(value, _units(node.per_user, ROUND_FLOOR))
    return replace(node, per_user=allocation.dollars(value))
