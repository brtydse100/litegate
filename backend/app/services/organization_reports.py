"""Organization views built from verified identities and LiteLLM daily aggregates."""

import asyncio
from datetime import date, datetime, timedelta, timezone
from time import monotonic

from fastapi import HTTPException

from app.config import settings
from app.services import litellm, organization_client as upstream, organization_store as store, organization_discovery as discovery
from app.services.organization_sync import resolve_identity
from app.services.organization_access import GLOBAL_SCOPE, OrganizationScope

_usage_cache: dict[tuple[str, str, str], tuple[float, list[dict]]] = {}


async def identities(scope: OrganizationScope = GLOBAL_SCOPE) -> tuple[list[tuple[dict, object]], list[dict]]:
    values, errors = [], discovery.issues() if scope.global_admin else []
    for identity in await asyncio.to_thread(store.list_identities):
        try:
            node = resolve_identity(identity)
            if node and scope.allows(node):
                values.append((identity, node))
            elif scope.global_admin:
                errors.append({"user_id": identity["user_id"], "error": "No current organization mapping"})
            if identity.get("sync_error") and scope.global_admin:
                errors.append({"user_id": identity["user_id"], "error": identity["sync_error"]})
        except HTTPException as exc:
            if scope.global_admin:
                errors.append({"user_id": identity["user_id"], "error": str(exc.detail)})
    return values, errors


def selected_nodes(node_id: str | None, scope: OrganizationScope = GLOBAL_SCOPE):
    tree = settings.organization_hierarchy
    if node_id and (node_id not in tree.nodes or not scope.allows(tree.nodes[node_id])):
        raise HTTPException(status_code=404, detail="Organization group not found")
    return tree.nodes.get(node_id)


def within(node, ancestor) -> bool:
    return ancestor is None or node.path[: len(ancestor.path)] == ancestor.path


def node_metadata(node, records, scope: OrganizationScope = GLOBAL_SCOPE) -> dict:
    return {
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
        "group_total": node.member.budget.groupTotal,
        "has_children": any(child.parent_id == node.id for child in settings.organization_hierarchy.nodes.values()),
        **scope.metadata(node),
    }


async def children(parent_id: str | None, scope: OrganizationScope = GLOBAL_SCOPE) -> dict:
    selected_nodes(parent_id, scope)
    tree = settings.organization_hierarchy
    records, errors = await identities(scope)
    return {
        "enabled": bool(tree.levels),
        "levels": scope.levels(),
        "groups": [
            node_metadata(node, records, scope)
            for node in tree.nodes.values()
            if scope.allows(node) and (node.id in scope.roots if parent_id is None and not scope.global_admin else node.parent_id == parent_id)
        ],
        "total_users": len(records),
        "issues": errors,
    }


async def group_detail(node_id: str, scope: OrganizationScope = GLOBAL_SCOPE) -> dict:
    node = selected_nodes(node_id, scope)
    records, _ = await identities(scope)
    result = {**node_metadata(node, records, scope), "group_spend": None, "sync_error": None, "spend_scope": "team"}
    try:
        info = await upstream.team_info(node.team_id)
        team = info.get("team_info", {})
        result["group_spend"] = upstream.finite_number(team.get("spend"))
        if team.get("max_budget") is not None or team.get("budget_duration") != node.duration:
            result["sync_error"] = "LiteLLM's team policy migration is pending"
    except HTTPException as exc:
        result["sync_error"] = str(exc.detail) if scope.global_admin else "Could not read group status"
    return result


async def overview(scope: OrganizationScope = GLOBAL_SCOPE) -> dict:
    tree = settings.organization_hierarchy
    records, errors = await identities(scope)
    visible = [node for node in tree.nodes.values() if scope.allows(node)]
    semaphore = asyncio.Semaphore(5)

    async def root_status(root):
        async with semaphore:
            try:
                info = await upstream.team_info(root.team_id)
                team = info.get("team_info", {})
                policy = {"max_budget": None, "budget_duration": root.duration}
                mismatch = any(team.get(key) != value for key, value in policy.items())
                return root.team_id, {
                    "spend": upstream.finite_number(team.get("spend")),
                    "error": "LiteLLM's team policy migration is pending" if mismatch else None,
                }
            except HTTPException as exc:
                return root.team_id, {"spend": None, "error": str(exc.detail) if scope.global_admin else "Could not read group status"}

    roots = dict(await asyncio.gather(*(root_status(node) for node in visible)))
    groups = []
    for node in visible:
        statuses = [roots[descendant.team_id] for descendant in visible if within(descendant, node)]
        status = {
            "spend": sum(item["spend"] for item in statuses) if all(item["spend"] is not None for item in statuses) else None,
            "error": next((item["error"] for item in statuses if item["error"]), None),
        }
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
                "group_total": node.member.budget.groupTotal,
                "group_spend": status["spend"],
                "sync_error": status["error"],
                **scope.metadata(node),
            }
        )
    return {
        "enabled": bool(tree.levels),
        "levels": scope.levels(),
        "groups": groups,
        "total_users": len(records),
        "issues": errors,
    }


