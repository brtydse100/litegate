"""Keep existing team metadata/default-member policy during Advanced updates."""

import copy
import math

from fastapi import HTTPException

from app.services import litellm, organization_client as upstream

MEMBER_FIELDS = {
    "team_member_budget": "max_budget",
    "team_member_rpm_limit": "rpm_limit",
    "team_member_tpm_limit": "tpm_limit",
    "team_member_budget_duration": "budget_duration",
}


async def update(team_id: str, changes: dict) -> dict:
    current = (await upstream.team_info(team_id)).get("team_info")
    if not current:
        raise HTTPException(status_code=404, detail="Team not found")
    forwarded = copy.deepcopy(changes)
    metadata = current.get("metadata")
    if isinstance(metadata, dict) and metadata:
        # LiteLLM's metadata-backed field conversion can otherwise replace the
        # existing metadata wholesale. This server-owned copy is never audited.
        forwarded["metadata"] = copy.deepcopy(metadata)
        if metadata.get("team_member_budget_id") and not any(field in changes for field in MEMBER_FIELDS):
            budget = current.get("team_member_budget_table")
            if not isinstance(budget, dict):
                raise HTTPException(status_code=503, detail="Cannot verify the existing member allowance; Advanced team update was not applied")
            for field, column in MEMBER_FIELDS.items():
                amount = budget.get(column)
                if isinstance(amount, (int, float)) and not isinstance(amount, bool) and math.isfinite(amount) and amount >= 0:
                    # Echo one unchanged limit so LiteLLM retains the existing
                    # budget association. Do not resend duration/reset windows.
                    forwarded[field] = amount
                    break
            else:
                raise HTTPException(
                    status_code=503, detail="Cannot safely preserve the member allowance; review it in LiteLLM before this Advanced update"
                )
    return await litellm.update_team(team_id, forwarded)
