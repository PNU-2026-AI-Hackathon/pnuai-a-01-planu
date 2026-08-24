"""Pydantic schemas shared by PlaNU agent session tools."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..models import Day, HardConstraints, PlanuSessionState, SelectedTimetable, SoftPreferences, time_to_minutes
from ..services.session_update_models import (
    HardConstraintsUpdate,
    SessionProfileUpdate,
    SoftPreferencesUpdate,
)


class SessionToolErrorCode(str, Enum):
    """Stable error codes returned by session state tools."""

    SESSION_NOT_AVAILABLE = "SESSION_NOT_AVAILABLE"
    INVALID_VALUE = "INVALID_VALUE"
    CONFLICTING_CONSTRAINT = "CONFLICTING_CONSTRAINT"
    INTERNAL_TOOL_ERROR = "INTERNAL_TOOL_ERROR"
    TIMETABLE_GENERATION_NOT_READY = "TIMETABLE_GENERATION_NOT_READY"
    TIMETABLE_CONDITIONS_NOT_CONFIRMED = "TIMETABLE_CONDITIONS_NOT_CONFIRMED"


class SessionToolError(BaseModel):
    """Structured error details for failed tool calls."""

    model_config = ConfigDict(extra="forbid")

    code: SessionToolErrorCode
    message: str = Field(min_length=1)
    field: str | None = None
    value: str | None = None


class SessionStateSummary(BaseModel):
    """Compact session state for agent planning without full course payloads."""

    model_config = ConfigDict(extra="forbid")

    session_id: str
    department: str | None
    major_catalog_id: str | None
    elective_catalog_id: str | None
    selected_major_course_ids: list[str]
    hard_constraints: HardConstraints
    soft_preferences: SoftPreferences
    selected_timetable: SelectedTimetable | None = None
    selected_timetable_status: str | None = None
    generation_preferences_confirmed_at: datetime | None = None
    generation_preferences_confirmed_version: int | None = None
    missing_information: list[str]
    updated_at: datetime
    expires_at: datetime

    @classmethod
    def from_state(cls, state: PlanuSessionState) -> "SessionStateSummary":
        missing_information: list[str] = []
        if state.department is None:
            missing_information.append("department")
        if state.major_catalog_id is None:
            missing_information.append("major_catalog_id")
        if not state.selected_major_course_ids:
            missing_information.append("selected_major_course_ids")
        return cls(
            session_id=state.session_id,
            department=state.department,
            major_catalog_id=state.major_catalog_id,
            elective_catalog_id=state.elective_catalog_id,
            selected_major_course_ids=list(state.selected_major_course_ids),
            hard_constraints=state.hard_constraints,
            soft_preferences=state.soft_preferences,
            selected_timetable=(
                None
                if state.selected_timetable is None
                else state.selected_timetable.model_copy(deep=True)
            ),
            selected_timetable_status=(
                None
                if state.selected_timetable_status is None
                else state.selected_timetable_status.value
            ),
            generation_preferences_confirmed_at=state.generation_preferences_confirmed_at,
            generation_preferences_confirmed_version=state.generation_preferences_confirmed_version,
            missing_information=missing_information,
            updated_at=state.updated_at,
            expires_at=state.expires_at,
        )


class SessionToolResult(BaseModel):
    """Common result envelope for all agent session tools."""

    model_config = ConfigDict(extra="forbid")

    success: bool
    message: str
    session_id: str | None = None
    changed: bool = False
    changed_fields: list[str] = Field(default_factory=list)
    state_summary: SessionStateSummary | None = None
    hard_constraints: HardConstraints | None = None
    soft_preferences: SoftPreferences | None = None
    selected_major_course_ids: list[str] | None = None
    selected_timetable: SelectedTimetable | None = None
    selected_timetable_status: str | None = None
    error: SessionToolError | None = None


class _ToolInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )


class SessionIdInput(_ToolInput):
    """Input for tools that need only a live session id."""

    session_id: str = Field(min_length=1)


class DepartmentInput(SessionIdInput):
    """Input for setting the user's department."""

    department: str = Field(min_length=1)


