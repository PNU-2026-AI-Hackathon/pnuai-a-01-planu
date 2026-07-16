"""Validated rules produced from a user's natural-language preferences."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .course import Day, time_to_minutes


class PreferenceTemplate(str, Enum):
    """User-selected timetable direction used to tune ranking weights.

    Templates express the broad shape the user wants, while concrete
    ``PreferenceRules`` fields still hold the actual preference content.
    """

    REQUIRED_FREE_DAY = "required_free_day"
    PREFER_FREE_DAY = "prefer_free_day"
    MINIMIZE_ATTENDANCE_DAYS = "minimize_attendance_days"
    MINIMIZE_CONSECUTIVE_CLASSES = "minimize_consecutive_classes"
    COMPACT_SCHEDULE = "compact_schedule"


class PreferenceParseStatus(str, Enum):
    """High-level outcome of a natural-language preference parse."""

    SUCCESS = "success"
    FALLBACK = "fallback"
    SKIPPED = "skipped"


class PreferenceToolStatus(str, Enum):
    """Status for an observable parser tool/step."""

    STARTED = "started"
    SUCCESS = "success"
    ERROR = "error"
    SKIPPED = "skipped"


class PreferenceToolUsage(BaseModel):
    """A tool or parser capability used while interpreting preferences."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    name: str = Field(min_length=1)
    purpose: str = Field(min_length=1)
    status: PreferenceToolStatus
    metadata: dict[str, Any] = Field(default_factory=dict)


class PreferenceTraceEvent(BaseModel):
    """One inspectable trace event for LLM preference parsing."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    step: str = Field(min_length=1)
    tool: str = Field(min_length=1)
    status: PreferenceToolStatus
    message: str = Field(min_length=1)
    input: dict[str, Any] | None = None
    output: dict[str, Any] | None = None
    error: str | None = None


class TimeRange(BaseModel):
    """A time window attached to one weekday."""

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
    def validate_range(self) -> "TimeRange":
        if self.start_minutes >= self.end_minutes:
            raise ValueError("time range end must be later than start")
        return self

    @property
    def start_minutes(self) -> int:
        return time_to_minutes(self.start)

    @property
    def end_minutes(self) -> int:
        return time_to_minutes(self.end)


class ExcludedTimeRange(TimeRange):
    """Backward-compatible name for hard excluded time windows."""


class PreferenceRules(BaseModel):
    """Structured preference content for filtering and ranking.

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
    excluded_time_ranges: list[ExcludedTimeRange] = Field(default_factory=list)
    excluded_professors: list[str] = Field(default_factory=list)
    required_course_names: list[str] = Field(
        default_factory=list,
        description=(
            "Concrete course names explicitly stated by the user as hard "
            "requirements that must be included in the final timetable. "
            "Use this field for expressions such as '대학영어는 반드시 넣어줘' "
            "or '대학영어는 꼭 들어야 해'. Do not use this field for optional "
            "or soft preferences."
        ),
    )
    excluded_course_names: list[str] = Field(
        default_factory=list,
        description=(
            "Concrete course names explicitly stated by the user as hard "
            "negative constraints that must not appear in the final timetable. "
            "Use this field for expressions such as '절대 듣고 싶지 않아', "
            "'무조건 제외해줘', '포함하지 마', '넣지 마', or '있으면 안 돼'. "
            "Do not use avoided_course_names for these hard exclusion requests."
        ),
    )
    selected_templates: list[PreferenceTemplate] = Field(default_factory=list)
    max_consecutive_classes: int | None = Field(default=None, ge=1)

    # Soft ranking preferences
    preferred_first_class_time: str | None = None
    preferred_free_time_ranges: list[TimeRange] = Field(default_factory=list)
    preferred_free_days: list[Day] = Field(default_factory=list)
    preferred_elective_areas: list[int] = Field(default_factory=list)
    preferred_course_names: list[str] = Field(
        default_factory=list,
        description=(
            "Concrete course names explicitly stated by the user as positive soft "
            "preferences, not hard requirements. These courses should influence "
            "ranking but should not remove candidates when absent. Use this field "
            "for expressions such as '가능하면 대학영어를 듣고 싶어', "
            "'대학영어를 선호해', '대학영어가 시간표에 있으면 좋겠어', and "
            "'꼭 들어야 하는 것은 아니지만 대학영어를 듣고 싶어'. Do not leave "
            "this field empty when a concrete course name and a positive soft "
            "preference are both explicitly present. Do not include topics, "
            "general course characteristics, or invented course names."
        ),
    )
    avoided_course_names: list[str] = Field(
        default_factory=list,
        description=(
            "Concrete course names explicitly stated by the user as negative soft "
            "preferences, not hard exclusions. Use this field for expressions "
            "such as '가능하면 피하고 싶어', '다른 선택지가 있으면 피해줘', "
            "'별로 선호하지 않아', or '절대 제외할 정도는 아니야'. Do not use "
            "this field when the user strongly forbids the course."
        ),
    )
    minimize_attendance_days: bool = False
    minimize_consecutive_classes: bool = False
    compact_schedule: bool = False

    @field_validator(
        "earliest_start_time", "latest_end_time", "preferred_first_class_time"
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
        "excluded_professors",
        "selected_templates",
        "required_course_names",
        "excluded_course_names",
        "preferred_course_names",
        "avoided_course_names",
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
            PreferenceTemplate.MINIMIZE_ATTENDANCE_DAYS: "minimize_attendance_days",
            PreferenceTemplate.MINIMIZE_CONSECUTIVE_CLASSES: "minimize_consecutive_classes",
            PreferenceTemplate.COMPACT_SCHEDULE: "compact_schedule",
        }
        for template, field_name in template_flags.items():
            if template in self.selected_templates and not getattr(self, field_name):
                object.__setattr__(self, field_name, True)
        self._validate_course_name_conflicts()
        return self

    def _validate_course_name_conflicts(self) -> None:
        required = set(self.required_course_names)
        excluded = set(self.excluded_course_names)
        preferred = set(self.preferred_course_names)
        avoided = set(self.avoided_course_names)

        required_and_excluded = required & excluded
        if required_and_excluded:
            names = ", ".join(sorted(required_and_excluded))
            raise ValueError(f"course names cannot be both required and excluded: {names}")

        preferred_and_avoided = preferred & avoided
        if preferred_and_avoided:
            names = ", ".join(sorted(preferred_and_avoided))
            raise ValueError(f"course names cannot be both preferred and avoided: {names}")

        object.__setattr__(
            self,
            "preferred_course_names",
            [name for name in self.preferred_course_names if name not in required and name not in excluded],
        )
        object.__setattr__(
            self,
            "avoided_course_names",
            [name for name in self.avoided_course_names if name not in required and name not in excluded],
        )


class PreferenceParseResult(BaseModel):
    """Inspectable result of parsing free text into timetable preferences."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    status: PreferenceParseStatus
    llm_preferences: PreferenceRules = Field(default_factory=PreferenceRules)
    merged_preferences: PreferenceRules = Field(default_factory=PreferenceRules)
    used_tools: list[PreferenceToolUsage] = Field(default_factory=list)
    trace: list[PreferenceTraceEvent] = Field(default_factory=list)
    fallback_used: bool = False
    warnings: list[str] = Field(default_factory=list)
    raw_output: dict[str, Any] | str | None = None


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
