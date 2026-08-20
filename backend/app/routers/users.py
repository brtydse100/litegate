import asyncio

from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import require_admin
from app.models import CurrentUser, LocalUserCreate, LocalUserInfo, LocalUserUpdate
from app.rate_limit import check_key_rate_limit
from app.services import litellm as llm
from app.services import local_users

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[LocalUserInfo])
async def list_local_users(_: CurrentUser = Depends(require_admin)):
    return await asyncio.to_thread(local_users.list_users)


@router.post("", response_model=LocalUserInfo, status_code=status.HTTP_201_CREATED)
async def create_local_user(payload: LocalUserCreate, current_user: CurrentUser = Depends(require_admin)):
    check_key_rate_limit(current_user.user_id)
    try:
        user = await asyncio.to_thread(
            local_users.create_user, payload.username, payload.email, payload.password, payload.role
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await llm.ensure_user_exists(user["user_id"], user["email"])
    return user


@router.patch("/{username}", response_model=LocalUserInfo)
async def update_local_user(
    username: str,
    payload: LocalUserUpdate,
    current_user: CurrentUser = Depends(require_admin),
):
    check_key_rate_limit(current_user.user_id)
    existing = local_users.get_user(username)
    if not existing:
        raise HTTPException(status_code=404, detail="Local user not found")
    if existing["user_id"] == current_user.user_id and payload.active is False:
        raise HTTPException(status_code=400, detail="You cannot disable your own account")
    if existing["user_id"] == current_user.user_id and payload.role == "user":
        raise HTTPException(status_code=400, detail="You cannot remove your own admin role")
    return await asyncio.to_thread(
        local_users.update_user, username, **payload.model_dump(exclude_unset=True)
    )
