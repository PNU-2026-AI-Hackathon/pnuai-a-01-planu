"""Models for general-course candidate pool preparation."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .course import Course


class _Model(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )


class GeneralCoursePools(_Model):
    required_courses: list[Course] = Field(default_factory=list)
    elective_courses: list[Course] = Field(default_factory=list)


class ExcludedCourseDiagnostic(_Model):
    course_key: str | None = None
    course_name: str
    section: str
    reason_code: str
    reason: str
    source: str | None = None


class GeneralCoursePoolResult(_Model):
    pools: GeneralCoursePools = Field(default_factory=GeneralCoursePools)
    excluded_courses: list[ExcludedCourseDiagnostic] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
