"""Installation-wide scheduled team budget windows (nightly; BerriAI/litellm#54147).

One schedule is shared by every team: each team only chooses its amount per
window, or none for unlimited in that window. LiteLLM stores a window as a team
``budget_limits`` entry with a ``schedule`` and names it by a derived label;
the rules here mirror LiteLLM's so a configuration it would reject never starts.
"""

import re
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Weekday = Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
WEEKDAYS: tuple[str, ...] = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
SCHEDULE_PREFIX = "sched:"
_DAY = 24 * 60
_WEEK = 7 * _DAY


def _minutes(value: str) -> int:
    hours, minutes = value.split(":")
    return int(hours) * 60 + int(minutes)


def _format_days(days: list[str]) -> str:
    """ "Every day", "Mon-Fri" or "Mon, Sat", matching the admin UI."""
    if len(days) == len(WEEKDAYS):
        return "Every day"
    indexes = [WEEKDAYS.index(day) for day in days]
    if len(indexes) >= 3 and indexes == list(range(indexes[0], indexes[-1] + 1)):
        return f"{days[0].title()}-{days[-1].title()}"
    return ", ".join(day.title() for day in days)


class BudgetWindow(BaseModel):
    """A recurring period identified by its days and hours, such as "Mon-Fri 08:00-13:00"."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    days: list[Weekday] = Field(default_factory=lambda: list(WEEKDAYS), min_length=1)
    start: str
    end: str

    @field_validator("days")
    @classmethod
    def ordered_days(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("days must list each weekday at most once")
        return [day for day in WEEKDAYS if day in value]

    @field_validator("start", "end")
    @classmethod
    def wall_time(cls, value: str) -> str:
        if not re.fullmatch(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]", value):
            raise ValueError("start and end are local 'HH:MM' times")
        return value

    @property
    def name(self) -> str:
        """The window's key in window_budgets, e.g. "Mon-Fri 08:00-13:00"."""
        return f"{_format_days(self.days)} {self.start}-{self.end}"

    def length(self) -> int:
        """Minutes per period; an end at or before the start wraps past midnight."""
        return (_minutes(self.end) - _minutes(self.start)) % _DAY or _DAY

    def weekly_intervals(self) -> list[tuple[int, int]]:
        intervals = []
        for day in self.days:
            start = WEEKDAYS.index(day) * _DAY + _minutes(self.start)
            end = start + self.length()
            intervals += [(start, end)] if end <= _WEEK else [(start, _WEEK), (0, end - _WEEK)]
        return intervals


class BudgetWindows(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    timezone: str
    windows: list[BudgetWindow] = Field(min_length=1, max_length=24)

    @field_validator("timezone")
    @classmethod
    def known_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"Unknown timezone '{value}'") from exc
        return value

    @model_validator(mode="after")
    def distinct_windows(self):
        intervals = sorted((start, end, window.name) for window in self.windows for start, end in window.weekly_intervals())
        for (_, first_end, first), (second_start, _, second) in zip(intervals, intervals[1:]):
            if second_start < first_end:
                raise ValueError(f"Budget windows overlap: {first} and {second}")
        return self

    def label(self, window: BudgetWindow) -> str:
        """The budget_duration LiteLLM derives for this window's schedule."""
        return f"{SCHEDULE_PREFIX}{self.timezone}:{','.join(window.days)}:{window.start}-{window.end}"

    def schedule(self, window: BudgetWindow) -> dict:
        return {"timezone": self.timezone, "days": list(window.days), "start": window.start, "end": window.end}

    def public(self) -> dict:
        return {
            "timezone": self.timezone,
            "windows": [{**window.model_dump(), "name": window.name, "label": self.label(window)} for window in self.windows],
        }
