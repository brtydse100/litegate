"""Personal, precomputed usage for portal identities only."""

import asyncio
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException

from app.config import settings
from app.dependencies import get_current_user
from app.models import CurrentUser
from app.services import analytics_store

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("")
async def personal_analytics(start_date: date | None = None, end_date: date | None = None, current_user: CurrentUser = Depends(get_current_user)):
    if not settings.analytics_enabled:
        raise HTTPException(404, "Personal analytics are disabled")
    today = datetime.now(timezone.utc).date()
    end = end_date or today
    earliest = today - timedelta(days=settings.analytics_retention_days - 1)
    if end < earliest or end > today:
        raise HTTPException(422, "Select dates within the configured analytics retention window")
    start = start_date or max(earliest, end - timedelta(days=29))
    if start < earliest or end > today or start > end:
        raise HTTPException(422, "Select dates within the configured analytics retention window")
    return await asyncio.to_thread(analytics_store.read, current_user.user_id, start.isoformat(), end.isoformat())
