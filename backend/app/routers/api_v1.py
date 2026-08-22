"""Stable automation API for users and virtual-key management."""

import asyncio
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from app.config import settings
from app.models import (
    ApiKeyCreateRequest,
    BulkKeyUpdateRequest,
    KeyCreateResponse,
    KeyDeleteRequest,
    TeamCreateRequest,
    TeamMemberMoveRequest,
    TeamUpdateRequest,
)
from app.rate_limit import check_key_rate_limit
from app.routers.api_actor import (
    ApiActor,
    get_api_actor,
    record_audit as _record_audit,
    require_api_admin as _require_api_admin,
)
from app.routers.api_v1_system import api_audit_events, api_status, router as system_router
from app.routers.api_v1_users import api_create_user, api_list_users, api_update_user, router as users_router
from app.services import litellm as llm

router = APIRouter(prefix="/v1", tags=["api-v1"])
router.include_router(system_router)
router.include_router(users_router)


def _team_config_references(team_id: str) -> tuple[list[str], bool]:
    mapped_groups: list[str] = []
    for group, configured in settings.oidc_group_team_mapping.items():
        team_ids = [configured] if isinstance(configured, str) else configured
        if team_id in team_ids:
            mapped_groups.append(group)
    return mapped_groups, settings.key_team_id == team_id


def _decorate_team(team: dict) -> dict:
    team_id = str(team.get("team_id") or "")
    mapped_groups, default_key_team = _team_config_references(team_id)
    return {
        **team,
        "mapped_groups": mapped_groups,
        "default_key_team": default_key_team,
    }

@router.get("/me")
async def api_me(actor: ApiActor = Depends(get_api_actor)):
    return {
        "user_id": actor.user.user_id,
        "email": actor.user.email,
        "role": actor.user.role,
        "auth_source": actor.user.auth_source,
        "team_ids": actor.user.team_ids,
    }


@router.get("/keys")
async def api_list_keys(
    all_keys: bool = Query(default=False, alias="all"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=100),
    search: str = Query(default="", max_length=128),
    team_id: str = Query(default="", max_length=128),
    blocked: Optional[bool] = Query(default=None),
    actor: ApiActor = Depends(get_api_actor),
):
    if all_keys:
        _require_api_admin(actor)
        return await llm.list_keys_filtered(
            page=page,
            size=size,
            search=search,
            team_id=team_id,
            blocked=blocked,
        )
    if actor.proof_key:
        info = await llm.get_key_info(actor.proof_key)
        return {"keys": [info] if info else []}
    if actor.user.user_id == "api:management":
        raise HTTPException(status_code=400, detail="Use ?all=true with a management API key")
    return {"keys": await llm.list_user_keys(actor.user.user_id)}


@router.get("/keys/identifiers")
async def api_list_key_identifiers(
    actor: ApiActor = Depends(get_api_actor),
    search: str = Query(default="", max_length=128),
    team_id: str = Query(default="", max_length=128),
    blocked: Optional[bool] = Query(default=None),
):
    """List every key identifier for the administrator select-all control."""
    _require_api_admin(actor)
    keys = await llm.list_key_identifiers(search=search, team_id=team_id, blocked=blocked)
    return {"keys": keys, "total": len(keys)}


@router.post("/keys", response_model=KeyCreateResponse, status_code=status.HTTP_201_CREATED)
async def api_create_key(
    payload: Optional[ApiKeyCreateRequest] = None,
    actor: ApiActor = Depends(get_api_actor),
):
    if actor.proof_key:
        raise HTTPException(status_code=403, detail="A LiteLLM key cannot create another key")
    requested_user_id = payload.user_id if payload else None
    requested_email = payload.email if payload else None
    if requested_user_id and not actor.is_admin:
        raise HTTPException(status_code=403, detail="Only admins can create keys for another user")
    user_id = requested_user_id or actor.user.user_id
    email = requested_email or actor.user.email
    if user_id == "api:management":
        raise HTTPException(status_code=422, detail="user_id is required for management API calls")
    check_key_rate_limit(actor.user.user_id)
    if await llm.list_user_keys(user_id):
        raise HTTPException(status_code=409, detail="This user already has a key")
    is_self_service = not requested_user_id or requested_user_id == actor.user.user_id
    team_id = actor.user.team_ids[0] if is_self_service and actor.user.team_ids else None
    result = await llm.generate_key(user_id, email, team_id)
    if actor.is_admin:
        await _record_audit(
            actor,
            "key.create",
            user_id,
            details={"for_another_user": bool(requested_user_id and requested_user_id != actor.user.user_id)},
        )
    return KeyCreateResponse(
        key=result["key"], user_id=result.get("user_id", user_id), expires=result.get("expires")
    )


