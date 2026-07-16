"""Models for matching LLM-selected major courses to catalog courses."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .course import Course


class _Model(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )


class MajorCourseReference(_Model):
    """A course reference extracted from natural language."""

    course_name: str = Field(min_length=1)
    section: str | None = None


class MajorSelectionParseResult(_Model):
    """Structured LLM output before catalog matching."""

    selected_courses: list[MajorCourseReference] = Field(default_factory=list)
    ambiguous_texts: list[str] = Field(default_factory=list)


class MatchedMajorCourse(_Model):
    """A reference that resolved to exactly one existing catalog course."""

    reference: MajorCourseReference
    course: Course


class AmbiguousMajorCourse(_Model):
    """A reference that needs user confirmation before selecting a course."""

    reference: MajorCourseReference
    candidates: list[Course] = Field(default_factory=list)
    reason: str = Field(min_length=1)


class UnmatchedMajorCourse(_Model):
    """A reference that could not be found in the parsed course catalog."""

    reference: MajorCourseReference
    reason: str = Field(min_length=1)


class MajorCourseMatchResult(_Model):
    """Outcome of matching selected major course references to catalog courses."""

    matched: list[MatchedMajorCourse] = Field(default_factory=list)
    ambiguous: list[AmbiguousMajorCourse] = Field(default_factory=list)
    unmatched: list[UnmatchedMajorCourse] = Field(default_factory=list)
