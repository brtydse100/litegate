import json

import httpx
from typing import Optional, List, Any
from fastapi import HTTPException
from app.config import settings


def _headers() -> dict:
    return {"Authorization": f"Bearer {settings.litellm_master_key}"}


def _transport_error(e: httpx.TransportError) -> None:
    raise HTTPException(status_code=503, detail=f"Cannot reach LiteLLM at {settings.litellm_url}")


async def get_user(user_id: str) -> Optional[dict]:
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{settings.litellm_url}/user/info",
                params={"user_id": user_id},
                headers=_headers(),
                timeout=10,
            )
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.json()
    except httpx.TransportError as e:
        _transport_error(e)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"LiteLLM returned {e.response.status_code}")


async def create_user(user_id: str, email: str) -> dict:
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{settings.litellm_url}/user/new",
                json={"user_id": user_id, "user_email": email},
                headers=_headers(),
                timeout=10,
            )
            r.raise_for_status()
            return r.json()
    except httpx.TransportError as e:
        _transport_error(e)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"LiteLLM returned {e.response.status_code}")


async def ensure_user_exists(user_id: str, email: str) -> Optional[dict]:
    """Check existence in one call; create only if missing. Returns None if LiteLLM unreachable."""
    try:
        user = await get_user(user_id)
        if user is not None:
            return user
        return await create_user(user_id, email)
    except Exception:
        return None


async def list_user_team_ids(user_id: str) -> List[str]:
    """Return LiteLLM teams the user already belongs to."""
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{settings.litellm_url}/team/list",
                params={"user_id": user_id},
                headers=_headers(),
                timeout=10,
            )
            r.raise_for_status()
            data = r.json()
            if isinstance(data, dict):
                teams = data.get("teams") or data.get("data") or []
            else:
                teams = data
            if not isinstance(teams, list):
                return []
            result: List[str] = []
            seen: set[str] = set()
            for team in teams:
                team_id = team.get("team_id") if isinstance(team, dict) else None
                if team_id is not None:
                    normalized = str(team_id).strip()
                    if normalized and normalized not in seen:
                        seen.add(normalized)
                        result.append(normalized)
            return result
    except httpx.TransportError as e:
        _transport_error(e)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"LiteLLM returned {e.response.status_code}")


def _is_duplicate_team_member_response(response: httpx.Response) -> bool:
    if response.status_code != 400:
        return False
    try:
        detail = json.dumps(response.json()).casefold()
    except (ValueError, TypeError):
        detail = response.text.casefold()
    normalized = " ".join(detail.replace("_", " ").split())
    return (
        "team member already in team" in normalized
        or "already in team" in normalized
        or "already exists in team" in normalized
        or "already a member of" in normalized
    )


async def add_user_to_team(user_id: str, email: str, team_id: str) -> dict:
    # Match by the stable LiteLLM user ID only. Supplying both ID and email can
    # make LiteLLM resolve the same member twice on some versions.
    member: dict[str, str] = {"role": "user", "user_id": user_id}
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{settings.litellm_url}/team/member_add",
                json={"team_id": team_id, "member": member},
                headers=_headers(),
                timeout=10,
            )
            if _is_duplicate_team_member_response(r):
                return {"already_member": True, "team_id": team_id}
            r.raise_for_status()
            return r.json()
    except httpx.TransportError as e:
        _transport_error(e)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"LiteLLM returned {e.response.status_code}")


async def sync_user_team_memberships(user_id: str, email: str, team_ids: List[str]) -> None:
    """Add missing mapped memberships without deleting manually managed memberships."""
    existing = set(await list_user_team_ids(user_id))
    for team_id in team_ids:
        if team_id not in existing:
            await add_user_to_team(user_id, email, team_id)


