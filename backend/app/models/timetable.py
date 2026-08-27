"""Models for generated and ranked timetable candidates."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .course import Category, Course, Day, time_to_minutes
from .preference import PreferenceRules, PreferenceWarning, UnsupportedCondition


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


class RankingTemplate(str, Enum):
    BALANCED = "balanced"
    FREE_DAY_PRIORITY = "free_day_priority"
    NO_MORNING_PRIORITY = "no_morning_priority"
    COMPACT_SCHEDULE = "compact_schedule"


class CourseLoadSatisfaction(_Model):
    """Objective course-load metadata calculated during candidate generation."""

    final_total_credits: float = Field(default=0, ge=0)
    target_total_credits: float | None = None
    required_general_count: int = Field(default=0, ge=0)
    required_general_credits: float = Field(default=0, ge=0)
    elective_count: int = Field(default=0, ge=0)
    requested_elective_count: int | None = Field(default=None, ge=0)
    credit_gap: float | None = None
    elective_count_gap: int | None = Field(default=None, ge=0)
    within_credit_limit: bool | None = None
    elective_count_met: bool | None = None
    satisfied_required_group_count: int | None = Field(default=None, ge=0)
    requested_required_group_count: int | None = Field(default=None, ge=0)
    satisfied_elective_count: int | None = Field(default=None, ge=0)

    @property
    def required_group_sort_count(self) -> int:
        if self.satisfied_required_group_count is not None:
            return self.satisfied_required_group_count
        return self.required_general_count

    @property
    def elective_count_sort_gap(self) -> int:
        if self.elective_count_gap is not None:
            return self.elective_count_gap
        if self.requested_elective_count is None:
            return 0
        return max(self.requested_elective_count - self.elective_count, 0)

    @property
    def credit_sort_gap(self) -> float:
        if self.credit_gap is not None:
            return self.credit_gap
        if self.target_total_credits is None:
            return 0
        return abs(self.target_total_credits - self.final_total_credits)


class Timetable(_Model):
    """A recommendation candidate ready to return from ``POST /recommend``."""

    rank: int = Field(default=1, ge=1) # 추천순위
    score: float = 0
    total_credit: float | None = Field(default=None, gt=0)
    courses: list[Course] = Field(min_length=1)
    schedule_items: list[ScheduleItem] = Field(default_factory=list)
    score_details: list[ScoreComponent] = Field(default_factory=list)
    load_satisfaction: CourseLoadSatisfaction = Field(
        default_factory=CourseLoadSatisfaction
    )
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
            key=lambda item: (list(Day).index(item.day), time_to_minutes(item.start))
        )
        return self


# Descriptive alias used by generator/ranker services.
TimetableCandidate = Timetable


class TimetableGenerationCandidate(_Model):
    """A valid generated timetable plus non-ranking objective metadata."""

    timetable: Timetable
    load_satisfaction: CourseLoadSatisfaction


class GenerationDiagnostic(_Model):
    reason_code: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    count: int | None = None


class TimetableGenerationResult(_Model):
    candidates: list[TimetableGenerationCandidate] = Field(default_factory=list)
    diagnostics: list[GenerationDiagnostic] = Field(default_factory=list)
    truncated: bool = False
    hard_conditions: PreferenceRules = Field(default_factory=PreferenceRules)
    soft_conditions: PreferenceRules = Field(default_factory=PreferenceRules)
    unsupported_conditions: list[UnsupportedCondition] = Field(default_factory=list)
    warnings: list[PreferenceWarning] = Field(default_factory=list)


class RankingResult(_Model):
    raw_score: float = 0
    score_components: list[ScoreComponent] = Field(default_factory=list)
    timetable: Timetable
    load_satisfaction: CourseLoadSatisfaction = Field(
        default_factory=CourseLoadSatisfaction
    )
    template: RankingTemplate = RankingTemplate.BALANCED

    @model_validator(mode="after")
    def sync_raw_score_and_timetable(self) -> "RankingResult":
        raw_score = sum(component.value for component in self.score_components)
        load_satisfaction = (
            self.load_satisfaction
            if self.load_satisfaction != CourseLoadSatisfaction()
            else self.timetable.load_satisfaction
        )
        object.__setattr__(self, "raw_score", raw_score)
        object.__setattr__(self, "load_satisfaction", load_satisfaction)
        object.__setattr__(
            self,
            "timetable",
            self.timetable.model_copy(
                update={
                    "score": raw_score,
                    "score_details": self.score_components,
                    "load_satisfaction": load_satisfaction,
                }
            ),
        )
        return self


class RankingDiagnostic(_Model):
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    details: dict[str, Any] = Field(default_factory=dict)


class TimetableRankingResult(_Model):
    ranked_candidates: list[RankingResult] = Field(default_factory=list)
    template: RankingTemplate = RankingTemplate.BALANCED
    total_candidate_count: int = Field(default=0, ge=0)
    diagnostics: list[RankingDiagnostic] = Field(default_factory=list)
