"""Read-only administrative organization and usage endpoints."""

import asyncio
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, StrictFloat, StrictInt, StrictStr

from app.routers.api_actor import ApiActor, get_api_actor, record_audit
from app.services import budget_allocations as allocation, organization_access, organization_limits, organization_reports, organization_sync

router = APIRouter(prefix="/v1/organization", tags=["organization"])


@router.get("")
async def organization_overview(actor: ApiActor = Depends(get_api_actor)):
    return await organization_reports.overview(await organization_access.resolve_scope(actor))


@router.get("/access")
async def organization_access_capabilities(actor: ApiActor = Depends(get_api_actor)):
    return await organization_access.capabilities(actor)


@router.get("/children")
async def organization_children(
    parent: str | None = Query(default=None, max_length=24),
    actor: ApiActor = Depends(get_api_actor),
):
    return await organization_reports.children(parent, await organization_access.resolve_scope(actor))


@router.get("/groups/{node_id}")
async def organization_group(node_id: str, actor: ApiActor = Depends(get_api_actor)):
    return await organization_reports.group_detail(node_id, await organization_access.resolve_scope(actor))


@router.get("/users")
async def organization_users(
    node: list[str] | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    actor: ApiActor = Depends(get_api_actor),
):
    return await organization_reports.users(node, page, page_size, await organization_access.resolve_scope(actor))


@router.get("/usage")
async def organization_usage(
    node: list[str] | None = Query(default=None),
    start_date: date | None = None,
    end_date: date | None = None,
    actor: ApiActor = Depends(get_api_actor),
):
    scope = await organization_access.resolve_scope(actor)
    end = end_date or datetime.now(timezone.utc).date()
    if start_date is None:
        if (end - date.min).days < 29:
            raise HTTPException(status_code=422, detail="Provide a start_date when the default 30-day range precedes year 1")
        start_date = end - timedelta(days=29)
    return await organization_reports.usage(node, start_date, end, scope)


class PerUserLimit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    amount: StrictInt | StrictFloat | StrictStr | None


@router.patch("/groups/{node_id}/per-user")
async def set_group_per_user(node_id: str, body: PerUserLimit, actor: ApiActor = Depends(get_api_actor)):
    """Override (or with null, restore) a group's configured per-user limit."""
    scope = await organization_access.resolve_scope(actor)
    if not scope.global_admin:
        raise HTTPException(status_code=403, detail="System administrator access required to change per-user limits")
    amount = allocation.units(body.amount) if body.amount is not None else None
    result = await asyncio.to_thread(organization_limits.save, node_id, amount)
    await record_audit(actor, "organization.per_user_limit", node_id, details={"per_user_override": result["per_user_override"]})
    organization_sync.request_reconciliation()
    return result
