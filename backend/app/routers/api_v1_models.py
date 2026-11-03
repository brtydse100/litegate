"""A names-only model catalog for administrator policy editors."""

import httpx
from fastapi import APIRouter, Depends, HTTPException

from app.config import settings
from app.routers.api_actor import ApiActor, get_api_actor, require_api_admin
from app.services.litellm_client import client, headers, transport_error

router = APIRouter()


@router.get("/models")
async def available_models(actor: ApiActor = Depends(get_api_actor)):
    require_api_admin(actor)
    try:
        async with client() as upstream:
            response = await upstream.get(f"{settings.litellm_url}/model/info", headers=headers(), timeout=10)
            response.raise_for_status()
            data = response.json()
        models = data.get("data", []) if isinstance(data, dict) else []
        return {"models": sorted({model["model_name"] for model in models if isinstance(model, dict) and isinstance(model.get("model_name"), str)})}
    except httpx.TransportError as exc:
        transport_error(exc)
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=f"LiteLLM model catalog returned {exc.response.status_code}")
