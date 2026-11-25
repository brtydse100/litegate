"""Startup pass keeping every team's window caps in line with the schedule (nightly).

Changed default caps, removed windows and teams created outside LiteGate
(directly in LiteLLM or by the organization sync) all change what a team should
enforce, so each start rewrites the teams whose caps or recorded choices differ.
"""

import asyncio
import logging

from fastapi import HTTPException

from app.config import settings
from app.services import audit, litellm
from app.services.team_budget_windows import OVERRIDES, caps, entries, metadata, overrides, scheduled, synced

STARTUP_CONCURRENCY = 5
MAX_PAGES = 50
PAGE_SIZE = 100

_logger = logging.getLogger(__name__)


def _enforced(team: dict) -> dict[str, float | None]:
    return {str(entry.get("budget_duration") or ""): entry.get("max_budget") for entry in entries(team) if scheduled(entry)}


def needs_sync(team: dict) -> bool:
    config = settings.team_budget_windows
    chosen = overrides(team)
    limits = caps(chosen, team["team_id"])
    wanted = {config.label(window): limits[window.id] for window in config.windows if limits[window.id] is not None}
    return _enforced(team) != wanted or metadata(team).get(OVERRIDES) != chosen


async def _teams() -> list[dict]:
    teams, seen, complete = [], set(), False
    for page in range(1, MAX_PAGES + 1):
        result = await litellm.list_teams(page=page, page_size=PAGE_SIZE)
        listed = [team for team in result["teams"] if isinstance(team, dict) and team.get("team_id")]
        seen.update(team["team_id"] for team in listed)
        teams += [team for team in listed if needs_sync(team)]
        if result.get("total_pages", 1) <= page:
            complete = True
            break
    if not complete:
        _logger.warning("Budget window sync stopped after %d teams", MAX_PAGES * PAGE_SIZE)
    missing = sorted(set(settings.team_budget_windows.teams) - seen)
    if complete and missing:
        _logger.warning("TEAM_BUDGET_WINDOWS sets caps for teams not found in LiteLLM: %s", ", ".join(missing))
    return teams


async def sync_team_windows() -> int:
    """Rewrite each team whose window caps differ from configuration and its custom choices."""
    if settings.team_budget_windows is None:
        return 0
    try:
        teams = await _teams()
    except HTTPException as exc:
        _logger.warning("Could not list LiteLLM teams for budget windows: %s", exc.detail)
        return 0
    semaphore = asyncio.Semaphore(STARTUP_CONCURRENCY)

    async def one(team: dict) -> bool:
        async with semaphore:
            chosen = overrides(team)
            try:
                await litellm.update_team(team["team_id"], synced(team, chosen))
            except HTTPException as exc:
                _logger.warning("Could not sync budget windows for team %s: %s", team["team_id"], exc.detail)
                outcome = "failure"
            else:
                outcome = "success"
            await asyncio.to_thread(
                audit.record,
                actor_id="system:litegate",
                actor_email="",
                action="team.budget_windows_synced",
                target=team["team_id"],
                outcome=outcome,
                details={"before": _enforced(team), "caps": caps(chosen, team["team_id"])},
            )
            return outcome == "success"

    return sum(await asyncio.gather(*(one(team) for team in teams)))
