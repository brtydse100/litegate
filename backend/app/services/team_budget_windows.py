"""Each team's amounts for the shared scheduled budget windows (nightly).

LiteGate owns the schedule (``TEAM_BUDGET_WINDOWS``); a team only chooses an
amount per window. An amount becomes a LiteLLM team ``budget_limits`` entry with
that window's ``schedule``; no entry means unlimited in that window. Plain
(unscheduled) ``budget_limits`` entries a team already has are always kept.
Requires a LiteLLM build with BerriAI/litellm#54147.
"""

import asyncio
import logging
from collections.abc import Awaitable

from fastapi import HTTPException

from app.budget_windows import SCHEDULE_PREFIX
from app.config import settings
from app.services import audit, litellm, organization_client as upstream

UNSUPPORTED = "LiteLLM rejected the scheduled budget windows; they need a LiteLLM build with BerriAI/litellm#54147"
STARTUP_CONCURRENCY = 5
MAX_PAGES = 50
PAGE_SIZE = 100

_logger = logging.getLogger(__name__)


def _entries(team: dict) -> list[dict]:
    limits = team.get("budget_limits")
    return [entry for entry in limits if isinstance(entry, dict)] if isinstance(limits, list) else []


def _scheduled(entry: dict) -> bool:
    return entry.get("schedule") is not None or str(entry.get("budget_duration") or "").startswith(SCHEDULE_PREFIX)


def amounts(team: dict) -> dict[str, float | None]:
    """The team's amount per configured window; None is unlimited."""
    config = settings.team_budget_windows
    if config is None:
        return {}
    caps = {entry.get("budget_duration"): entry.get("max_budget") for entry in _entries(team)}
    return {window.name: caps.get(config.label(window)) for window in config.windows}


def merge(team: dict, changes: dict[str, float | None]) -> list[dict]:
    """New budget_limits: plain entries kept, one scheduled entry per capped window."""
    config = settings.team_budget_windows
    current = amounts(team)
    unknown = sorted(set(changes) - set(current))
    if unknown:
        raise HTTPException(status_code=422, detail=f"Unknown budget windows: {', '.join(unknown)}")
    wanted = {**current, **changes}
    limits = [{name: value for name, value in entry.items() if value is not None} for entry in _entries(team) if not _scheduled(entry)]
    for window in config.windows:
        if wanted[window.name] is not None:
            limits.append({"max_budget": wanted[window.name], "schedule": config.schedule(window)})
    return limits


def _stale(team: dict) -> bool:
    config = settings.team_budget_windows
    labels = {config.label(window) for window in config.windows}
    return any(_scheduled(entry) and entry.get("budget_duration") not in labels for entry in _entries(team))


async def apply(team_id: str | None, changes: dict, window_budgets: dict | None) -> dict:
    """Turn a create (team_id None) or update request's window amounts into budget_limits."""
    if settings.team_budget_windows is None:
        if window_budgets:
            raise HTTPException(status_code=422, detail="Scheduled budget windows are not configured (TEAM_BUDGET_WINDOWS)")
        return changes
    if "budget_limits" in changes:
        raise HTTPException(status_code=422, detail="budget_limits is managed by the scheduled budget windows; set window amounts instead")
    if window_budgets is None:
        return changes
    team = {} if team_id is None else (await upstream.team_info(team_id)).get("team_info") or {}
    return {**changes, "budget_limits": merge(team, window_budgets)}


async def guarded(operation: Awaitable[dict], changes: dict) -> dict:
    """Name the missing LiteLLM feature when LiteLLM rejects a scheduled entry."""
    try:
        return await operation
    except HTTPException as exc:
        rejected = isinstance(exc.detail, str) and exc.detail.startswith("LiteLLM team operation returned 4")
        if rejected and any(_scheduled(entry) for entry in changes.get("budget_limits") or []):
            raise HTTPException(status_code=exc.status_code, detail=f"{UNSUPPORTED}. {exc.detail}") from exc
        raise


async def usage(team_id: str) -> dict:
    """Each window's cap, current-period spend and next start for one team."""
    config = settings.team_budget_windows
    if config is None:
        raise HTTPException(status_code=404, detail="Scheduled budget windows are not configured")
    info = (await upstream.team_info(team_id)).get("team_info")
    if not isinstance(info, dict):
        raise HTTPException(status_code=404, detail="Team not found")
    caps = amounts(info)
    spent = info.get("budget_limits_usage") if isinstance(info.get("budget_limits_usage"), dict) else {}
    windows = []
    for window in config.public()["windows"]:
        current = spent.get(window["label"]) if isinstance(spent.get(window["label"]), dict) else {}
        windows.append(
            {
                **window,
                "max_budget": caps[window["name"]],
                "current_spend": current.get("current_spend"),
                "active": current.get("active"),
                "next_start": current.get("next_start"),
            }
        )
    return {"team_id": team_id, "timezone": config.timezone, "windows": windows}


async def _stale_teams() -> list[dict]:
    teams = []
    for page in range(1, MAX_PAGES + 1):
        result = await litellm.list_teams(page=page, page_size=PAGE_SIZE)
        teams += [team for team in result["teams"] if isinstance(team, dict) and team.get("team_id") and _stale(team)]
        if result.get("total_pages", 1) <= page:
            return teams
    _logger.warning("Budget window cleanup stopped after %d teams", MAX_PAGES * PAGE_SIZE)
    return teams


async def prune_stale_windows() -> int:
    """One startup pass removing windows that are no longer in the schedule."""
    if settings.team_budget_windows is None:
        return 0
    try:
        teams = await _stale_teams()
    except HTTPException as exc:
        _logger.warning("Could not list LiteLLM teams for budget windows: %s", exc.detail)
        return 0
    semaphore = asyncio.Semaphore(STARTUP_CONCURRENCY)

    async def one(team: dict) -> bool:
        async with semaphore:
            removed = sorted(entry["budget_duration"] for entry in _entries(team) if _scheduled(entry) and _stale({"budget_limits": [entry]}))
            try:
                await litellm.update_team(team["team_id"], {"budget_limits": merge(team, {})})
            except HTTPException as exc:
                _logger.warning("Could not remove old budget windows from team %s: %s", team["team_id"], exc.detail)
                outcome = "failure"
            else:
                outcome = "success"
            await asyncio.to_thread(
                audit.record,
                actor_id="system:litegate",
                actor_email="",
                action="team.budget_windows_pruned",
                target=team["team_id"],
                outcome=outcome,
                details={"removed": removed},
            )
            return outcome == "success"

    return sum(await asyncio.gather(*(one(team) for team in teams)))
