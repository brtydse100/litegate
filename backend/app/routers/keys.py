from secrets import token_hex

from fastapi import APIRouter, Depends, HTTPException
from app.dependencies import get_current_user
from app.models import CurrentUser, KeyCreateResponse
from app.rate_limit import check_key_rate_limit, key_rate_limit_status
from app.services import litellm as llm

router = APIRouter(prefix="/keys", tags=["keys"])


@router.get("")
async def list_keys(current_user: CurrentUser = Depends(get_current_user)):
    return {"keys": await llm.list_user_keys(current_user.user_id)}


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
    result = await llm.generate_key(current_user.user_id, current_user.email, team_id)
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
    result = await llm.generate_key(
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


@router.delete("/{key}")
async def delete_key(key: str, current_user: CurrentUser = Depends(get_current_user)):
    check_key_rate_limit(current_user.user_id)
    owned = {k.get("token") or k.get("api_key") or k.get("key")
             for k in await llm.list_user_keys(current_user.user_id)}
    if key not in owned:
        raise HTTPException(status_code=403, detail="Key not owned by user")
    await llm.delete_key(key)
    return {"deleted": True}
