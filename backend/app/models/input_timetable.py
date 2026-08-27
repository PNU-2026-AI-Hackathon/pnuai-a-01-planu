"""Validation model for a user-confirmed fixed major timetable."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .course import Course, Day, time_to_minutes
from .timetable import ScheduleItem


class InputTimetable(BaseModel):
    """A fixed timetable entered by the user before recommendation generation.

    Unlike the recommendation ``Timetable`` model, this model rejects conflicts
    because fixed major courses must already form a valid schedule.
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    courses: list[Course] = Field(min_length=1)
    total_credit: float | None = Field(default=None, gt=0)
    schedule_items: list[ScheduleItem] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_fixed_timetable(self) -> "InputTimetable":
        course_ids = [course.course_id for course in self.courses]
        if len(course_ids) != len(set(course_ids)):
            raise ValueError("courses must not contain duplicate course_id values")

        for index, course in enumerate(self.courses):
            for other in self.courses[index + 1 :]:
                if course.conflicts_with(other):
                    raise ValueError(
                        "time conflict between courses "
                        f"'{course.course_id}' and '{other.course_id}'"
                    )

        calculated_credit = sum(course.credit for course in self.courses)
        if self.total_credit is None:
            object.__setattr__(self, "total_credit", calculated_credit)
        elif abs(self.total_credit - calculated_credit) > 1e-9:
            raise ValueError("total_credit must equal the sum of course credits")

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
