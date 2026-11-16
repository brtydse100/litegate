"""Administrator-only, read-only registered people directory."""

from fastapi import APIRouter, Depends, HTTPException, Query

from app.routers.api_actor import ApiActor, get_api_actor, require_api_admin
from app.services import people

router = APIRouter(tags=["people"])


@router.get("/people")
async def directory(
    page: int = Query(default=1, ge=1, le=100000),
    size: int = Query(default=25, ge=1, le=100),
    search: str = Query(default="", max_length=200),
    actor: ApiActor = Depends(get_api_actor),
):
    require_api_admin(actor)
    if actor.proof_key is not None or actor.user.auth_source == "litellm_key":
        raise HTTPException(status_code=403, detail="Administrator access required")
    return await people.directory(page=page, size=size, search=search.strip())
