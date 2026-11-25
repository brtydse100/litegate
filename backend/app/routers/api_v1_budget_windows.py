"""Administrator view of one team's scheduled budget windows (nightly)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path

from app.routers.api_actor import ApiActor, get_api_actor, require_api_admin
from app.services import team_budget_windows

router = APIRouter(prefix="/v1", tags=["api-v1"])


@router.get("/teams/{team_id}/budget-windows")
async def api_team_budget_windows(
    team_id: Annotated[str, Path(min_length=1, max_length=128)],
    actor: Annotated[ApiActor, Depends(get_api_actor)],
):
    """Each shared window's cap, current-period spend and next start for one team."""
    require_api_admin(actor)
    return await team_budget_windows.usage(team_id)
