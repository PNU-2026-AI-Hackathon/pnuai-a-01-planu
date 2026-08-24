"""Structured condition summary DTOs for PlaNU chat responses."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, validate_assignment=True)


class ConditionItemStatus(str, Enum):
    SET = "SET"
    EMPTY = "EMPTY"
    UNSET = "UNSET"


class ConditionCourseRefDto(_Model):
    course_id: str
    course_name: str | None = None
    course_code: str | None = None


class ConditionSummaryItemDto(_Model):
    key: str
    label: str
    status: ConditionItemStatus
    display_value: str | None = None
    course_refs: list[ConditionCourseRefDto] = Field(default_factory=list)
    raw_value: object | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class MissingGenerationRequirementDto(_Model):
    code: str
    message: str


class GenerationReadinessDto(_Model):
    ready: bool
    generation_confirmed: bool = False
    confirmed_at: datetime | None = None
    confirmed_version: int | None = None
    current_version: int
    missing_requirements: list[MissingGenerationRequirementDto] = Field(default_factory=list)


class ConditionSummaryDto(_Model):
    hard_constraints: list[ConditionSummaryItemDto]
    soft_preferences: list[ConditionSummaryItemDto]
    selected_major_courses: list[ConditionCourseRefDto] = Field(default_factory=list)
    generation_readiness: GenerationReadinessDto
