"""Models for recommendation course-load target interpretation.

These models describe the credit goals and constraints that the future
backtracking engine should use. They do not represent a concrete timetable or
an already-selected set of general courses.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

class _Model(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )


class CourseLoadTarget(_Model):
    """Optional user targets for backtracking-based recommendation.

    ``target_total_credits`` is the total credit goal the user would like to
    approach, not a hard ``max_credit`` validator for this calculation stage.
    ``additional_elective_count`` is the desired number of elective general
    courses to add after required general courses are accounted for.
    """

    target_total_credits: float | None = Field(default=None, gt=0)
    additional_elective_count: int | None = Field(default=None, ge=0)


class CourseLoadWarning(_Model):
    """Structured warning emitted when interpreted load goals conflict."""

    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    requested_elective_count: int | None = None
    actual_elective_count: int | None = None
    reason: str | None = None


class CourseLoadCalculationResult(_Model):
    """Credit-capacity summary for the backtracking engine.

    The result intentionally contains no selected ``Course`` objects. Actual
    general-course combination generation, time-conflict checks, campus travel
    checks, and choosing one section among duplicate course divisions belong to
    the backtracking engine.
    """

    target: CourseLoadTarget = Field(default_factory=CourseLoadTarget)
    fixed_major_credits: float = Field(ge=0)
    required_general_credits: float = Field(ge=0)
    base_total_credits: float = Field(ge=0)
    target_total_credits: float | None = None
    remaining_elective_credit_capacity: float | None = Field(default=None, ge=0)
    additional_elective_count: int | None = Field(default=None, ge=0)
    warnings: list[CourseLoadWarning] = Field(default_factory=list)
