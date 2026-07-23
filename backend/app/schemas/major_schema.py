"""Request and response schemas for major-course selection APIs."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..models.course import Category, Day
from ..models.major_selection import MajorCourseReference
from ..services.session_store import SessionStage


MAJOR_PREVIEW_PROMPT_MAX_LENGTH = 1000


class _Model(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )


class MajorPreviewRequest(_Model):
    session_id: str = Field(min_length=1)
    prompt: str = Field(min_length=1, max_length=MAJOR_PREVIEW_PROMPT_MAX_LENGTH)

    @field_validator("session_id", "prompt")
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value


class MajorConfirmRequest(_Model):
    session_id: str = Field(min_length=1)
    preview_id: str = Field(min_length=1)

    @field_validator("session_id", "preview_id")
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value


class MajorManualPreviewRequest(_Model):
    session_id: str = Field(min_length=1)
    course_ids: list[str] = Field(min_length=1)

    @field_validator("session_id")
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value

    @field_validator("course_ids")
    @classmethod
    def reject_blank_course_ids(cls, values: list[str]) -> list[str]:
        cleaned: list[str] = []
        for value in values:
            if not value.strip():
                raise ValueError("course_ids must not contain blank values")
            if value not in cleaned:
                cleaned.append(value)
        return cleaned


class MajorPreviewClassTime(_Model):
    day: Day
    start: str
    end: str
    classroom: str
    building_code: str


class MajorPreviewCourse(_Model):
    course_id: str
    course_name: str
    category: Category
    area: int | None = None
    credit: float
    division: str
    professor: str
    class_times: list[MajorPreviewClassTime]


class MajorCourseListResponse(_Model):
    session_id: str
    courses: list[MajorPreviewCourse] = Field(default_factory=list)


class MajorPreviewTimetableEntry(_Model):
    course_id: str
    course_name: str
    category: Category
    credit: float
    division: str
    professor: str
    day: Day
    start: str
    end: str
    classroom: str
    building_code: str


class MatchedMajorPreviewCourse(_Model):
    reference: MajorCourseReference
    course: MajorPreviewCourse


class AmbiguousMajorPreviewCourse(_Model):
    reference: MajorCourseReference
    candidates: list[MajorPreviewCourse] = Field(default_factory=list)
    reason: str


class UnmatchedMajorPreviewCourse(_Model):
    reference: MajorCourseReference
    reason: str


class MajorPreviewConflict(_Model):
    first_course_id: str
    second_course_id: str
    day: Day
    overlap_start: str
    overlap_end: str


class MajorPreviewResponse(_Model):
    session_id: str
    preview_id: str
    matched_courses: list[MatchedMajorPreviewCourse] = Field(default_factory=list)
    ambiguous_courses: list[AmbiguousMajorPreviewCourse] = Field(default_factory=list)
    unmatched_courses: list[UnmatchedMajorPreviewCourse] = Field(default_factory=list)
    ambiguous_texts: list[str] = Field(default_factory=list)
    timetable_entries: list[MajorPreviewTimetableEntry] = Field(default_factory=list)
    has_time_conflict: bool
    conflicts: list[MajorPreviewConflict] = Field(default_factory=list)
    can_confirm: bool


class MajorConfirmResponse(_Model):
    session_id: str
    preview_id: str
    confirmed_courses: list[MajorPreviewCourse] = Field(default_factory=list)
    confirmed_course_count: int
    confirmed_major_credits: float
    session_stage: SessionStage