async def generate_key(user_id: str, email: str = "", team_id: Optional[str] = None) -> dict:
    name = email.split("@")[0] if email else user_id.split(":")[-1]
    payload: dict[str, Any] = {"user_id": user_id, "key_alias": f"{name}'s key"}
    if settings.key_max_budget is not None:
        payload["max_budget"] = settings.key_max_budget
    if settings.key_budget_duration:
        payload["budget_duration"] = settings.key_budget_duration
    if settings.key_models_list:
        payload["models"] = settings.key_models_list
    if settings.key_tpm_limit is not None:
        payload["tpm_limit"] = settings.key_tpm_limit
    if settings.key_rpm_limit is not None:
        payload["rpm_limit"] = settings.key_rpm_limit
    if settings.key_duration:
        payload["duration"] = settings.key_duration
    effective_team_id = team_id or settings.key_team_id
    if effective_team_id:
        payload["team_id"] = effective_team_id

    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{settings.litellm_url}/key/generate",
                json=payload,
                headers=_headers(),
                timeout=10,
            )
            r.raise_for_status()
            return r.json()
    except httpx.TransportError as e:
        _transport_error(e)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"LiteLLM returned {e.response.status_code}")


async def delete_key(key: str) -> dict:
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{settings.litellm_url}/key/delete",
                json={"keys": [key]},
                headers=_headers(),
                timeout=10,
            )
            r.raise_for_status()
            return r.json()
    except httpx.TransportError as e:
        _transport_error(e)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"LiteLLM returned {e.response.status_code}")


async def list_user_keys(user_id: str) -> List[dict]:
    user = await get_user(user_id)
    if user is None:
        return []
    return user.get("keys", [])


async def list_keys(page: int = 1, size: int = 50, user_id: Optional[str] = None) -> dict:
    """Return one bounded page from LiteLLM's key-management endpoint."""
    params: dict[str, Any] = {
        "page": page,
        "size": size,
        "return_full_object": "true",
    }
    if user_id:
        params["user_id"] = user_id
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{settings.litellm_url}/key/list",
                params=params,
                headers=_headers(),
                timeout=10,
            )
            r.raise_for_status()
            data = r.json()
            if isinstance(data, list):
                keys = data
                total = len(data)
                total_pages = 1
            else:
                keys = data.get("keys") or data.get("data") or []
                total = data.get("total_count", data.get("total", len(keys)))
                total_pages = data.get("total_pages") or max(1, (int(total) + size - 1) // size)
            return {
                "keys": keys,
                "page": data.get("current_page", page) if isinstance(data, dict) else page,
                "size": size,
                "total": total,
                "total_pages": total_pages,
            }
    except httpx.TransportError as e:
        _transport_error(e)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"LiteLLM returned {e.response.status_code}")


async def get_key_info(key: str) -> Optional[dict]:
    """Validate a virtual key and return its metadata."""
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{settings.litellm_url}/key/info",
                params={"key": key},
                headers=_headers(),
                timeout=10,
            )
            if r.status_code in {401, 403, 404}:
                return None
            r.raise_for_status()
            data = r.json()
            return data.get("info", data) if isinstance(data, dict) else None
    except httpx.TransportError as e:
        _transport_error(e)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"LiteLLM returned {e.response.status_code}")


async def update_key(key: str, settings_update: dict) -> dict:
    """Update one virtual key through LiteLLM's management API."""
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{settings.litellm_url}/key/update",
                json={"key": key, **settings_update},
                headers=_headers(),
                timeout=10,
            )
            r.raise_for_status()
            return r.json()
    except httpx.TransportError as e:
        _transport_error(e)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"LiteLLM returned {e.response.status_code}")


async def get_spend_logs(
    user_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 100,
) -> List[dict]:
    params: dict = {"user_id": user_id, "limit": limit}
    if start_date:
        params["start_date"] = start_date
    if end_date:
        params["end_date"] = end_date

    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{settings.litellm_url}/spend/logs",
                params=params,
                headers=_headers(),
                timeout=15,
            )
            r.raise_for_status()
            data = r.json()
            return data if isinstance(data, list) else data.get("data", [])
    except httpx.TransportError as e:
        _transport_error(e)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"LiteLLM returned {e.response.status_code}")
