"""Selected timetable state stored separately from user preferences."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .timetable_generation import SectionSource


class SelectedTimetableStatus(str, Enum):
    CURRENT = "CURRENT"
    STALE = "STALE"
    INVALID = "INVALID"


class SelectedTimetable(BaseModel):
    """Durable snapshot of the user's explicitly selected timetable candidate."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    candidate_id: str = Field(min_length=1)
    section_ids: list[str] = Field(min_length=1)
    fixed_section_ids: list[str] = Field(default_factory=list)
    added_section_ids: list[str] = Field(default_factory=list)
    course_ids: list[str] = Field(min_length=1)
    section_sources: list[SectionSource] = Field(default_factory=list)
    fixed_section_sources: list[SectionSource] = Field(default_factory=list)
    added_section_sources: list[SectionSource] = Field(default_factory=list)
    total_credits: float | None = Field(default=None, ge=0)
    selected_at: datetime

    @field_validator("section_ids", "fixed_section_ids", "added_section_ids", "course_ids")
    @classmethod
    def validate_non_empty_items(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("id lists must not contain empty values")
        return list(dict.fromkeys(values))

    @field_validator("selected_at")
    @classmethod
    def validate_selected_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
            raise ValueError("selected_at must include timezone information")
        return value
