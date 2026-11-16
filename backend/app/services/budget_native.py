"""Native aggregate-budget adapter; strict activation requires verified guarantees."""

import asyncio

from fastapi import HTTPException

from app.services import budget_allocations as allocation, budget_store as store, organization_client as upstream

LIMITATIONS = [
    "Atomic request-cost reservations across team and aggregate member budgets have not been verified for this deployment.",
    "Aligned reset boundaries and retained spend across membership transfers have not been verified.",
    "Fail-closed enforcement for token-unknown, image, audio, and batch requests has not been verified.",
]


async def capabilities() -> dict:
    version = None
    try:
        info = await upstream.request("GET", "/health/readiness")
        raw = info.get("litellm_version", info.get("version"))
        if isinstance(raw, str) and len(raw) <= 80:
            version = raw
    except HTTPException:
        pass
    # A version string or successful management write does not prove inference
    # reservations, license availability, transfer accounting, or reset semantics.
    return {"supported": False, "version": version, "reasons": list(LIMITATIONS)}


async def require_capability() -> None:
    capability = await capabilities()
    if not capability["supported"]:
        raise HTTPException(503, {"message": "Strict hierarchical budget activation is unavailable", "capability": capability})


async def read_amount(target: dict) -> int | None:
    info = await upstream.team_info(target["team_id"])
    if target.get("user_id"):
        member = upstream.membership(info, target["user_id"])
        if member is None or not isinstance(member.get("litellm_budget_table"), dict):
            raise HTTPException(502, "Could not verify native aggregate member budget")
        record = member["litellm_budget_table"]
    else:
        record = info.get("team_info")
    if not isinstance(record, dict) or "max_budget" not in record:
        raise HTTPException(502, "Could not verify native budget")
    return allocation.units(record["max_budget"]) if record["max_budget"] is not None else None


async def write_amount(target: dict) -> None:
    payload = {"team_id": target["team_id"]}
    if target.get("user_id"):
        payload.update(user_id=target["user_id"], max_budget_in_team=allocation.dollars(target["amount"]))
        path = "/team/member_update"
    else:
        payload["max_budget"] = allocation.dollars(target["amount"])
        path = "/team/update"
    # Never reset spend or change period boundaries as a side effect of a cap edit.
    await upstream.request("POST", path, payload=payload)


async def apply_pending(revision: int) -> bool:
    """Internal journal executor, not activation. Stop on uncertainty before raises.

    Production activation intentionally cannot reach this adapter until a
    deployment's supported request set and reset/transfer contracts are verified.
    Each retry rereads current caps; successful decreases remain in force.
    """
    if (await asyncio.to_thread(store.read))["revision"] != revision:
        raise HTTPException(409, "Budget revision changed before native application")
    targets = await asyncio.to_thread(store.pending, revision)
    try:
        current = [(target, await read_amount(target)) for target in targets]
        ordered = sorted(current, key=lambda item: item[1] is not None and item[0]["amount"] > item[1])
        for target, previous in ordered:
            if previous != target["amount"]:
                await write_amount(target)
            if await read_amount(target) != target["amount"]:
                raise HTTPException(502, "Native budget readback did not match")
            await asyncio.to_thread(store.mark, revision, target)
    except (HTTPException, TimeoutError):
        for pending in await asyncio.to_thread(store.pending, revision):
            await asyncio.to_thread(store.mark, revision, pending, error="Native budget application remains unverified; retry required")
        return False
    return True
