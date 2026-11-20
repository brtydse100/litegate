"""Organization views built from verified identities and LiteLLM daily aggregates."""

import asyncio
from datetime import date, datetime, timedelta, timezone
from time import monotonic

from fastapi import HTTPException

from app.config import settings
from app.services import litellm, litellm_snapshot, organization_client as upstream, organization_store as store, organization_discovery as discovery
from app.services.organization_sync import resolve_identity
from app.services.organization_access import GLOBAL_SCOPE, OrganizationScope

_usage_cache: dict[tuple, tuple[float, list[dict]]] = {}
# Team status on the overview, reused for a minute; failures are not kept.
_status_cache: dict[str, tuple[float, dict]] = {}
USAGE_TEAM_BATCH = 50


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


MAX_SELECTED_GROUPS = 50


def selected_ancestors(node_ids: str | list[str] | None, scope: OrganizationScope = GLOBAL_SCOPE) -> list:
    """Groups a report covers (none means every visible group); each is scope-checked."""
    ids = [node_ids] if node_ids is None or isinstance(node_ids, str) else node_ids
    ids = list(dict.fromkeys(node_id for node_id in ids if node_id))
    if len(ids) > MAX_SELECTED_GROUPS or any(len(node_id) > 24 for node_id in ids):
        raise HTTPException(status_code=422, detail=f"Select at most {MAX_SELECTED_GROUPS} groups")
    return [selected_nodes(node_id, scope) for node_id in ids]


def within_any(node, ancestors: list) -> bool:
    return not ancestors or any(within(node, ancestor) for ancestor in ancestors)


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
    # One bulk team listing replaces a /team/info request per group. Teams it
    # omits, or listings without every field the status compares, fall back to
    # team info so a sparse listing never reports a false policy mismatch.
    try:
        listed = await litellm_snapshot.teams.get() if visible else {}
    except HTTPException:
        listed = {}

    def team_status(root, team: dict) -> dict:
        policy = {"max_budget": None, "budget_duration": root.duration}
        mismatch = any(team.get(key) != value for key, value in policy.items())
        return {
            "spend": upstream.finite_number(team.get("spend")),
            "error": "LiteLLM's team policy migration is pending" if mismatch else None,
        }

    async def root_status(root):
        team = listed.get(root.team_id)
        if team is not None and all(field in team for field in ("spend", "max_budget", "budget_duration")):
            return root.team_id, team_status(root, team)
        cached = _status_cache.get(root.team_id)
        if cached and monotonic() - cached[0] < 60:
            return root.team_id, cached[1]
        async with semaphore:
            try:
                info = await upstream.team_info(root.team_id)
                status = team_status(root, info.get("team_info", {}))
                if len(_status_cache) >= 5000:
                    _status_cache.clear()
                _status_cache[root.team_id] = (monotonic(), status)
                return root.team_id, status
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


async def users(node_id: str | list[str] | None, page: int, size: int, scope: OrganizationScope = GLOBAL_SCOPE) -> dict:
    ancestors = selected_ancestors(node_id, scope)
    records, _ = await identities(scope)
    selected = [(identity, node) for identity, node in records if within_any(node, ancestors)]
    batch = selected[(page - 1) * size : page * size]
    semaphore = asyncio.Semaphore(5)
    # Spend for the page comes from one shared key listing when available.
    # An empty page needs no listing at all.
    try:
        owners = await litellm_snapshot.keys_by_user.get() if batch else {}
    except HTTPException:
        owners = None

    async def get_info(user_id):
        if owners is not None:
            return user_id, owners.get(user_id, [])
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


async def cached_team_usage(team_ids: tuple[str, ...], start: str, end: str) -> list[dict]:
    key = (team_ids, start, end)
    now = monotonic()
    cached = _usage_cache.get(key)
    if cached and now - cached[0] < 60:
        return cached[1]
    rows = await upstream.team_daily_usage(list(team_ids), start, end)
    validate_usage(rows, start, end)
    if len(_usage_cache) >= 1000:
        _usage_cache.clear()
    _usage_cache[key] = (now, rows)
    return rows


