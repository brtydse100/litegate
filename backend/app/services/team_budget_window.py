"""One installation-wide team budget reset window (TEAM_BUDGET_DURATION).

Each team keeps its own ``max_budget`` (or none, for unlimited), but every team
uses the same ``budget_duration``. LiteLLM aligns ``1d``, ``7d`` and ``1mo`` to
calendar boundaries (midnight, Monday, the 1st, in its configured timezone), so
all teams reset at the same moment. Organization-managed teams already match:
startup configuration validation requires their durations to equal the window.
"""

import asyncio
import logging

from fastapi import HTTPException

from app.config import settings
from app.services import audit, litellm

STARTUP_CONCURRENCY = 5
MAX_PAGES = 50
PAGE_SIZE = 100

_logger = logging.getLogger(__name__)


def apply(changes: dict, *, create: bool) -> dict:
    """Enforce the shared window on a team create or update payload."""
    window = settings.team_budget_duration
    if window is None:
        return changes
    if "budget_duration" in changes and changes["budget_duration"] != window:
        raise HTTPException(status_code=422, detail=f"Team budget reset is set for every team by TEAM_BUDGET_DURATION ({window})")
    if create:
        return {**changes, "budget_duration": window}
    # Resending the same duration would make LiteLLM recompute the next reset.
    return {name: value for name, value in changes.items() if name != "budget_duration"}


async def _misaligned_team_ids(window: str) -> list[str]:
    team_ids = []
    for page in range(1, MAX_PAGES + 1):
        result = await litellm.list_teams(page=page, page_size=PAGE_SIZE)
        for team in result["teams"]:
            team_id = team.get("team_id") if isinstance(team, dict) else None
            if team_id and team.get("budget_duration") != window and not settings.organization_hierarchy.is_managed_team(team_id):
                team_ids.append(team_id)
        if result.get("total_pages", 1) <= page:
            return team_ids
    _logger.warning("Team budget window alignment stopped after %d teams", MAX_PAGES * PAGE_SIZE)
    return team_ids


async def align_existing_teams() -> int:
    """One startup pass that moves every other team onto the shared window."""
    window = settings.team_budget_duration
    if window is None:
        return 0
    try:
        team_ids = await _misaligned_team_ids(window)
    except HTTPException as exc:
        _logger.warning("Could not list LiteLLM teams for the budget window: %s", exc.detail)
        return 0
    semaphore = asyncio.Semaphore(STARTUP_CONCURRENCY)

    async def one(team_id: str) -> bool:
        async with semaphore:
            try:
                await litellm.update_team(team_id, {"budget_duration": window})
            except HTTPException as exc:
                _logger.warning("Could not set the budget window on team %s: %s", team_id, exc.detail)
                outcome = "failure"
            else:
                outcome = "success"
            await asyncio.to_thread(
                audit.record,
                actor_id="system:litegate",
                actor_email="",
                action="team.budget_window_aligned",
                target=team_id,
                outcome=outcome,
                details={"budget_duration": window},
            )
            return outcome == "success"

    return sum(await asyncio.gather(*(one(team_id) for team_id in team_ids)))
