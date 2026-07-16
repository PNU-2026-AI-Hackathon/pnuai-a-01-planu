"""Models for recommendation course-load targets and calculation results."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .course import Course


class _Model(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )


class CourseLoadTarget(_Model):
    """Optional user targets for general-course recommendation volume."""

    target_total_credits: float | None = Field(default=None, gt=0)
    additional_elective_count: int | None = Field(default=None, ge=0)


class CourseLoadWarning(_Model):
    """Structured warning emitted when course-load goals cannot be fully met."""

    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    requested_elective_count: int | None = None
    actual_elective_count: int | None = None
    reason: str | None = None


class CourseLoadCalculationResult(_Model):
    """Result of applying a course-load target to available general courses."""

    target: CourseLoadTarget = Field(default_factory=CourseLoadTarget)
    fixed_major_credits: float = Field(ge=0)
    target_total_credits: float | None = None
    selected_required_general_courses: list[Course] = Field(default_factory=list)
    selected_elective_general_courses: list[Course] = Field(default_factory=list)
    final_total_credits: float = Field(ge=0)
    remaining_credit_capacity: float | None = Field(default=None, ge=0)
    warnings: list[CourseLoadWarning] = Field(default_factory=list)

    @property
    def selected_required_general_count(self) -> int:
        return len(self.selected_required_general_courses)

    @property
    def selected_elective_general_count(self) -> int:
        return len(self.selected_elective_general_courses)