async def users(node_id: str | None, page: int, size: int, scope: OrganizationScope = GLOBAL_SCOPE) -> dict:
    ancestor = selected_nodes(node_id, scope)
    records, _ = await identities(scope)
    selected = [(identity, node) for identity, node in records if within(node, ancestor)]
    batch = selected[(page - 1) * size : page * size]
    semaphore = asyncio.Semaphore(5)

    async def get_info(user_id):
        async with semaphore:
            try:
                return user_id, await litellm.list_user_keys(user_id)
            except HTTPException:
                return user_id, None

    infos = dict(await asyncio.gather(*(get_info(identity["user_id"]) for identity, _ in batch)))
    result = []
    for identity, node in batch:
        keys = infos[identity["user_id"]]
        result.append(
            {
                "user_id": identity["user_id"],
                "email": identity["email"],
                "path": scope.path(node),
                "per_user": node.per_user,
                "duration": node.duration,
                "budget_spend": litellm.total_key_spend(keys) if keys is not None else None,
                "sync_error": (
                    identity.get("sync_error")
                    if scope.global_admin
                    else "Organization synchronization is pending"
                    if identity.get("sync_error")
                    else None
                )
                or ("Could not read the user's key metadata" if keys is None else None),
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
    validate_usage(rows, start, end)
    if len(_usage_cache) >= 1000:
        _usage_cache.clear()
    _usage_cache[key] = (now, rows)
    return rows


def zero_metrics() -> dict:
    return {"spend": 0.0, "tokens": 0, "requests": 0}


def metric_values(source: dict) -> dict:
    if not isinstance(source, dict):
        raise HTTPException(status_code=502, detail="LiteLLM returned invalid usage metrics")
    result = {}
    for source_key, target_key in (("spend", "spend"), ("total_tokens", "tokens"), ("api_requests", "requests")):
        value = source.get(source_key)
        if type(value) not in (int, float):
            raise HTTPException(status_code=502, detail="LiteLLM returned missing or invalid usage metrics")
        number = upstream.finite_number(value)
        if target_key != "spend" and number != int(number):
            raise HTTPException(status_code=502, detail="LiteLLM returned fractional usage counts")
        result[target_key] = number if target_key == "spend" else int(number)
    return result


def validate_usage(rows: list[dict], start: str, end: str) -> None:
    if not isinstance(rows, list):
        raise HTTPException(status_code=502, detail="LiteLLM returned an invalid daily usage aggregate")
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("date"), str) or not start <= row["date"] <= end:
            raise HTTPException(status_code=502, detail="LiteLLM returned an invalid daily usage aggregate")
        try:
            if date.fromisoformat(row["date"]).isoformat() != row["date"]:
                raise ValueError
        except ValueError as exc:
            raise HTTPException(status_code=502, detail="LiteLLM returned an invalid usage date") from exc
        metric_values(row.get("metrics"))
        breakdown = row.get("breakdown", {})
        if not isinstance(breakdown, dict) or not isinstance(breakdown.get("models", {}), dict):
            raise HTTPException(status_code=502, detail="LiteLLM returned an invalid model usage aggregate")
        for name, values in breakdown.get("models", {}).items():
            if not isinstance(name, str) or not name or not isinstance(values, dict):
                raise HTTPException(status_code=502, detail="LiteLLM returned an invalid model usage aggregate")
            metric_values(values.get("metrics", values))


def add_metrics(target: dict, source: dict) -> None:
    for key, value in metric_values(source).items():
        target[key] = upstream.finite_number(target[key] + value, integer=key != "spend")


async def usage(node_id: str | None, start: date, end: date, scope: OrganizationScope = GLOBAL_SCOPE) -> dict:
    if end < start or (end - start).days > 90 or end > datetime.now(timezone.utc).date():
        raise HTTPException(status_code=422, detail="Select a past or current date range of at most 90 days")
    ancestor = selected_nodes(node_id, scope)
    records, issues = await identities(scope)
    selected = [(identity, node) for identity, node in records if within(node, ancestor)]
    if len(selected) > 500:
        raise HTTPException(status_code=422, detail="Select a smaller group; one report supports at most 500 users")
    semaphore = asyncio.Semaphore(8)

    async def fetch(identity, node):
        async with semaphore:
            return identity, node, await cached_usage(identity["user_id"], start.isoformat(), end.isoformat())

    tasks = [asyncio.create_task(fetch(identity, node)) for identity, node in selected]
    try:
        batches = await asyncio.gather(*tasks)
    except BaseException:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise
    daily = {(start + timedelta(days=offset)).isoformat(): zero_metrics() for offset in range((end - start).days + 1)}
    total, by_group, by_model, by_user = zero_metrics(), {}, {}, []
    for identity, node, rows in batches:
        member = {"id": identity["user_id"], "name": identity.get("email") or identity["user_id"], **zero_metrics()}
        by_user.append(member)
        root = scope.root_for(node)
        depth = ancestor.level + 1 if ancestor else root.level if root is not None and not scope.global_admin else 0
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
            for target in (daily[day], total, group, member):
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
        "by_user": by_user,
        "by_model": [{"name": name, **values} for name, values in by_model.items()],
        "users": len(selected),
        "attribution": "current_membership",
        "issues": issues,
    }
