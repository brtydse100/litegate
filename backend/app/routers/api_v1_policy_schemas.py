"""Administrator discovery of editable LiteLLM policy fields."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.routers.api_actor import ApiActor, get_api_actor, require_api_admin
from app.services.policy_schemas import get_policy_schemas

router = APIRouter()


@router.get("/policy-schemas")
async def api_policy_schemas(actor: Annotated[ApiActor, Depends(get_api_actor)]):
    require_api_admin(actor)
    if actor.proof_key or actor.user.auth_source == "litellm_key":
        raise HTTPException(status_code=403, detail="Administrator portal or management identity required")
    return await get_policy_schemas()
