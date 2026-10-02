"""Organization views built from verified identities and LiteLLM daily aggregates."""

import asyncio
from datetime import date, datetime, timedelta, timezone
from time import monotonic

from fastapi import HTTPException

from app.config import settings
from app.services import organization_client as upstream, organization_store as store
from app.services.organization_sync import resolve

_usage_cache: dict[tuple[str, str, str], tuple[float, list[dict]]] = {}


async def identities() -> tuple[list[tuple[dict, object]], list[dict]]:
    values, errors = [], []
    for identity in await asyncio.to_thread(store.list_identities):
        try:
            node = resolve(identity["user_id"], identity["groups"])
            if node:
                values.append((identity, node))
            else:
                errors.append({"user_id": identity["user_id"], "error": "No current organization mapping"})
            if identity.get("sync_error"):
                errors.append({"user_id": identity["user_id"], "error": identity["sync_error"]})
        except HTTPException as exc:
            errors.append({"user_id": identity["user_id"], "error": str(exc.detail)})
    return values, errors


def selected_nodes(node_id: str | None):
    tree = settings.organization_hierarchy
    if node_id and node_id not in tree.nodes:
        raise HTTPException(status_code=404, detail="Organization group not found")
    return tree.nodes.get(node_id)


def within(node, ancestor) -> bool:
    return ancestor is None or node.path[: len(ancestor.path)] == ancestor.path


async def overview() -> dict:
    tree = settings.organization_hierarchy
    records, errors = await identities()
    semaphore = asyncio.Semaphore(5)

    async def root_status(root):
        async with semaphore:
            try:
                info = await upstream.team_info(root.team_id)
                team = info.get("team_info", {})
                policy = {"max_budget": root.member.budget.groupTotal, "budget_duration": root.member.budget.duration}
                mismatch = any(team.get(key) != value for key, value in policy.items())
                return root.team_id, {
                    "spend": upstream.finite_number(team.get("spend")),
                    "error": "LiteLLM's top-level budget differs from organizationHierarchy" if mismatch else None,
                }
            except HTTPException as exc:
                return root.team_id, {"spend": None, "error": str(exc.detail)}

    roots = dict(await asyncio.gather(*(root_status(root) for root in tree.roots)))
    groups = []
    for node in tree.nodes.values():
        root = next(root for root in tree.roots if root.team_id == node.team_id)
        status = roots[node.team_id]
        groups.append(
            {
                "id": node.id,
                "name": node.member.name,
                "level": node.level,
                "path": list(node.path),
                "parent_id": node.parent_id,
                "team_id": node.team_id,
                "members": sum(within(member, node) for _, member in records),
                "per_user": node.per_user,
                "duration": node.duration,
                "budget_source": node.budget_source,
                "group_total": root.member.budget.groupTotal,
                "group_spend": status["spend"],
                "sync_error": status["error"],
            }
        )
    return {
        "enabled": bool(tree.levels),
        "levels": [level.name for level in tree.levels],
        "groups": groups,
        "total_users": len(records),
        "issues": errors,
    }


