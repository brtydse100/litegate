"""Administrative runtime status and audit endpoints."""

import asyncio

from fastapi import APIRouter, Depends, Query

from app.routers.api_actor import ApiActor, get_api_actor, require_api_admin
from app.services import audit, litellm as llm, local_users

router = APIRouter()


@router.get("/status")
async def api_status(actor: ApiActor = Depends(get_api_actor)):
    require_api_admin(actor)
    litellm_status, database_status = await asyncio.gather(
        llm.healthcheck(), asyncio.to_thread(local_users.healthcheck)
    )
    return {
        "ready": bool(litellm_status["ok"] and database_status["ok"]),
        "dependencies": {"litellm": litellm_status, "database": database_status},
        "storage_mode": "sqlite-single-replica",
    }


@router.get("/audit-events")
async def api_audit_events(limit: int = Query(default=100, ge=1, le=500), actor: ApiActor = Depends(get_api_actor)):
    require_api_admin(actor)
    return {"events": await asyncio.to_thread(audit.list_events, limit)}
