"""Finish revoking undelivered credentials even when their request is cancelled."""

import asyncio
import logging

from app.services import litellm

_logger = logging.getLogger(__name__)


async def revoke_created_key(key: str) -> None:
    cleanup = asyncio.create_task(litellm.delete_key(key))
    while not cleanup.done():
        try:
            await asyncio.shield(cleanup)
        except asyncio.CancelledError:
            continue
        except Exception:
            break
    try:
        cleanup.result()
    except BaseException:
        _logger.exception("Could not revoke an undelivered credential")