class TextValueInput(SessionIdInput):
    """Backward-compatible input for setting a plain text session field."""

    value: str = Field(min_length=1)


class CatalogInput(SessionIdInput):
    """Input for storing a parsed catalog identifier."""

    catalog_id: str = Field(min_length=1)


class CourseIdInput(SessionIdInput):
    """Input for changing one resolved course id."""

    course_id: str = Field(min_length=1)


class CourseIdsInput(SessionIdInput):
    """Input for replacing resolved course id lists."""

    course_ids: list[str]

    @field_validator("course_ids")
    @classmethod
    def validate_course_ids(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("course_ids must not contain empty ids")
        return values


class DayInput(SessionIdInput):
    """Input for changing one weekday value."""

    day: Day


class DaysInput(SessionIdInput):
    """Input for replacing weekday lists."""

    days: list[Day]


class TimeInput(SessionIdInput):
    """Input for setting a HH:MM time value."""

    time: str = Field(min_length=1)

    @field_validator("time")
    @classmethod
    def validate_time(cls, value: str) -> str:
        time_to_minutes(value)
        return value


class BoolPreferenceInput(SessionIdInput):
    """Input for setting a boolean soft preference."""

    value: bool


ProfileClearField = Literal["department", "major_catalog_id", "elective_catalog_id"]
CourseUpdateMode = Literal["replace", "add", "remove"]
HardClearField = Literal[
    "required_free_days",
    "earliest_start_time",
    "latest_end_time",
    "required_course_ids",
    "excluded_course_ids",
    "min_credit",
    "max_credit",
]
SoftClearField = Literal[
    "preferred_free_days",
    "preferred_earliest_start_time",
    "preferred_latest_end_time",
    "preferred_course_ids",
    "disliked_course_ids",
    "compact_schedule",
]
ResetPreferenceTarget = Literal["hard", "soft", "all"]


class UpdateSessionProfileInput(SessionIdInput):
    """Input for updating session profile fields in one agent tool call."""

    department: str | None = Field(
        default=None,
        min_length=1,
        description="Resolved department name to store. Omit or use null to leave unchanged.",
    )
    major_catalog_id: str | None = Field(
        default=None,
        min_length=1,
        description="Parsed major catalog identifier. Omit or use null to leave unchanged.",
    )
    elective_catalog_id: str | None = Field(
        default=None,
        min_length=1,
        description="Parsed elective catalog identifier. Omit or use null to leave unchanged.",
    )
    clear_fields: list[ProfileClearField] = Field(
        default_factory=list,
        description="Profile fields to explicitly clear. Null values alone never clear fields.",
    )

    def to_service_update(self) -> SessionProfileUpdate:
        return SessionProfileUpdate(
            department=self.department,
            major_catalog_id=self.major_catalog_id,
            elective_catalog_id=self.elective_catalog_id,
            clear_fields=tuple(dict.fromkeys(self.clear_fields)),
        )


class UpdateSelectedMajorCoursesInput(SessionIdInput):
    """Input for updating selected major course ids in one call."""

    course_ids: list[str] = Field(
        description="Resolved course_id values only; do not pass natural-language course names.",
    )
    mode: CourseUpdateMode = Field(
        default="replace",
        description="replace overwrites the list, add appends missing ids, remove deletes ids idempotently.",
    )

    @field_validator("course_ids")
    @classmethod
    def validate_course_ids(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("course_ids must not contain empty ids")
        return values


class HardConstraintsPatch(_ToolInput):
    """Patch for replacing or clearing hard timetable constraint fields."""

    required_free_days: list[Day] | None = Field(default=None)
    earliest_start_time: str | None = Field(default=None)
    latest_end_time: str | None = Field(default=None)
    required_course_ids: list[str] | None = Field(default=None)
    excluded_course_ids: list[str] | None = Field(default=None)
    excluded_elective_areas: list[int] | None = Field(default=None)
    min_credit: float | None = Field(default=None, ge=0, description="완성된 시간표 전체의 최소 총학점")
    max_credit: float | None = Field(default=None, ge=0, description="완성된 시간표 전체의 최대 총학점")
    clear_fields: list[HardClearField] = Field(default_factory=list)

    @field_validator("earliest_start_time", "latest_end_time")
    @classmethod
    def validate_time(cls, value: str | None) -> str | None:
        if value is not None:
            time_to_minutes(value)
        return value

    @field_validator("required_course_ids", "excluded_course_ids")
    @classmethod
    def validate_course_ids(cls, values: list[str] | None) -> list[str] | None:
        if values is not None and any(not value.strip() for value in values):
            raise ValueError("course id lists must not contain empty ids")
        return values

    @field_validator("excluded_elective_areas")
    @classmethod
    def validate_excluded_elective_areas(cls, values: list[int] | None) -> list[int] | None:
        if values is not None and any(not 1 <= value <= 7 for value in values):
            raise ValueError("elective areas must be between 1 and 7")
        return values

    def to_service_update(self) -> HardConstraintsUpdate:
        return HardConstraintsUpdate(
            required_free_days=self.required_free_days,
            earliest_start_time=self.earliest_start_time,
            latest_end_time=self.latest_end_time,
            required_course_ids=self.required_course_ids,
            excluded_course_ids=self.excluded_course_ids,
            excluded_elective_areas=self.excluded_elective_areas,
            min_credit=self.min_credit,
            max_credit=self.max_credit,
            clear_fields=tuple(dict.fromkeys(self.clear_fields)),
        )


class SoftPreferencesPatch(_ToolInput):
    """Patch for replacing or clearing soft timetable preference fields."""

    preferred_free_days: list[Day] | None = Field(default=None)
    preferred_earliest_start_time: str | None = Field(default=None)
    preferred_latest_end_time: str | None = Field(default=None)
    preferred_course_ids: list[str] | None = Field(default=None)
    disliked_course_ids: list[str] | None = Field(default=None)
    compact_schedule: bool | None = Field(default=None)
    clear_fields: list[SoftClearField] = Field(default_factory=list)

    @field_validator("preferred_earliest_start_time", "preferred_latest_end_time")
    @classmethod
    def validate_time(cls, value: str | None) -> str | None:
        if value is not None:
            time_to_minutes(value)
        return value

    @field_validator("preferred_course_ids", "disliked_course_ids")
    @classmethod
    def validate_course_ids(cls, values: list[str] | None) -> list[str] | None:
        if values is not None and any(not value.strip() for value in values):
            raise ValueError("course id lists must not contain empty ids")
        return values

    def to_service_update(self) -> SoftPreferencesUpdate:
        return SoftPreferencesUpdate(
            preferred_free_days=self.preferred_free_days,
            preferred_earliest_start_time=self.preferred_earliest_start_time,
            preferred_latest_end_time=self.preferred_latest_end_time,
            preferred_course_ids=self.preferred_course_ids,
            disliked_course_ids=self.disliked_course_ids,
            compact_schedule=self.compact_schedule,
            clear_fields=tuple(dict.fromkeys(self.clear_fields)),
        )


class UpdateTimetablePreferencesInput(SessionIdInput):
    """Input for one atomic Hard/Soft timetable preference patch."""

    hard: HardConstraintsPatch | None = Field(
        default=None,
        description="Hard constraint replacements or explicit clears. Hard wins over Soft.",
    )
    soft: SoftPreferencesPatch | None = Field(
        default=None,
        description="Soft preference replacements or explicit clears after course ids are resolved.",
    )

    @model_validator(mode="after")
    def validate_has_patch(self) -> "UpdateTimetablePreferencesInput":
        if self.hard is None and self.soft is None:
            raise ValueError("hard or soft patch is required")
        return self


class ResetSessionPreferencesInput(SessionIdInput):
    """Input for resetting Hard, Soft, or all timetable preferences."""

    target: ResetPreferenceTarget = Field(
        description="hard clears only constraints, soft clears only preferences, all clears both.",
    )

