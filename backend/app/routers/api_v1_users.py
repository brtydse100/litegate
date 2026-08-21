"""Administrative local-account endpoints."""

import asyncio

from fastapi import APIRouter, Depends, HTTPException, status

from app.models import LocalUserCreate, LocalUserInfo, LocalUserUpdate
from app.rate_limit import check_key_rate_limit
from app.routers.api_actor import ApiActor, get_api_actor, record_audit, require_api_admin
from app.services import litellm as llm, local_users

router = APIRouter()


@router.get("/users", response_model=list[LocalUserInfo])
async def api_list_users(actor: ApiActor = Depends(get_api_actor)):
    require_api_admin(actor)
    return await asyncio.to_thread(local_users.list_users)


@router.post("/users", response_model=LocalUserInfo, status_code=status.HTTP_201_CREATED)
async def api_create_user(payload: LocalUserCreate, actor: ApiActor = Depends(get_api_actor)):
    require_api_admin(actor)
    check_key_rate_limit(actor.user.user_id)
    try:
        user = await asyncio.to_thread(local_users.create_user, payload.username, payload.email, payload.password, payload.role)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await llm.ensure_user_exists(user["user_id"], user["email"])
    await record_audit(actor, "local_user.create", user["user_id"], details={"role": user["role"]})
    return user


@router.patch("/users/{username}", response_model=LocalUserInfo)
async def api_update_user(username: str, payload: LocalUserUpdate, actor: ApiActor = Depends(get_api_actor)):
    require_api_admin(actor)
    check_key_rate_limit(actor.user.user_id)
    existing = local_users.get_user(username)
    if not existing:
        raise HTTPException(status_code=404, detail="Local user not found")
    if existing["user_id"] == actor.user.user_id and payload.active is False:
        raise HTTPException(status_code=400, detail="You cannot disable your own account")
    if existing["user_id"] == actor.user.user_id and payload.role == "user":
        raise HTTPException(status_code=400, detail="You cannot remove your own admin role")
    updated = await asyncio.to_thread(local_users.update_user, username, **payload.model_dump(exclude_unset=True))
    await record_audit(actor, "local_user.update", existing["user_id"], details={"setting_fields": sorted(payload.model_fields_set)})
    return updated
