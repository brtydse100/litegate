"""Scoped, durable allocation proposals; native enforcement remains gated."""

import asyncio

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictStr

from app.config import settings
from app.routers.api_actor import ApiActor, get_api_actor, record_audit
from app.services import budget_allocations as allocation, budget_native as native, budget_store as store
from app.services import budget_enforcement as enforcement, organization_access as access

router = APIRouter(prefix="/v1/organization/budgets", tags=["organization budgets"])


class Activation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=0, strict=True)


class EnvelopeEdit(Activation):
    amount: StrictFloat | StrictStr


class UserEdit(Activation):
    amount: StrictFloat | StrictStr | None


async def _scope(actor):
    if not settings.hierarchical_budgets_enabled:
        raise HTTPException(404, "Hierarchical budget previews are disabled")
    return await access.resolve_scope(actor)


def _node(node_id, scope):
    node = settings.organization_hierarchy.nodes.get(node_id)
    if node is None or not scope.allows(node):
        raise HTTPException(404, "Organization group not found")
    return node


def _can_edit_envelope(node, scope):
    return scope.global_admin or bool(node.parent_id and scope.allows(settings.organization_hierarchy.nodes[node.parent_id]))


def _view(state, scope, actor):
    members, emails = enforcement.members()
    allocated = enforcement.allocations(state, members, strict=False)
    budgeted = enforcement.budgeted_nodes(state, members)
    groups = []
    for node in settings.organization_hierarchy.nodes.values():
        if not scope.allows(node):
            continue
        row = allocated[node.id]
        users = [
            {
                "user_id": user,
                "email": emails.get(user, ""),
                "allocation": _displayed(node, node.id in budgeted, value),
                "override": allocation.dollars(state["overrides"][user]) if state["overrides"].get(user) is not None else None,
                "mode": ("manual" if state["overrides"].get(user) is not None else "automatic" if node.id in budgeted else "fixed"),
                "used": None,
                "remaining": None,
                "can_edit": scope.global_admin or user != actor.user.user_id,
            }
            for user, value in row["users"].items()
        ]
        groups.append(
            {
                "id": node.id,
                "name": node.member.name,
                "path": scope.path(node),
                "parent_id": scope.metadata(node)["parent_id"],
                "duration": node.duration,
                **{key: allocation.dollars(row[key]) if row[key] is not None else None for key in ("assigned", "allocated", "reserved", "remainder")},
                "allocation_error": row["allocation_error"],
                "used": None,
                "remaining": None,
                "can_edit_envelope": _can_edit_envelope(node, scope),
                "users": users,
            }
        )
    applied = enforcement.enforced()
    return {"revision": state["revision"], "mode": "enforced" if applied else "preview", "applied": applied, "pending": False, "groups": groups}


def _displayed(node, budgeted, value):
    """The allowance enforcement applies: the share capped by perUser, or perUser."""
    if not budgeted:
        return node.per_user
    if value is not None and node.per_user is not None:
        return min(allocation.dollars(value), node.per_user)
    return allocation.dollars(value) if value is not None else None


async def _response(state, scope, actor):
    result = await asyncio.to_thread(_view, state, scope, actor)
    result["capability"] = await native.capabilities()
    return result


@router.get("")
async def budget_view(actor: ApiActor = Depends(get_api_actor)):
    scope = await _scope(actor)
    return await _response(await asyncio.to_thread(store.read), scope, actor)


def _edit(revision, actor, scope, change):
    def validate(state):
        members, _ = enforcement.members()
        # Read invalid proposals without inventing allocations. Any editor may
        # leave an independent (possibly out-of-scope) deficit in place or repair
        # it incrementally, but no edit may create or worsen a deficit.
        before = enforcement.allocations(state, members, strict=False)
        change(state, members)
        after = enforcement.allocations(state, members, strict=False)
        if any(row["shortfall"] > before[node_id]["shortfall"] for node_id, row in after.items()):
            raise HTTPException(409, allocation.ALLOCATION_ERROR)
        owner_group = members.get(actor.user.user_id)
        if not scope.global_admin and owner_group:
            # A group in deficit reports no automatic share; treat it as zero.
            own_before = before[owner_group]["users"].get(actor.user.user_id) or 0
            own_after = after[owner_group]["users"].get(actor.user.user_id) or 0
            if own_after > own_before:
                raise HTTPException(403, "A parent or system administrator must increase your personal allowance")

    state = store.edit(revision, validate)
    if enforcement.enforced():
        enforcement.refresh()
    return state


@router.patch("/groups/{node_id}")
async def edit_envelope(node_id: str, body: EnvelopeEdit, actor: ApiActor = Depends(get_api_actor)):
    scope = await _scope(actor)
    node = _node(node_id, scope)
    if not _can_edit_envelope(node, scope):
        raise HTTPException(
            403, "Only a parent or system administrator can change this team's assigned budget; redistribute it among members or child teams"
        )
    amount = allocation.units(body.amount)
    state = await asyncio.to_thread(_edit, body.revision, actor, scope, lambda state, members: state["envelopes"].update({node_id: amount}))
    await record_audit(actor, "organization.budget_preview", node_id, details={"revision": state["revision"], "kind": "envelope"})
    return await _response(state, scope, actor)


@router.patch("/groups/{node_id}/users/{user_id}")
async def edit_override(node_id: str, user_id: str, body: UserEdit, actor: ApiActor = Depends(get_api_actor)):
    scope = await _scope(actor)
    _node(node_id, scope)
    amount = allocation.units(body.amount) if body.amount is not None else None

    def change(state, members):
        if members.get(user_id) != node_id:
            raise HTTPException(404, "Direct organization member not found")
        state["overrides"][user_id] = amount

    state = await asyncio.to_thread(_edit, body.revision, actor, scope, change)
    await record_audit(actor, "organization.budget_preview", user_id, details={"revision": state["revision"], "kind": "override"})
    return await _response(state, scope, actor)


@router.post("/activate")
async def activate(body: Activation, actor: ApiActor = Depends(get_api_actor)):
    scope = await _scope(actor)
    if not scope.global_admin:
        raise HTTPException(403, "System administrator access required to activate budgets")
    if (await asyncio.to_thread(store.read))["revision"] != body.revision:
        raise HTTPException(409, "Budget revision changed; reload before activation")
    await native.require_capability()
    # Deliberately no activation implementation while native guarantees remain
    # unverified. A future capability implementation must not implicitly enable it.
    raise HTTPException(503, "Strict hierarchical enforcement is not available in this release")
