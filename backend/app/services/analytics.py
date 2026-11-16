"""Hourly bounded aggregate collection; personal reads never invoke this service."""

import asyncio
import logging
import math
from time import monotonic
from datetime import date, datetime, timedelta, timezone

from app.config import settings
from app.services import analytics_store as store, litellm, organization_client as upstream
from app.services.organization_reports import validate_usage

_logger = logging.getLogger(__name__)


def _tokens(source: dict, name: str) -> int | None:
    value = source.get(name)
    if value is None:
        return None
    if type(value) is not int or value < 0:
        raise ValueError("Invalid token aggregate")
    return value


def normalize(rows: list[dict]) -> list[dict]:
    result = []
    seen = set()
    for row in rows:
        groups = [("", row["metrics"])]
        groups += [(name, value.get("metrics", value)) for name, value in row.get("breakdown", {}).get("models", {}).items()]
        for model, values in groups:
            key = row["date"], model
            if key in seen:
                raise ValueError("Duplicate daily aggregate")
            seen.add(key)
            result.append(
                {
                    "day": row["date"],
                    "model": model,
                    "requests": values["api_requests"],
                    "tokens": values["total_tokens"],
                    "cost": values["spend"],
                    "input_tokens": _tokens(values, "prompt_tokens"),
                    "output_tokens": _tokens(values, "completion_tokens"),
                }
            )
    return result


async def budgets(user_id: str) -> list[dict]:
    result = []
    for index, key in enumerate(await litellm.list_user_keys(user_id)):
        cap, spend = key.get("max_budget"), key.get("spend")
        valid = type(spend) in (float, int) and math.isfinite(spend) and spend >= 0
        valid_cap = cap is None or type(cap) in (float, int) and math.isfinite(cap) and cap >= 0
        result.append(
            {
                "number": index + 1,
                "limit": cap if valid_cap else None,
                "used": spend if valid else None,
                "remaining": max(0, cap - spend) if cap is not None and valid_cap and valid else None,
                "duration": key.get("budget_duration"),
                "available": valid and valid_cap,
            }
        )
    return result


async def refresh_user(user_id: str, end: date | None = None) -> None:
    end = end or datetime.now(timezone.utc).date()
    start = end - timedelta(days=settings.analytics_retention_days - 1)
    try:
        rows = await upstream.daily_usage(user_id, start.isoformat(), end.isoformat())
        validate_usage(rows, start.isoformat(), end.isoformat())
        snapshot = normalize(rows)
        try:
            allowances = await budgets(user_id)
        except Exception:
            allowances = [{"available": False}]
        await asyncio.to_thread(
            store.publish, user_id, snapshot, start.isoformat(), end.isoformat(), allowances, datetime.now(timezone.utc).isoformat()
        )
    except Exception:
        _logger.warning("Personal analytics refresh failed; keeping the previous snapshot")
        await asyncio.to_thread(store.failed, user_id)


async def discover_users() -> None:
    """One bounded roster scan per pass, independent of hierarchy/key ownership."""
    seen = set()
    async with asyncio.timeout(120):
        for page in range(1, 101):
            data = await upstream.request("GET", "/user/list", params={"page": page, "page_size": 100, "sort_by": "user_id", "sort_order": "asc"})
            batch = data.get("users")
            pages = data.get("total_pages")
            if not isinstance(batch, list) or type(pages) is not int or pages > 100 or pages < 0 or data.get("page") != page:
                raise ValueError("Incomplete analytics user roster")
            for user in batch:
                identifier = user.get("user_id")
                if not isinstance(identifier, str) or not identifier or identifier in seen:
                    raise ValueError("Invalid analytics user roster")
                seen.add(identifier)
                await asyncio.to_thread(store.remember_user, identifier, user.get("user_email") or "", "litellm")
            if page >= pages:
                return
    raise ValueError("Analytics roster scan exceeded safety bound")


async def refresh_all() -> None:
    try:
        await discover_users()
    except Exception:
        _logger.warning("Analytics user discovery failed; refreshing previously known users")
    semaphore = asyncio.Semaphore(settings.analytics_batch_concurrency)

    async def one(user_id):
        async with semaphore:
            await refresh_user(user_id)

    await asyncio.gather(*(one(user_id) for user_id in await asyncio.to_thread(store.users)))


async def run() -> None:
    while True:
        started = monotonic()
        try:
            await refresh_all()
        except Exception:
            _logger.exception("Hourly analytics aggregation failed")
        await asyncio.sleep(max(0, 3600 - (monotonic() - started)))