async def users(node_id: str | None, page: int, size: int) -> dict:
    ancestor = selected_nodes(node_id)
    records, _ = await identities()
    selected = [(identity, node) for identity, node in records if within(node, ancestor)]
    batch = selected[(page - 1) * size : page * size]
    semaphore = asyncio.Semaphore(5)

    async def get_info(team_id):
        async with semaphore:
            try:
                return team_id, await upstream.team_info(team_id)
            except HTTPException:
                return team_id, None

    infos = dict(await asyncio.gather(*(get_info(team_id) for team_id in {node.team_id for _, node in batch})))
    result = []
    for identity, node in batch:
        info = infos[node.team_id]
        member = upstream.membership(info, identity["user_id"]) if info else None
        result.append(
            {
                "user_id": identity["user_id"],
                "email": identity["email"],
                "path": list(node.path),
                "per_user": node.per_user,
                "duration": node.duration,
                "budget_spend": upstream.finite_number(member.get("spend")) if member else None,
                "sync_error": identity.get("sync_error") or ("Could not read the user's LiteLLM membership" if member is None else None),
            }
        )
    return {"users": result, "page": page, "page_size": size, "total": len(selected), "total_pages": max(1, (len(selected) + size - 1) // size)}


async def cached_usage(user_id: str, start: str, end: str) -> list[dict]:
    key = (user_id, start, end)
    now = monotonic()
    cached = _usage_cache.get(key)
    if cached and now - cached[0] < 60:
        return cached[1]
    rows = await upstream.daily_usage(user_id, start, end)
    if len(_usage_cache) >= 1000:
        _usage_cache.clear()
    _usage_cache[key] = (now, rows)
    return rows


def zero_metrics() -> dict:
    return {"spend": 0.0, "tokens": 0, "requests": 0}


def add_metrics(target: dict, source: dict) -> None:
    target["spend"] += upstream.finite_number(source.get("spend"))
    target["tokens"] += upstream.finite_number(source.get("total_tokens"), integer=True)
    target["requests"] += upstream.finite_number(source.get("api_requests"), integer=True)


async def usage(node_id: str | None, start: date, end: date) -> dict:
    if end < start or (end - start).days > 90 or end > datetime.now(timezone.utc).date():
        raise HTTPException(status_code=422, detail="Select a past or current date range of at most 90 days")
    ancestor = selected_nodes(node_id)
    records, issues = await identities()
    selected = [(identity, node) for identity, node in records if within(node, ancestor)]
    if len(selected) > 500:
        raise HTTPException(status_code=422, detail="Select a smaller group; one report supports at most 500 users")
    semaphore = asyncio.Semaphore(8)

    async def fetch(identity, node):
        async with semaphore:
            return node, await cached_usage(identity["user_id"], start.isoformat(), end.isoformat())

    tasks = [asyncio.create_task(fetch(identity, node)) for identity, node in selected]
    try:
        batches = await asyncio.gather(*tasks)
    except BaseException:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise
    daily = {(start + timedelta(days=offset)).isoformat(): zero_metrics() for offset in range((end - start).days + 1)}
    total, by_group, by_model = zero_metrics(), {}, {}
    for node, rows in batches:
        depth = ancestor.level + 1 if ancestor else 0
        child = node
        while child.level > depth:
            child = settings.organization_hierarchy.nodes[child.parent_id]
        group_id = child.id if child.level == depth else None
        group_name = child.member.name if group_id is not None else "Direct members"
        group = by_group.setdefault(group_id, {"id": group_id, "name": group_name, **zero_metrics()})
        for row in rows:
            if not isinstance(row, dict):
                raise HTTPException(status_code=502, detail="LiteLLM returned an invalid daily usage aggregate")
            day = row.get("date")
            if day not in daily or not isinstance(row.get("metrics"), dict):
                raise HTTPException(status_code=502, detail="LiteLLM returned an invalid daily usage aggregate")
            metrics = row["metrics"]
            for target in (daily[day], total, group):
                add_metrics(target, metrics)
            breakdown = row.get("breakdown") or {}
            if not isinstance(breakdown, dict):
                raise HTTPException(status_code=502, detail="LiteLLM returned an invalid model usage aggregate")
            models = breakdown.get("models") or {}
            if not isinstance(models, dict):
                raise HTTPException(status_code=502, detail="LiteLLM returned an invalid model usage aggregate")
            for model, values in models.items():
                if not isinstance(values, dict) or not isinstance(values.get("metrics", values), dict):
                    raise HTTPException(status_code=502, detail="LiteLLM returned an invalid model usage aggregate")
                add_metrics(by_model.setdefault(model, zero_metrics()), values.get("metrics", values))
    return {
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "totals": total,
        "daily": [{"date": day, **values} for day, values in daily.items()],
        "by_group": list(by_group.values()),
        "by_model": [{"name": name, **values} for name, values in by_model.items()],
        "users": len(selected),
        "attribution": "current_membership",
        "issues": issues,
    }
