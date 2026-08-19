from fastapi import APIRouter, Depends, Query
from typing import Optional
from app.dependencies import get_current_user
from app.models import CurrentUser, SpendSummary
from app.services import litellm as llm

router = APIRouter(prefix="/logs", tags=["logs"])


@router.get("")
async def get_logs(
    start_date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    limit: int = Query(100, le=500),
    current_user: CurrentUser = Depends(get_current_user),
):
    logs = await llm.get_spend_logs(
        current_user.user_id,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
    )
    return {"logs": logs}


@router.get("/summary", response_model=SpendSummary)
async def get_summary(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    current_user: CurrentUser = Depends(get_current_user),
):
    logs = await llm.get_spend_logs(
        current_user.user_id,
        start_date=start_date,
        end_date=end_date,
        limit=500,
    )
    total_spend = sum(float(l.get("spend", 0)) for l in logs)
    total_tokens = sum(int(l.get("total_tokens", 0) or 0) for l in logs)
    spend_by_model: dict = {}
    for l in logs:
        model = l.get("model", "unknown")
        spend_by_model[model] = spend_by_model.get(model, 0) + float(l.get("spend", 0))
    return SpendSummary(
        total_spend=round(total_spend, 6),
        total_requests=len(logs),
        total_tokens=total_tokens,
        spend_by_model={k: round(v, 6) for k, v in spend_by_model.items()},
    )
