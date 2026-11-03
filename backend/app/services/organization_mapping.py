"""Validate and resolve the optional email organization hierarchy."""

import json
import re
from functools import lru_cache
from pathlib import Path

from app.config import settings

_EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_BACKEND = Path(__file__).resolve().parents[2]


@lru_cache(maxsize=8)
def _snapshot(inline_json: str, filename: str):
    return load_mapping(json.loads(inline_json), filename)


def get_mapping():
    """Share the validated file snapshot between startup and login."""
    return _snapshot(json.dumps(settings.organization_mapping), settings.organization_mapping_file)


def normalize_email(value):
    if not isinstance(value, str) or not _EMAIL.fullmatch(value.strip()):
        raise ValueError("Invalid organization member email")
    return value.strip().casefold()


class OrganizationMapping:
    def __init__(self, groups):
        self.groups = groups
        self.by_team = {group["team_id"]: name for name, group in groups.items()}

    def referenced_team_ids(self):
        return list(self.by_team)

    def member_emails(self):
        return list(dict.fromkeys(email for group in self.groups.values() for email in group["members"]))

    def team_ids(self, email, sso_team_ids):
        email = email.strip().casefold() if isinstance(email, str) else ""
        direct = [name for name, group in self.groups.items() if email in group["members"]]

        def depth(name):
            count = 0
            while self.groups[name]["parent"]:
                count += 1
                name = self.groups[name]["parent"]
            return count

        direct.sort(key=depth, reverse=True)
        result = list(dict.fromkeys(sso_team_ids))
        for name in direct:
            team = self.groups[name]["team_id"]
            if team not in result:
                result.append(team)
        for team in list(result):
            name = self.by_team.get(team)
            while name and self.groups[name]["parent"]:
                name = self.groups[name]["parent"]
                ancestor = self.groups[name]["team_id"]
                if ancestor not in result:
                    result.append(ancestor)
        return result


def _group_definitions(data: dict) -> dict:
    """Normalize named levels without changing parent-based inheritance."""
    if not isinstance(data, dict):
        raise ValueError("Organization mapping must be an object")
    if "levels" not in data:
        if set(data) - {"groups"} or not isinstance(data.get("groups", {}), dict):
            raise ValueError("Invalid organization mapping")
        return data.get("groups", {})
    if set(data) != {"levels"} or not isinstance(data["levels"], list):
        raise ValueError("Use levels or legacy groups, not both")
    groups = {}
    level_names = set()
    for level in data["levels"]:
        if not isinstance(level, dict) or set(level) != {"name", "groups"}:
            raise ValueError("Each organization level requires name and groups")
        name = level["name"]
        if not isinstance(name, str) or not name.strip() or name.strip().casefold() in level_names:
            raise ValueError("Organization level names must be nonempty and unique")
        if not isinstance(level["groups"], dict):
            raise ValueError("Organization level groups must be an object")
        if groups.keys() & level["groups"].keys():
            raise ValueError("Organization group names must be unique across levels")
        level_names.add(name.strip().casefold())
        groups.update(level["groups"])
    return groups


def load_mapping(inline, filename):
    if not isinstance(inline, dict):
        raise ValueError("Organization mapping must be an object")
    if filename:
        if inline:
            raise ValueError("Only one organization mapping source may be configured")
        path = Path(filename)
        if not path.is_absolute():
            path = _BACKEND / path
        try:
            inline = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ValueError("Cannot read organization mapping JSON") from exc
    definitions = _group_definitions(inline)
    groups = {}
    teams = set()
    for name, raw in definitions.items():
        if not isinstance(name, str) or not name.strip() or not isinstance(raw, dict) or set(raw) - {"team_id", "parent", "members"}:
            raise ValueError("Invalid organization group")
        team = raw.get("team_id")
        parent = raw.get("parent")
        members = raw.get("members", [])
        if not isinstance(team, str) or not team.strip() or team.strip() in teams:
            raise ValueError("Invalid or duplicate team ID")
        if parent is not None and (not isinstance(parent, str) or not parent):
            raise ValueError("Invalid parent")
        if not isinstance(members, list):
            raise ValueError("Members must be a list")
        teams.add(team.strip())
        groups[name] = {"team_id": team.strip(), "parent": parent, "members": list(dict.fromkeys(normalize_email(m) for m in members))}
    for name in groups:
        seen = set()
        current = name
        while current:
            if current in seen or current not in groups:
                raise ValueError("Missing parent or cyclic organization hierarchy")
            seen.add(current)
            current = groups[current]["parent"]
    return OrganizationMapping(groups)
