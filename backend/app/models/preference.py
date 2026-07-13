"""Validated rules produced from a user's natural-language preferences."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .course import Day, time_to_minutes


class PreferenceTemplate(str, Enum):
    """User-facing preference choices mapped to deterministic backend rules."""

    NO_MORNING_CLASSES = "no_morning_classes"
    PREFER_LATE_START = "prefer_late_start"
    REQUIRED_FREE_DAY = "required_free_day"
    PREFER_FREE_DAY = "prefer_free_day"
    MINIMIZE_ATTENDANCE_DAYS = "minimize_attendance_days"
    MINIMIZE_CONSECUTIVE_CLASSES = "minimize_consecutive_classes"
    COMPACT_SCHEDULE = "compact_schedule"


class ExcludedTimeRange(BaseModel):
    """A hard time window that no meeting may overlap."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    day: Day
    start: str
    end: str

    @field_validator("start", "end")
    @classmethod
    def validate_time(cls, value: str) -> str:
        time_to_minutes(value)
        return value

    @model_validator(mode="after")
    def validate_range(self) -> "ExcludedTimeRange":
        if self.start_minutes >= self.end_minutes:
            raise ValueError("excluded time range end must be later than start")
        return self

    @property
    def start_minutes(self) -> int:
        return time_to_minutes(self.start)

    @property
    def end_minutes(self) -> int:
        return time_to_minutes(self.end)


class PreferenceRules(BaseModel):
    """Structured, deterministic input for filtering and ranking.

    Every field has a safe default so an LLM parsing failure can fall back to an
    empty ``PreferenceRules`` instance as required by the backend design.
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    # Hard filters
    excluded_days: list[Day] = Field(default_factory=list)
    required_free_days: list[Day] = Field(default_factory=list)
    earliest_start_time: str | None = None
    latest_end_time: str | None = None
    no_morning_classes: bool = False
    excluded_time_ranges: list[ExcludedTimeRange] = Field(default_factory=list)
    excluded_professors: list[str] = Field(default_factory=list)
    preferred_elective_areas: list[int] = Field(default_factory=list)
    required_keywords: list[str] = Field(default_factory=list)
    excluded_keywords: list[str] = Field(default_factory=list)
    selected_templates: list[PreferenceTemplate] = Field(default_factory=list)

    # Soft ranking preferences
    preferred_free_days: list[Day] = Field(default_factory=list)
    avoid_morning_classes: bool = False
    morning_end_time: str = "10:00" # 아침 수업 기준을 10시로 설정
    prefer_late_start: bool = False
    minimize_attendance_days: bool = False
    minimize_consecutive_classes: bool = False
    compact_schedule: bool = False
    max_consecutive_classes: int | None = Field(default=None, ge=1)

    @field_validator(
        "earliest_start_time", "latest_end_time", "morning_end_time"
    )
    @classmethod
    def validate_time(cls, value: str | None) -> str | None:
        if value is not None:
            time_to_minutes(value)
        return value

    @field_validator("preferred_elective_areas")
    @classmethod
    def validate_areas(cls, values: list[int]) -> list[int]:
        if any(not 1 <= value <= 7 for value in values):
            raise ValueError("elective areas must be between 1 and 7")
        return list(dict.fromkeys(values))

    @field_validator(
        "excluded_days",
        "required_free_days",
        "preferred_free_days",
        "required_keywords",
        "excluded_keywords",
        "excluded_professors",
        "selected_templates",
    )
    @classmethod
    def remove_duplicates(cls, values: list) -> list:
        return list(dict.fromkeys(values))

    @model_validator(mode="after")
    def validate_ranges(self) -> "PreferenceRules":
        if (
            self.earliest_start_time is not None
            and self.latest_end_time is not None
            and time_to_minutes(self.earliest_start_time)
            >= time_to_minutes(self.latest_end_time)
        ):
            raise ValueError("latest_end_time must be later than earliest_start_time")
        template_flags = {
            PreferenceTemplate.NO_MORNING_CLASSES: "no_morning_classes",
            PreferenceTemplate.PREFER_LATE_START: "prefer_late_start",
            PreferenceTemplate.MINIMIZE_ATTENDANCE_DAYS: "minimize_attendance_days",
            PreferenceTemplate.MINIMIZE_CONSECUTIVE_CLASSES: "minimize_consecutive_classes",
            PreferenceTemplate.COMPACT_SCHEDULE: "compact_schedule",
        }
        for template, field_name in template_flags.items():
            if template in self.selected_templates and not getattr(self, field_name):
                object.__setattr__(self, field_name, True)
        return self


def merge_preference_rules(
    selected_preferences: PreferenceRules | None = None,
    llm_preferences: PreferenceRules | None = None,
    defaults: PreferenceRules | None = None,
) -> PreferenceRules:
    """Merge UI-selected rules, LLM additions, and defaults without double count.

    UI-selected values have priority over LLM output for the same field. The LLM
    is therefore additive: it can fill fields the UI did not explicitly set, but
    it cannot override a direct user choice.
    """

    base = (defaults or PreferenceRules()).model_dump()
    llm = llm_preferences or PreferenceRules()
    selected = selected_preferences or PreferenceRules()

    for field_name in PreferenceRules.model_fields:
        if field_name in llm.model_fields_set:
            base[field_name] = getattr(llm, field_name)
        if field_name in selected.model_fields_set:
            base[field_name] = getattr(selected, field_name)

    return PreferenceRules.model_validate(base)
