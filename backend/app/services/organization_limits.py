"""Administrator per-user limits that override organizationHierarchy ``perUser``.

The configured hierarchy stays the source of structure. A global administrator
may replace a group's ``perUser`` from the portal; the override is stored with
the budget plan and inherited by child groups exactly like a configured value.
Clearing it restores the configured value.
"""

import threading

from fastapi import HTTPException

from app.config import settings
from app.organization import OrganizationHierarchy
from app.services import budget_allocations as allocation, budget_enforcement, budget_store

_lock = threading.Lock()
_base: OrganizationHierarchy | None = None
_effective: OrganizationHierarchy | None = None
_applied: dict[str, int] = {}


def overrides(state: dict) -> dict[str, int]:
    return {node: value for node, value in (state.get("per_user") or {}).items() if value is not None}


def base() -> OrganizationHierarchy:
    """The configured hierarchy, before portal overrides."""
    current = settings.organization_hierarchy
    return _base if current is _effective and _base is not None else current


def configured_per_user(node_id: str) -> float | None:
    node = base().nodes.get(node_id)
    return node.per_user if node else None


def apply(state: dict | None = None) -> None:
    """Install the effective hierarchy for the stored overrides."""
    global _base, _effective, _applied
    state = budget_store.read() if state is None else state
    with _lock:
        configured = base()
        values = {node_id: value for node_id, value in overrides(state).items() if node_id in configured.nodes}
        _applied = values
        if not values:
            _base, _effective = configured, configured
            settings.organization_hierarchy = configured
            return
        data = configured.model_dump(exclude_unset=True)
        positions = {}
        for depth, level in enumerate(configured.levels):
            for bundle_index, bundle in enumerate(level.groups):
                for member_index, member in enumerate(bundle.members):
                    positions[id(member)] = (depth, bundle_index, member_index)
        for node_id, value in values.items():
            depth, bundle_index, member_index = positions[id(configured.nodes[node_id].member)]
            member = data["levels"][depth]["groups"][bundle_index]["members"][member_index]
            member.setdefault("budget", {})["perUser"] = allocation.dollars(value)
        # Revalidation drops private state, so carry adopted LiteLLM teams over.
        effective = OrganizationHierarchy.model_validate(data).bound(configured.team_bindings)
        _base, _effective = configured, effective
        settings.organization_hierarchy = effective


def override(node_id: str) -> float | None:
    if settings.organization_hierarchy is not _effective:
        return None  # The configuration was replaced since the overrides were applied.
    value = _applied.get(node_id)
    return allocation.dollars(value) if value is not None else None


def describe(node_id: str) -> dict:
    node = settings.organization_hierarchy.nodes.get(node_id)
    return {
        "node_id": node_id,
        "per_user": node.per_user if node else None,
        "per_user_config": configured_per_user(node_id),
        "per_user_override": override(node_id),
    }


def save(node_id: str, amount: int | None) -> dict:
    """Store (or clear, with None) a group's per-user limit and apply it now."""
    if node_id not in base().nodes:
        raise HTTPException(404, "Organization group not found")

    def change(state):
        values = dict(state.get("per_user") or {})
        if amount is None:
            values.pop(node_id, None)
        else:
            values[node_id] = amount
        state["per_user"] = values

    for attempt in range(3):
        try:
            state = budget_store.edit(budget_store.read()["revision"], change)
            break
        except HTTPException as exc:
            if exc.status_code != 409 or attempt == 2:
                raise
    apply(state)
    if budget_enforcement.enforced():
        budget_enforcement.refresh()
    return describe(node_id)
