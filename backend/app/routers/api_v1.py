"""Stable automation API for users and virtual-key management."""

import asyncio
import hmac
from dataclasses import dataclass
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials
from jwt import InvalidTokenError

from app.config import settings
from app.dependencies import bearer, decode_portal_token, enforce_account_state
from app.models import (
    ApiKeyCreateRequest,
    BulkKeyUpdateRequest,
    CurrentUser,
    KeyCreateResponse,
    LocalUserCreate,
    LocalUserInfo,
    LocalUserUpdate,
)
from app.rate_limit import check_key_rate_limit
from app.services import litellm as llm
from app.services import local_users

router = APIRouter(prefix="/v1", tags=["api-v1"])


@dataclass
class ApiActor:
    user: CurrentUser
    proof_key: Optional[str] = None

    @property
    def is_admin(self) -> bool:
        return self.user.is_admin


async def get_api_actor(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
) -> ApiActor:
    if (
        x_api_key
        and settings.management_api_key
        and hmac.compare_digest(x_api_key, settings.management_api_key)
    ):
        return ApiActor(
            CurrentUser(
                user_id="api:management",
                email="management-api@local",
                role="admin",
                auth_source="management_api_key",
            )
        )
    if credentials:
        token = credentials.credentials
        try:
            return ApiActor(enforce_account_state(decode_portal_token(token)))
        except InvalidTokenError:
            info = await llm.get_key_info(token)
            if info is not None:
                return ApiActor(
                    CurrentUser(
                        user_id=info.get("user_id") or "key-holder",
                        email="",
                        role="user",
                        auth_source="litellm_key",
                    ),
                    proof_key=token,
                )
    raise HTTPException(status_code=401, detail="Valid portal token, management key, or LiteLLM key required")


def _require_api_admin(actor: ApiActor) -> None:
    if not actor.is_admin:
        raise HTTPException(status_code=403, detail="Administrator access required")


@router.get("/me")
async def api_me(actor: ApiActor = Depends(get_api_actor)):
    return {
        "user_id": actor.user.user_id,
        "email": actor.user.email,
        "role": actor.user.role,
        "auth_source": actor.user.auth_source,
    }


@router.get("/keys")
async def api_list_keys(
    all_keys: bool = Query(default=False, alias="all"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=100),
    actor: ApiActor = Depends(get_api_actor),
):
    if all_keys:
        _require_api_admin(actor)
        return await llm.list_keys(page=page, size=size)
    if actor.proof_key:
        info = await llm.get_key_info(actor.proof_key)
        return {"keys": [info] if info else []}
    if actor.user.user_id == "api:management":
        raise HTTPException(status_code=400, detail="Use ?all=true with a management API key")
    return {"keys": await llm.list_user_keys(actor.user.user_id)}


@router.post("/keys", response_model=KeyCreateResponse, status_code=status.HTTP_201_CREATED)
async def api_create_key(
    payload: Optional[ApiKeyCreateRequest] = None,
    actor: ApiActor = Depends(get_api_actor),
):
    if actor.proof_key:
        raise HTTPException(status_code=403, detail="A LiteLLM key cannot create another key")
    requested_user_id = payload.user_id if payload else None
    requested_email = payload.email if payload else None
    if requested_user_id and not actor.is_admin:
        raise HTTPException(status_code=403, detail="Only admins can create keys for another user")
    user_id = requested_user_id or actor.user.user_id
    email = requested_email or actor.user.email
    if user_id == "api:management":
        raise HTTPException(status_code=422, detail="user_id is required for management API calls")
    check_key_rate_limit(actor.user.user_id)
    if await llm.list_user_keys(user_id):
        raise HTTPException(status_code=409, detail="This user already has a key")
    result = await llm.generate_key(user_id, email)
    return KeyCreateResponse(
        key=result["key"], user_id=result.get("user_id", user_id), expires=result.get("expires")
    )


@router.patch("/keys/bulk")
async def bulk_update_keys(
    payload: BulkKeyUpdateRequest,
    actor: ApiActor = Depends(get_api_actor),
):
    """Apply one settings change to multiple keys. Administrator access is required."""
    _require_api_admin(actor)
    check_key_rate_limit(actor.user.user_id)

    changes = payload.settings.model_dump(exclude_unset=True)
    semaphore = asyncio.Semaphore(5)

    async def update_one(key: str) -> dict:
        async with semaphore:
            try:
                await llm.update_key(key, changes)
                return {"key": key, "updated": True}
            except HTTPException as exc:
                return {"key": key, "updated": False, "error": str(exc.detail)}
            except Exception:
                return {"key": key, "updated": False, "error": "Unexpected update failure"}

    results = await asyncio.gather(*(update_one(key) for key in payload.keys))
    updated = sum(1 for result in results if result["updated"])
    return {"updated": updated, "failed": len(results) - updated, "results": results}


@router.get("/users", response_model=list[LocalUserInfo])
async def api_list_users(actor: ApiActor = Depends(get_api_actor)):
    _require_api_admin(actor)
    return await asyncio.to_thread(local_users.list_users)


@router.post("/users", response_model=LocalUserInfo, status_code=status.HTTP_201_CREATED)
async def api_create_user(payload: LocalUserCreate, actor: ApiActor = Depends(get_api_actor)):
    _require_api_admin(actor)
    try:
        user = await asyncio.to_thread(
            local_users.create_user, payload.username, payload.email, payload.password, payload.role
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await llm.ensure_user_exists(user["user_id"], user["email"])
    return user


@router.patch("/users/{username}", response_model=LocalUserInfo)
async def api_update_user(
    username: str,
    payload: LocalUserUpdate,
    actor: ApiActor = Depends(get_api_actor),
):
    _require_api_admin(actor)
    existing = local_users.get_user(username)
    if not existing:
        raise HTTPException(status_code=404, detail="Local user not found")
    if existing["user_id"] == actor.user.user_id and payload.active is False:
        raise HTTPException(status_code=400, detail="You cannot disable your own account")
    if existing["user_id"] == actor.user.user_id and payload.role == "user":
        raise HTTPException(status_code=400, detail="You cannot remove your own admin role")
    return await asyncio.to_thread(
        local_users.update_user, username, **payload.model_dump(exclude_unset=True)
    )
