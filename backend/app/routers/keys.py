import asyncio
from secrets import token_hex

from fastapi import APIRouter, Depends, HTTPException, Response
from app.config import settings
from app.dependencies import get_current_user
from app.models import CurrentUser, KeyCreateResponse, KeyDeleteRequest
from app.rate_limit import check_key_rate_limit, key_rate_limit_status
from app.services import litellm as llm
from app.services import audit, key_secrets, organization_sync

router = APIRouter(prefix="/keys", tags=["keys"])


@router.get("")
async def list_keys(current_user: CurrentUser = Depends(get_current_user)):
    keys = await llm.list_user_keys(current_user.user_id)
    policy = await organization_sync.personal_policy(current_user)
    if policy:
        keys = [{**key, "user_budget": policy["per_user"], "user_spend": policy["spend"], "organization_path": policy["path"]} for key in keys]
    return {"keys": await asyncio.to_thread(key_secrets.annotate, keys)}


@router.post("/reveal")
async def reveal_key(payload: KeyDeleteRequest, response: Response, current_user: CurrentUser = Depends(get_current_user)):
    if not settings.save_api_keys_in_db:
        raise HTTPException(status_code=404, detail="API key storage is disabled")
    info = await llm.get_key_info(payload.key)
    if not info:
        raise HTTPException(status_code=404, detail="Key not found")
    owner = info.get("user_id")
    if not current_user.is_admin and owner != current_user.user_id:
        raise HTTPException(status_code=403, detail="Key not owned by user")
    secret = await asyncio.to_thread(key_secrets.get, payload.key, owner)
    if not secret:
        raise HTTPException(status_code=404, detail="No stored copy is available. Regenerate this key once to save it.")
    await asyncio.to_thread(
        audit.record,
        actor_id=current_user.user_id,
        actor_email=current_user.email,
        action="key.reveal",
        target=owner,
    )
    response.headers["Cache-Control"] = "no-store"
    return {"key": secret}


@router.get("/operation-limit")
async def operation_limit(current_user: CurrentUser = Depends(get_current_user)):
    """Return the authenticated user's current mutation allowance without consuming it."""
    return key_rate_limit_status(current_user.user_id)


@router.post("", response_model=KeyCreateResponse, status_code=201)
async def create_key(current_user: CurrentUser = Depends(get_current_user)):
    check_key_rate_limit(current_user.user_id)
    existing = await llm.list_user_keys(current_user.user_id)
    if existing:
        raise HTTPException(status_code=409, detail="You already have a key. Delete it before creating a new one.")
    team_id = current_user.team_ids[0] if current_user.team_ids else None
    result = await organization_sync.generate_key(current_user.user_id, current_user.email, team_id)
    return KeyCreateResponse(
        key=result["key"],
        user_id=result.get("user_id", current_user.user_id),
        expires=result.get("expires"),
    )


@router.post("/regenerate", response_model=KeyCreateResponse, status_code=201)
async def regenerate_key(current_user: CurrentUser = Depends(get_current_user)):
    """Replace existing keys while carrying their spend into the new key."""
    check_key_rate_limit(current_user.user_id)
    existing = await llm.list_user_keys(current_user.user_id)
    carried_spend = llm.total_key_spend(existing)
    team_id = current_user.team_ids[0] if current_user.team_ids else None
    name = current_user.email.split("@")[0] if current_user.email else current_user.user_id.split(":")[-1]
    result = await organization_sync.generate_key(
        current_user.user_id,
        current_user.email,
        team_id,
        initial_spend=carried_spend,
        key_alias=f"{name}'s rotated key {token_hex(4)}",
    )
    try:
        for key_info in existing:
            token = key_info.get("token") or key_info.get("api_key") or key_info.get("key")
            if token:
                await llm.delete_key(token)
    except Exception:
        # Revoke the replacement so a failed cleanup does not leave an extra live key.
        await llm.delete_key(result["key"])
        raise
    return KeyCreateResponse(
        key=result["key"],
        user_id=result.get("user_id", current_user.user_id),
        expires=result.get("expires"),
    )


async def _delete_owned_key(key: str, current_user: CurrentUser) -> dict:
    check_key_rate_limit(current_user.user_id)
    owned = {k.get("token") or k.get("api_key") or k.get("key") for k in await llm.list_user_keys(current_user.user_id)}
    if key not in owned:
        raise HTTPException(status_code=403, detail="Key not owned by user")
    await llm.delete_key(key)
    return {"deleted": True}


@router.delete("")
async def delete_key(payload: KeyDeleteRequest, current_user: CurrentUser = Depends(get_current_user)):
    """Delete an owned key without exposing the credential in access-log URLs."""
    return await _delete_owned_key(payload.key, current_user)


@router.delete("/{key}", deprecated=True)
async def delete_key_legacy(key: str, current_user: CurrentUser = Depends(get_current_user)):
    """Compatibility route; use DELETE /api/keys with a JSON body instead."""
    return await _delete_owned_key(key, current_user)
