"""Read-only administrative organization and usage endpoints."""

from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query

from app.routers.api_actor import ApiActor, get_api_actor, require_api_admin
from app.services import organization_reports

router = APIRouter(prefix="/v1/organization", tags=["organization"])


@router.get("")
async def organization_overview(actor: ApiActor = Depends(get_api_actor)):
    require_api_admin(actor)
    return await organization_reports.overview()


@router.get("/users")
async def organization_users(
    node: str | None = Query(default=None, max_length=24),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    actor: ApiActor = Depends(get_api_actor),
):
    require_api_admin(actor)
    return await organization_reports.users(node, page, page_size)


@router.get("/usage")
async def organization_usage(
    node: str | None = Query(default=None, max_length=24),
    start_date: date | None = None,
    end_date: date | None = None,
    actor: ApiActor = Depends(get_api_actor),
):
    require_api_admin(actor)
    end = end_date or datetime.now(timezone.utc).date()
    if start_date is None:
        if (end - date.min).days < 29:
            raise HTTPException(status_code=422, detail="Provide a start_date when the default 30-day range precedes year 1")
        start_date = end - timedelta(days=29)
    return await organization_reports.usage(node, start_date, end)
