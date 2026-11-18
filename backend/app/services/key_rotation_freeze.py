"""Stop a managed key's spend before an enforced rotation copies it.

Enforced organization budgets keep consumed spend on the member's key. A
replacement starts from the old key's spend, so the old key must stop taking
requests first and LiteLLM's batched spend writes must land before the copy.
"""

import asyncio

from fastapi import HTTPException

from app.config import settings
from app.services import litellm

MARK = "litegate_rotation_freeze"
# LiteLLM batches spend writes (about every 10 seconds by default).
SETTLE_SECONDS = 12.0
_RESTORED = ("blocked", "metadata")
active: set[str] = set()


def _token(key: dict) -> str | None:
    return key.get("token") or key.get("api_key") or key.get("key")


def frozen(key: dict) -> bool:
    metadata = key.get("metadata")
    return isinstance(metadata, dict) and isinstance(metadata.get(MARK), dict)


def original(key: dict) -> dict:
    """The key as it was before this rotation froze it."""
    if not frozen(key):
        return key
    before = key["metadata"][MARK].get("before") or {}
    return {**{name: value for name, value in key.items() if name not in _RESTORED}, **before}


def _managed(key: dict) -> bool:
    return settings.organization_hierarchy.is_managed_team(key.get("team_id"))


async def freeze(user_id: str, keys: list[dict]) -> bool:
    """Block managed keys, remembering their prior state. True when any was frozen."""
    froze = False
    for key in keys:
        token = _token(key)
        if not token or not _managed(key):
            continue
        froze = True
        if frozen(key):
            continue  # Interrupted earlier; its spend has long settled.
        before = {name: key[name] for name in _RESTORED if name in key}
        metadata = {**(key.get("metadata") or {}), MARK: {"before": before}}
        await litellm.update_key(token, {"blocked": True, "metadata": metadata})
        info = await litellm.get_key_info(token)
        if not info or info.get("user_id") != user_id or not info.get("blocked") or not frozen(info):
            await thaw(user_id, [{**key, "metadata": metadata}])
            raise HTTPException(status_code=502, detail="Could not pause the old key before replacing it; it was kept unchanged")
    return froze


async def thaw(user_id: str, keys: list[dict] | None = None) -> None:
    """Restore keys a rotation froze, leaving everything else untouched."""
    keys = await litellm.list_user_keys(user_id) if keys is None else keys
    for key in keys:
        token = _token(key)
        if not token:
            continue
        if not frozen(key):
            info = await litellm.get_key_info(token)
            if not info or not frozen(info):
                continue
            key = info
        before = original(key)
        await litellm.update_key(token, {"blocked": bool(before.get("blocked")), "metadata": before.get("metadata") or {}})


async def recover(user_id: str, keys: list[dict]) -> list[dict]:
    """Unblock keys left frozen by an interrupted rotation (for example a restart)."""
    if user_id in active or not any(frozen(key) for key in keys):
        return keys
    await thaw(user_id, [key for key in keys if frozen(key)])
    return [original(key) for key in keys]


async def settle() -> None:
    await asyncio.sleep(SETTLE_SECONDS)
