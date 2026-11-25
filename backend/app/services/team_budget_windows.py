"""Each team's caps for the shared scheduled budget windows (nightly).

LiteGate owns the schedule (``TEAM_BUDGET_WINDOWS``). A team's cap in a window
comes from, in order: the window's ``team_budgets`` entry for that team in
configuration (read-only in the UI), a custom cap or unlimited an administrator
chose, or the window's ``default_budget``. Custom choices live in the team's
LiteLLM metadata under ``OVERRIDES``. A cap becomes a LiteLLM team
``budget_limits`` entry with that window's ``schedule``; no entry means
unlimited in that window. Plain (unscheduled) ``budget_limits`` entries a team
already has are always kept. Requires a LiteLLM build with BerriAI/litellm#54147.
"""

from collections.abc import Awaitable

from fastapi import HTTPException

from app.budget_windows import SCHEDULE_PREFIX
from app.config import settings
from app.services import organization_client as upstream

UNSUPPORTED = "LiteLLM rejected the scheduled budget windows; they need a LiteLLM build with BerriAI/litellm#54147"
OVERRIDES = "litegate_window_budgets"
CONFIG = "config"


def entries(team: dict) -> list[dict]:
    limits = team.get("budget_limits")
    return [entry for entry in limits if isinstance(entry, dict)] if isinstance(limits, list) else []


def metadata(team: dict) -> dict:
    return team.get("metadata") if isinstance(team.get("metadata"), dict) else {}


def scheduled(entry: dict) -> bool:
    return entry.get("schedule") is not None or str(entry.get("budget_duration") or "").startswith(SCHEDULE_PREFIX)


def amounts(team: dict) -> dict[str, float | None]:
    """The cap LiteLLM enforces per configured window; None is unlimited."""
    config = settings.team_budget_windows
    if config is None:
        return {}
    limits = {entry.get("budget_duration"): entry.get("max_budget") for entry in entries(team)}
    return {window.name: limits.get(config.label(window)) for window in config.windows}


def configured(team_id: str | None) -> dict[str, float | None]:
    """Windows whose cap configuration sets for this team (read-only in the UI)."""
    windows = settings.team_budget_windows.windows
    return {window.name: window.team_budgets[team_id] for window in windows if team_id and team_id in window.team_budgets}


def overrides(team: dict) -> dict[str, float | None]:
    """Windows where an administrator chose a custom cap (None is unlimited)."""
    names = {window.name for window in settings.team_budget_windows.windows}
    stored = metadata(team).get(OVERRIDES)
    if isinstance(stored, dict):
        return {
            name: value
            for name, value in stored.items()
            if name in names and (value is None or (isinstance(value, (int, float)) and not isinstance(value, bool)))
        }
    # A team capped before defaults existed keeps those caps as its own.
    return {name: cap for name, cap in amounts(team).items() if cap is not None}


def caps(chosen: dict[str, float | None], team_id: str | None = None) -> dict[str, float | None]:
    """Each window's cap: configuration for this team, else the custom choice, else the default."""
    fixed = configured(team_id)
    return {
        window.name: fixed[window.name] if window.name in fixed else chosen.get(window.name, window.default_budget)
        for window in settings.team_budget_windows.windows
    }


def merge(team: dict, wanted: dict[str, float | None]) -> list[dict]:
    """New budget_limits: plain entries kept, one scheduled entry per capped window."""
    config = settings.team_budget_windows
    limits = [{name: value for name, value in entry.items() if value is not None} for entry in entries(team) if not scheduled(entry)]
    for window in config.windows:
        if wanted.get(window.name) is not None:
            limits.append({"max_budget": wanted[window.name], "schedule": config.schedule(window)})
    return limits


