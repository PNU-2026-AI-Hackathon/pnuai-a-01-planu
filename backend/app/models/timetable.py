"""Models for generated and ranked timetable candidates."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .course import Category, Course, Day, time_to_minutes


class _Model(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )


class ScheduleItem(_Model):
    day: Day
    start: str
    end: str
    course_name: str = Field(min_length=1)
    category: Category
    division: str = Field(min_length=1)
    professor: str = Field(min_length=1)
    classroom: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_time_range(self) -> "ScheduleItem":
        if time_to_minutes(self.start) >= time_to_minutes(self.end):
            raise ValueError("schedule item end time must be later than start time")
        return self


class ScoreComponent(_Model):
    key: str = Field(min_length=1)
    label: str = Field(min_length=1)
    value: float
    reason: str = Field(min_length=1)


# Backward-compatible alias for older tests/clients.
ScoreDetail = ScoreComponent


class Timetable(_Model):
    """A recommendation candidate ready to return from ``POST /recommend``."""

    rank: int = Field(default=1, ge=1) # 추천순위
    score: float = 0
    total_credit: float | None = Field(default=None, gt=0)
    courses: list[Course] = Field(min_length=1)
    schedule_items: list[ScheduleItem] = Field(default_factory=list)
    score_details: list[ScoreComponent] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def populate_and_validate(self) -> "Timetable":
        calculated_credit = sum(course.credit for course in self.courses)
        if self.total_credit is None:
            object.__setattr__(self, "total_credit", calculated_credit)
        elif abs(self.total_credit - calculated_credit) > 1e-9:
            raise ValueError("total_credit must equal the sum of course credits")

        course_ids = [course.course_id for course in self.courses]
        if len(course_ids) != len(set(course_ids)):
            raise ValueError("courses must not contain duplicate course_id values")

        if self.score_details:
            score = sum(detail.value for detail in self.score_details)
            object.__setattr__(self, "score", score)

        if not self.schedule_items:
            items = [
                ScheduleItem(
                    day=meeting.day,
                    start=meeting.start,
                    end=meeting.end,
                    course_name=course.course_name,
                    category=course.category,
                    division=course.division,
                    professor=course.professor,
                    classroom=meeting.classroom,
                )
                for course in self.courses
                for meeting in course.class_times
            ]
            object.__setattr__(self, "schedule_items", items)

        self.schedule_items.sort(
            key=lambda item: (item.day.order, time_to_minutes(item.start))
        )
        return self


# Descriptive alias used by generator/ranker services.
TimetableCandidate = Timetable


class RankingResult(_Model):
    raw_score: float = 0
    score_components: list[ScoreComponent] = Field(default_factory=list)
    timetable: Timetable

    @model_validator(mode="after")
    def sync_raw_score_and_timetable(self) -> "RankingResult":
        raw_score = sum(component.value for component in self.score_components)
        object.__setattr__(self, "raw_score", raw_score)
        object.__setattr__(
            self,
            "timetable",
            self.timetable.model_copy(
                update={
                    "score": raw_score,
                    "score_details": self.score_components,
                }
            ),
        )
        return self
