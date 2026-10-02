"""Validated, provider-independent organization configuration and inheritance."""

from dataclasses import dataclass
from functools import cached_property
from hashlib import sha256
import json
import re

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class OrganizationBudget(BaseModel):
    model_config = ConfigDict(extra="forbid")
    duration: str | None = None
    groupTotal: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    perUser: float | None = Field(default=None, ge=0, allow_inf_nan=False)

    @field_validator("duration")
    @classmethod
    def valid_duration(cls, value: str | None) -> str | None:
        if value is not None and not re.fullmatch(r"[1-9][0-9]*(?:s|m|h|d|mo)", value):
            raise ValueError("Budget duration must be positive, for example 30d or 1mo")
        return value


class OrganizationMember(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=128)
    litellmTeamId: str | None = Field(default=None, min_length=1, max_length=128)
    ssoGroups: list[str] = Field(default_factory=list, max_length=200)
    userIds: list[str] = Field(default_factory=list, max_length=200)
    budget: OrganizationBudget = Field(default_factory=OrganizationBudget)

    @field_validator("ssoGroups", "userIds")
    @classmethod
    def clean_matches(cls, values: list[str]) -> list[str]:
        if any(not value.strip() or len(value.strip()) > 256 for value in values):
            raise ValueError("Membership mappings must contain nonempty identifiers of at most 256 characters")
        return list(dict.fromkeys(value.strip() for value in values))


class OrganizationBundle(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    parent: str | None = Field(default=None, min_length=1, max_length=128)
    members: list[OrganizationMember] = Field(min_length=1, max_length=500)


class OrganizationLevel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=64)
    groups: list[OrganizationBundle] = Field(min_length=1, max_length=500)


@dataclass(frozen=True)
class OrganizationNode:
    id: str
    level: int
    member: OrganizationMember
    path: tuple[str, ...]
    parent_id: str | None
    team_id: str
    per_user: float | None
    duration: str | None
    budget_source: str | None


class MembershipConflict(ValueError):
    pass


class OrganizationHierarchy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    levels: list[OrganizationLevel] = Field(default_factory=list, max_length=8)

    @cached_property
    def nodes(self) -> dict[str, OrganizationNode]:
        result: dict[str, OrganizationNode] = {}
        previous: dict[str, OrganizationNode] = {}
        team_ids: set[str] = set()
        level_names: set[str] = set()
        for depth, level in enumerate(self.levels):
            if level.name.casefold() in level_names:
                raise ValueError(f"Duplicate organization level: {level.name}")
            level_names.add(level.name.casefold())
            current: dict[str, OrganizationNode] = {}
            for bundle in level.groups:
                parent = previous.get(bundle.parent) if bundle.parent else None
                if depth == 0 and bundle.parent is not None:
                    raise ValueError("Top-level groups cannot have a parent")
                if depth > 0 and parent is None:
                    raise ValueError(f"Unknown parent in the preceding level: {bundle.parent}")
                for member in bundle.members:
                    if member.name in current:
                        raise ValueError(f"Duplicate group name in {level.name}: {member.name}")
                    if parent and (member.litellmTeamId is not None or "groupTotal" in member.budget.model_fields_set):
                        raise ValueError("litellmTeamId and groupTotal are supported only on top-level groups")
                    if not parent and not member.litellmTeamId:
                        raise ValueError(f"Top-level group {member.name} requires litellmTeamId")
                    team_id = parent.team_id if parent else member.litellmTeamId
                    if not parent:
                        if team_id in team_ids:
                            raise ValueError("Each top-level group requires a distinct LiteLLM team ID")
                        team_ids.add(team_id)
                    path = (*parent.path, member.name) if parent else (member.name,)
                    node_id = sha256(json.dumps(path, ensure_ascii=False).encode()).hexdigest()[:24]
                    budget = member.budget
                    per_user = budget.perUser if "perUser" in budget.model_fields_set else parent.per_user if parent else None
                    duration = budget.duration if "duration" in budget.model_fields_set else parent.duration if parent else None
                    source = node_id if "perUser" in budget.model_fields_set else parent.budget_source if parent else None
                    node = OrganizationNode(node_id, depth, member, path, parent.id if parent else None, team_id, per_user, duration, source)
                    current[member.name] = node
                    result[node_id] = node
            previous = current
        if len(result) > 2000:
            raise ValueError("Organization hierarchy supports at most 2000 groups")
        return result

    @model_validator(mode="after")
    def validate_tree(self):
        # Also reject a single mapping that could never resolve to one path.
        matches: dict[tuple[str, str], list[OrganizationNode]] = {}
        for node in self.nodes.values():
            for kind, values in (("group", node.member.ssoGroups), ("user", node.member.userIds)):
                for value in values:
                    matches.setdefault((kind, value.casefold() if kind == "group" else value), []).append(node)
        for nodes in matches.values():
            self._compatible(nodes)
        return self

    @staticmethod
    def _compatible(matches: list[OrganizationNode]) -> OrganizationNode | None:
        if not matches:
            return None
        deepest = max(matches, key=lambda node: node.level)
        if any(deepest.path[: len(node.path)] != node.path for node in matches):
            raise MembershipConflict("Organization mappings conflict; each user must belong to one organizational path")
        return deepest

    def resolve(self, user_id: str, groups: list[str]) -> OrganizationNode | None:
        claimed = {group.strip().casefold() for group in groups}
        return self._compatible(
            [
                node
                for node in self.nodes.values()
                if user_id in node.member.userIds or claimed.intersection(group.casefold() for group in node.member.ssoGroups)
            ]
        )

    @property
    def roots(self) -> list[OrganizationNode]:
        return [node for node in self.nodes.values() if node.parent_id is None]

    def is_managed_team(self, team_id: str | None) -> bool:
        return bool(team_id) and any(root.team_id == team_id for root in self.roots)