def key_entries(breakdown: dict, *, model: str | None = None) -> list[tuple[str, dict]]:
    """(owner, metrics) per key from a team activity breakdown."""
    source = breakdown.get("api_keys") if model is None else (breakdown.get("models") or {}).get(model, {}).get("api_key_breakdown")
    if source is None:
        return []
    if not isinstance(source, dict):
        raise HTTPException(status_code=502, detail="LiteLLM returned an invalid per-key usage aggregate")
    entries = []
    for entry in source.values():
        metadata = entry.get("metadata") if isinstance(entry, dict) else None
        if not isinstance(metadata, dict) or not isinstance(entry.get("metrics"), dict):
            raise HTTPException(status_code=502, detail="LiteLLM returned an invalid per-key usage aggregate")
        owner = metadata.get("user_id")
        if isinstance(owner, str) and owner:
            entries.append((owner, entry["metrics"]))
    return entries


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


async def usage(node_id: str | list[str] | None, start: date, end: date, scope: OrganizationScope = GLOBAL_SCOPE) -> dict:
    """Usage of the selected members across every managed team.

    LiteLLM aggregates per team, one request for up to 50 teams, and attributes
    each key's usage to its owner, so members are counted wherever their keys
    were (including a previous group). Usage of keys outside managed teams is
    not part of the organization report.
    """
    if end < start or (end - start).days > 90 or end > datetime.now(timezone.utc).date():
        raise HTTPException(status_code=422, detail="Select a past or current date range of at most 90 days")
    ancestors = selected_ancestors(node_id, scope)
    ancestor = ancestors[0] if len(ancestors) == 1 else None
    records, issues = await identities(scope)
    selected = [(identity, node) for identity, node in records if within_any(node, ancestors)]
    if len(selected) > 5000:
        raise HTTPException(status_code=422, detail="Select a smaller group; one report supports at most 5000 users")
    teams = sorted({node.team_id for node in settings.organization_hierarchy.nodes.values()})
    batches = [tuple(teams[index : index + USAGE_TEAM_BATCH]) for index in range(0, len(teams), USAGE_TEAM_BATCH)]
    semaphore = asyncio.Semaphore(4)

    async def fetch(batch):
        async with semaphore:
            return await cached_team_usage(batch, start.isoformat(), end.isoformat())

    tasks = [asyncio.create_task(fetch(batch)) for batch in batches]
    try:
        results = await asyncio.gather(*tasks)
    except BaseException:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise
    daily = {(start + timedelta(days=offset)).isoformat(): zero_metrics() for offset in range((end - start).days + 1)}
    total, by_group, by_model, by_user = zero_metrics(), {}, {}, []
    members, groups = {}, {}
    for identity, node in selected:
        member = {"id": identity["user_id"], "name": identity.get("email") or identity["user_id"], **zero_metrics()}
        by_user.append(member)
        root = scope.root_for(node)
        # One group breaks down by its children; several compare side by side.
        depth = (
            ancestor.level + 1
            if ancestor
            else min(item.level for item in ancestors)
            if ancestors
            else root.level
            if root is not None and not scope.global_admin
            else 0
        )
        child = node
        while child.level > depth:
            child = settings.organization_hierarchy.nodes[child.parent_id]
        group_id = child.id if child.level == depth else None
        group_name = child.member.name if group_id is not None else "Direct members"
        members[identity["user_id"]] = member
        groups[identity["user_id"]] = by_group.setdefault(group_id, {"id": group_id, "name": group_name, **zero_metrics()})
    for rows in results:
        for row in rows:
            day = row.get("date")
            breakdown = row.get("breakdown") or {}
            if day not in daily or not isinstance(breakdown, dict):
                raise HTTPException(status_code=502, detail="LiteLLM returned an invalid daily usage aggregate")
            for owner, metrics in key_entries(breakdown):
                if owner in members:
                    for target in (daily[day], total, groups[owner], members[owner]):
                        add_metrics(target, metrics)
            for model in breakdown.get("models") or {}:
                for owner, metrics in key_entries(breakdown, model=model):
                    if owner in members:
                        add_metrics(by_model.setdefault(model, zero_metrics()), metrics)
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
