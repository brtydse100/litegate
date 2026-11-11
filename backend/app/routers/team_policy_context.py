"""Configuration ownership metadata shared by team management endpoints."""

from app.config import settings


def team_config_references(team_id: str) -> tuple[list[str], bool]:
    mapped_groups: list[str] = []
    for group, configured in settings.oidc_group_team_mapping.items():
        team_ids = [configured] if isinstance(configured, str) else configured
        if team_id in team_ids:
            mapped_groups.append(group)
    return mapped_groups, settings.key_team_id == team_id


def decorate_team(team: dict) -> dict:
    team_id = str(team.get("team_id") or "")
    mapped_groups, default_key_team = team_config_references(team_id)
    return {
        **team,
        "mapped_groups": mapped_groups,
        "default_key_team": default_key_team,
        "organization_managed": settings.organization_hierarchy.is_managed_team(team_id),
    }