def choose(team: dict, changes: dict[str, float | str | None]) -> dict[str, float | None]:
    """The team's custom choices after a request: an amount or None is custom, "config" follows configuration."""
    chosen = overrides(team)
    unknown = sorted(set(changes) - set(caps({})))
    if unknown:
        raise HTTPException(status_code=422, detail=f"Unknown budget windows: {', '.join(unknown)}")
    fixed = configured(team.get("team_id"))
    locked = sorted(name for name, value in changes.items() if name in fixed and value != CONFIG)
    if locked:
        raise HTTPException(status_code=409, detail=f"Budget windows set in configuration for this team: {', '.join(locked)}")
    for name, value in changes.items():
        if value == CONFIG:
            chosen.pop(name, None)
        else:
            chosen[name] = value
    return chosen


def synced(team: dict, chosen: dict[str, float | None], base: dict | None = None) -> dict:
    """The budget_limits and metadata that make LiteLLM enforce these choices."""
    return {
        "budget_limits": merge(team, caps(chosen, team.get("team_id"))),
        "metadata": {**(metadata(team) if base is None else base), OVERRIDES: chosen},
    }


async def apply(team_id: str | None, changes: dict, window_budgets: dict | None) -> dict:
    """Write a create (team_id None) or update request's window choices into budget_limits."""
    if settings.team_budget_windows is None:
        if window_budgets:
            raise HTTPException(status_code=422, detail="Scheduled budget windows are not configured (TEAM_BUDGET_WINDOWS)")
        return changes
    if "budget_limits" in changes:
        raise HTTPException(status_code=422, detail="budget_limits is managed by the scheduled budget windows; set window amounts instead")
    # An update touching neither leaves the team's windows and metadata as they are.
    if team_id is not None and window_budgets is None and "metadata" not in changes:
        return changes
    if team_id is None:
        team = {"team_id": changes.get("team_id")}
    else:
        team = {"team_id": team_id, **((await upstream.team_info(team_id)).get("team_info") or {})}
    base = changes["metadata"] if isinstance(changes.get("metadata"), dict) else None
    return {**changes, **synced(team, choose(team, window_budgets or {}), base)}


async def guarded(operation: Awaitable[dict], changes: dict) -> dict:
    """Name the missing LiteLLM feature when LiteLLM rejects a scheduled entry."""
    try:
        return await operation
    except HTTPException as exc:
        rejected = isinstance(exc.detail, str) and exc.detail.startswith("LiteLLM team operation returned 4")
        if rejected and any(scheduled(entry) for entry in changes.get("budget_limits") or []):
            raise HTTPException(status_code=exc.status_code, detail=f"{UNSUPPORTED}. {exc.detail}") from exc
        raise


def decorate(team: dict) -> dict:
    """The team's custom choices and its configuration-set caps, for the team dialog."""
    if settings.team_budget_windows is None:
        return {}
    fixed = configured(str(team.get("team_id") or ""))
    custom = {name: value for name, value in overrides(team).items() if name not in fixed}
    return {"window_budgets": custom, "window_config": fixed}


async def usage(team_id: str) -> dict:
    """Each window's cap, where it comes from, current-period spend and next start."""
    config = settings.team_budget_windows
    if config is None:
        raise HTTPException(status_code=404, detail="Scheduled budget windows are not configured")
    info = (await upstream.team_info(team_id)).get("team_info")
    if not isinstance(info, dict):
        raise HTTPException(status_code=404, detail="Team not found")
    enforced, chosen, fixed = amounts(info), overrides(info), configured(team_id)
    spent = info.get("budget_limits_usage") if isinstance(info.get("budget_limits_usage"), dict) else {}
    windows = []
    for window in config.public()["windows"]:
        name = window["name"]
        current = spent.get(window["label"]) if isinstance(spent.get(window["label"]), dict) else {}
        windows.append(
            {
                **window,
                "max_budget": enforced[name],
                "source": "custom" if name in chosen and name not in fixed else CONFIG,
                "locked": name in fixed,
                "current_spend": current.get("current_spend"),
                "active": current.get("active"),
                "next_start": current.get("next_start"),
            }
        )
    return {"team_id": team_id, "timezone": config.timezone, "zone": config.zone, "windows": windows}