@router.delete("/keys")
async def api_delete_key(payload: KeyDeleteRequest, actor: ApiActor = Depends(get_api_actor)):
    """Delete a key while keeping the credential out of URLs and access logs."""
    if actor.proof_key:
        if payload.key != actor.proof_key:
            raise HTTPException(status_code=403, detail="A LiteLLM key can only delete itself")
    elif not actor.is_admin:
        owned = {
            key.get("token") or key.get("api_key") or key.get("key")
            for key in await llm.list_user_keys(actor.user.user_id)
        }
        if payload.key not in owned:
            raise HTTPException(status_code=403, detail="Key not owned by user")
    check_key_rate_limit(actor.user.user_id)
    await llm.delete_key(payload.key)
    if actor.is_admin:
        await _record_audit(actor, "key.delete", "installation-key")
    return {"deleted": True}


@router.patch("/keys/bulk")
async def bulk_update_keys(
    payload: BulkKeyUpdateRequest,
    actor: ApiActor = Depends(get_api_actor),
):
    """Apply one settings change to multiple keys. Administrator access is required."""
    _require_api_admin(actor)
    check_key_rate_limit(actor.user.user_id)

    changes = payload.settings.model_dump(exclude_unset=True)
    semaphore = asyncio.Semaphore(10)

    async def update_one(key: str) -> dict:
        async with semaphore:
            try:
                await llm.update_key(key, changes)
                return {"key": key, "updated": True}
            except HTTPException as exc:
                return {"key": key, "updated": False, "error": str(exc.detail)}
            except Exception:
                return {"key": key, "updated": False, "error": "Unexpected update failure"}

    results = await asyncio.gather(*(update_one(key) for key in payload.keys))
    updated = sum(1 for result in results if result["updated"])
    failed = len(results) - updated
    await _record_audit(
        actor,
        "keys.bulk_update",
        "installation-keys",
        outcome="failure" if failed else "success",
        details={
            "keys": payload.keys,
            "setting_fields": sorted(changes),
            "updated": updated,
            "failed": failed,
        },
    )
    return {"updated": updated, "failed": failed, "results": results}


@router.get("/teams")
async def api_list_teams(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=25, ge=1, le=100),
    search: str = Query(default="", max_length=128),
    actor: ApiActor = Depends(get_api_actor),
):
    """List a bounded page of LiteLLM teams. Administrator access is required."""
    _require_api_admin(actor)
    result = await llm.list_teams(page=page, page_size=size, search=search.strip())
    result["teams"] = [_decorate_team(team) for team in result["teams"] if isinstance(team, dict)]
    return result


@router.post("/teams", status_code=status.HTTP_201_CREATED)
async def api_create_team(payload: TeamCreateRequest, actor: ApiActor = Depends(get_api_actor)):
    """Create a LiteLLM team with core budget and access policy."""
    _require_api_admin(actor)
    check_key_rate_limit(actor.user.user_id)
    created = await llm.create_team(payload.model_dump(exclude_none=True))
    await _record_audit(actor, "team.create", str(created.get("team_id") or payload.team_id or payload.team_alias), details={"setting_fields": sorted(payload.model_fields_set)})
    return _decorate_team(created)


@router.patch("/teams/{team_id}")
async def api_update_team(
    team_id: Annotated[str, Path(min_length=1, max_length=128)],
    payload: TeamUpdateRequest,
    actor: ApiActor = Depends(get_api_actor),
):
    """Update a LiteLLM team's core budget and access policy."""
    _require_api_admin(actor)
    check_key_rate_limit(actor.user.user_id)
    updated = await llm.update_team(team_id, payload.model_dump(exclude_unset=True))
    await _record_audit(actor, "team.update", team_id, details={"setting_fields": sorted(payload.model_fields_set)})
    return _decorate_team(updated)


