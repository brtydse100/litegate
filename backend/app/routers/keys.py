from fastapi import APIRouter, Depends, HTTPException
from app.dependencies import get_current_user
from app.models import CurrentUser, KeyCreateResponse
from app.rate_limit import check_key_rate_limit
from app.services import litellm as llm

router = APIRouter(prefix="/keys", tags=["keys"])


@router.get("")
async def list_keys(current_user: CurrentUser = Depends(get_current_user)):
    return {"keys": await llm.list_user_keys(current_user.user_id)}


@router.post("", response_model=KeyCreateResponse, status_code=201)
async def create_key(current_user: CurrentUser = Depends(get_current_user)):
    check_key_rate_limit(current_user.user_id)
    existing = await llm.list_user_keys(current_user.user_id)
    if existing:
        raise HTTPException(status_code=409, detail="You already have a key. Delete it before creating a new one.")
    result = await llm.generate_key(current_user.user_id, current_user.email)
    return KeyCreateResponse(
        key=result["key"],
        user_id=result.get("user_id", current_user.user_id),
        expires=result.get("expires"),
    )


@router.post("/regenerate", response_model=KeyCreateResponse, status_code=201)
async def regenerate_key(current_user: CurrentUser = Depends(get_current_user)):
    """Delete all existing keys then issue a new one. User-level spend history is preserved."""
    check_key_rate_limit(current_user.user_id)
    existing = await llm.list_user_keys(current_user.user_id)
    for k in existing:
        token = k.get("token") or k.get("api_key") or k.get("key")
        if token:
            await llm.delete_key(token)
    result = await llm.generate_key(current_user.user_id, current_user.email)
    return KeyCreateResponse(
        key=result["key"],
        user_id=result.get("user_id", current_user.user_id),
        expires=result.get("expires"),
    )


@router.delete("/{key}")
async def delete_key(key: str, current_user: CurrentUser = Depends(get_current_user)):
    owned = {k.get("token") or k.get("api_key") or k.get("key")
             for k in await llm.list_user_keys(current_user.user_id)}
    if key not in owned:
        raise HTTPException(status_code=403, detail="Key not owned by user")
    await llm.delete_key(key)
    return {"deleted": True}
