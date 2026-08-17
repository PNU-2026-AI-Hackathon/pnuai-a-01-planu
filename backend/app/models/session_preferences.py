"""Session-scoped, resolved timetable constraints and preferences.

These models are durable domain state stored on ``PlanuSessionState`` after
free-text preferences have been interpreted and reconciled with uploaded course
catalogs. Course constraints intentionally use ``course_id`` values, not course
names, and do not contain LLM trace, warnings, raw output, or parser metadata.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from .course import Day, time_to_minutes


CourseId = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


def _deduplicate(values: list) -> list:
    return list(dict.fromkeys(values))


class HardConstraints(BaseModel):
    """Resolved hard constraints that candidate generation must satisfy.

    Unlike ``HardPreferenceConditions`` in ``preference.py``, this model is not
    an LLM/input DTO. Any course-name preferences must be resolved against the
    active catalog before values are stored here as course ids.
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    required_free_days: list[Day] = Field(default_factory=list)
    earliest_start_time: str | None = None
    latest_end_time: str | None = None
    min_credit: float | None = Field(default=None, ge=0)
    max_credit: float | None = Field(default=None, ge=0)
    required_course_ids: list[CourseId] = Field(default_factory=list)
    excluded_course_ids: list[CourseId] = Field(default_factory=list)

    @field_validator("earliest_start_time", "latest_end_time")
    @classmethod
    def validate_time(cls, value: str | None) -> str | None:
        if value is not None:
            time_to_minutes(value)
        return value

    @field_validator(
        "required_free_days",
        "required_course_ids",
        "excluded_course_ids",
    )
    @classmethod
    def remove_duplicates(cls, values: list) -> list:
        return _deduplicate(values)

    @model_validator(mode="after")
    def validate_constraints(self) -> "HardConstraints":
        if self.min_credit is not None and self.max_credit is not None and self.min_credit > self.max_credit:
            raise ValueError("min_credit must not exceed max_credit")
        if (
            self.earliest_start_time is not None
            and self.latest_end_time is not None
            and time_to_minutes(self.earliest_start_time)
            >= time_to_minutes(self.latest_end_time)
        ):
            raise ValueError("earliest_start_time must be earlier than latest_end_time")

        overlap = set(self.required_course_ids) & set(self.excluded_course_ids)
        if overlap:
            course_ids = ", ".join(sorted(overlap))
            raise ValueError(f"course ids cannot be both required and excluded: {course_ids}")
        return self


class SoftPreferences(BaseModel):
    """Resolved soft preferences used for ranking without filtering candidates.

    This is session state, not the LLM parsing layer. Course preferences are
    stored only after ambiguous course names and divisions have been resolved to
    concrete ``course_id`` values.
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    preferred_free_days: list[Day] = Field(default_factory=list)
    preferred_earliest_start_time: str | None = None
    preferred_latest_end_time: str | None = None
    preferred_course_ids: list[CourseId] = Field(default_factory=list)
    disliked_course_ids: list[CourseId] = Field(default_factory=list)
    compact_schedule: bool | None = None

    @field_validator("preferred_earliest_start_time", "preferred_latest_end_time")
    @classmethod
    def validate_time(cls, value: str | None) -> str | None:
        if value is not None:
            time_to_minutes(value)
        return value

    @field_validator(
        "preferred_free_days",
        "preferred_course_ids",
        "disliked_course_ids",
    )
    @classmethod
    def remove_duplicates(cls, values: list) -> list:
        return _deduplicate(values)

    @model_validator(mode="after")
    def validate_preferences(self) -> "SoftPreferences":
        if (
            self.preferred_earliest_start_time is not None
            and self.preferred_latest_end_time is not None
            and time_to_minutes(self.preferred_earliest_start_time)
            >= time_to_minutes(self.preferred_latest_end_time)
        ):
            raise ValueError(
                "preferred_earliest_start_time must be earlier than "
                "preferred_latest_end_time"
            )

        overlap = set(self.preferred_course_ids) & set(self.disliked_course_ids)
        if overlap:
            course_ids = ", ".join(sorted(overlap))
            raise ValueError(f"course ids cannot be both preferred and disliked: {course_ids}")
        return self