@router.delete("/teams/{team_id}")
async def api_delete_team(
    team_id: Annotated[str, Path(min_length=1, max_length=128)],
    actor: ApiActor = Depends(get_api_actor),
):
    """Delete a team and its team-scoped keys after configuration safeguards."""
    _require_api_admin(actor)
    mapped_groups, default_key_team = _team_config_references(team_id)
    references = []
    if mapped_groups:
        references.append(f"SSO groups: {', '.join(mapped_groups)}")
    if default_key_team:
        references.append("KEY_TEAM_ID")
    if references:
        raise HTTPException(
            status_code=409,
            detail=f"Remove this team from LiteGate configuration before deleting it ({'; '.join(references)})",
        )
    check_key_rate_limit(actor.user.user_id)
    await llm.delete_team(team_id)
    await _record_audit(actor, "team.delete", team_id)
    return {"deleted": True, "team_id": team_id}


@router.post("/teams/{source_team_id}/members/move")
async def api_move_team_member(
    source_team_id: Annotated[str, Path(min_length=1, max_length=128)],
    payload: TeamMemberMoveRequest,
    actor: ApiActor = Depends(get_api_actor),
):
    """Move a member and their source-team keys to another LiteLLM team."""
    _require_api_admin(actor)
    if source_team_id == payload.destination_team_id:
        raise HTTPException(status_code=422, detail="Source and destination teams must be different")

    mapped_groups, default_key_team = _team_config_references(source_team_id)
    references = []
    if mapped_groups:
        references.append(f"SSO groups: {', '.join(mapped_groups)}")
    if default_key_team:
        references.append("KEY_TEAM_ID")
    if references:
        raise HTTPException(
            status_code=409,
            detail=f"This team is configuration-managed; remove its reference before moving members ({'; '.join(references)})",
        )

    source_team = await llm.get_team(source_team_id)
    if source_team is None:
        raise HTTPException(status_code=404, detail="Source team not found")
    destination_team = await llm.get_team(payload.destination_team_id)
    if destination_team is None:
        raise HTTPException(status_code=404, detail="Destination team not found")

    source_member = next(
        (
            member
            for member in source_team.get("members_with_roles", [])
            if isinstance(member, dict) and member.get("user_id") == payload.user_id
        ),
        None,
    )
    if source_member is None:
        raise HTTPException(status_code=404, detail="User is not a member of the source team")

    check_key_rate_limit(actor.user.user_id)
    destination_members = destination_team.get("members_with_roles", [])
    already_in_destination = any(
        isinstance(member, dict) and member.get("user_id") == payload.user_id
        for member in destination_members
    )
    if not already_in_destination:
        await llm.add_team_member(
            team_id=payload.destination_team_id,
            user_id=payload.user_id,
            role=source_member.get("role") if source_member.get("role") in {"user", "admin"} else "user",
        )

    try:
        moved_keys = await llm.move_user_team_keys(
            user_id=payload.user_id,
            source_team_id=source_team_id,
            destination_team_id=payload.destination_team_id,
        )
    except HTTPException as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=f"Destination membership is ready, but key migration did not finish. Source membership was kept. {exc.detail}",
        ) from exc

    try:
        await llm.remove_team_member(source_team_id, payload.user_id)
    except HTTPException as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail="Keys and destination membership moved, but source membership removal failed. Retry the move or remove the source membership in LiteLLM.",
        ) from exc
    await _record_audit(
        actor,
        "team.member_move",
        payload.user_id,
        details={
            "source_team_id": source_team_id,
            "destination_team_id": payload.destination_team_id,
            "keys_moved": moved_keys,
        },
    )
    return {
        "moved": True,
        "user_id": payload.user_id,
        "source_team_id": source_team_id,
        "destination_team_id": payload.destination_team_id,
        "keys_moved": moved_keys,
        "destination_membership_existed": already_in_destination,
    }
