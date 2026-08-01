"""Pydantic schemas shared by PlaNU agent session tools."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..models import Day, HardConstraints, PlanuSessionState, SoftPreferences, time_to_minutes


class SessionToolErrorCode(str, Enum):
    """Stable error codes returned by session state tools."""

    SESSION_NOT_AVAILABLE = "SESSION_NOT_AVAILABLE"
    INVALID_VALUE = "INVALID_VALUE"
    CONFLICTING_CONSTRAINT = "CONFLICTING_CONSTRAINT"
    INTERNAL_TOOL_ERROR = "INTERNAL_TOOL_ERROR"


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
    state_summary: SessionStateSummary | None = None
    hard_constraints: HardConstraints | None = None
    soft_preferences: SoftPreferences | None = None
    selected_major_course_ids: list[str] | None = None
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
