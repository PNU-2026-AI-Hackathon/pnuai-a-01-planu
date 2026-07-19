"""Core course models shared by parsers, services, and API schemas."""

from __future__ import annotations

from enum import Enum
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Category(str, Enum):
    """Course categories used internally by PlaNU."""

    MAJOR_BASIC = "MAJOR_BASIC"
    MAJOR_REQUIRED = "MAJOR_REQUIRED"
    GENERAL_REQUIRED = "GENERAL_REQUIRED"
    GENERAL_ELECTIVE = "GENERAL_ELECTIVE"

    @property
    def korean_label(self) -> str:
        return {
            Category.MAJOR_BASIC: "전공기초",
            Category.MAJOR_REQUIRED: "전공필수",
            Category.GENERAL_REQUIRED: "교양필수",
            Category.GENERAL_ELECTIVE: "교양선택",
        }[self]


_CATEGORY_ALIASES = {
    "전공기초": Category.MAJOR_BASIC,
    "전기": Category.MAJOR_BASIC,
    "MAJOR_BASIC": Category.MAJOR_BASIC,
    "MAJORBASIC": Category.MAJOR_BASIC,
    "전공필수": Category.MAJOR_REQUIRED,
    "전필": Category.MAJOR_REQUIRED,
    "MAJOR_REQUIRED": Category.MAJOR_REQUIRED,
    "MAJORREQUIRED": Category.MAJOR_REQUIRED,
    "교양필수": Category.GENERAL_REQUIRED,
    "효원핵심교양": Category.GENERAL_REQUIRED,
    "GENERAL_REQUIRED": Category.GENERAL_REQUIRED,
    "GENERALREQUIRED": Category.GENERAL_REQUIRED,
    "교양선택": Category.GENERAL_ELECTIVE,
    "GENERAL_ELECTIVE": Category.GENERAL_ELECTIVE,
    "GENERALELECTIVE": Category.GENERAL_ELECTIVE,
}


def normalize_course_category(value: Any) -> Category:
    """Convert source category labels into PlaNU's internal Category enum."""

    if isinstance(value, Category):
        return value
    if value is None:
        raise ValueError("course category is required")
    text = re.sub(r"\s+", "", str(value).strip()).upper()
    if not text:
        raise ValueError("course category is required")
    try:
        return _CATEGORY_ALIASES[text]
    except KeyError as exc:
        raise ValueError(f"unknown course category: {value}") from exc


class Day(str, Enum):
    """Weekdays supported by the MVP, in timetable display order."""

    MON = "MON"
    TUE = "TUE"
    WED = "WED"
    THU = "THU"
    FRI = "FRI"
    SAT = "SAT"
    SUN = "SUN"


def time_to_minutes(value: str) -> int:
    """Convert an API time (``HH:MM``) to minutes after midnight."""

    try:
        hour_text, minute_text = value.split(":")
        if len(hour_text) != 2 or len(minute_text) != 2:
            raise ValueError
        hour, minute = int(hour_text), int(minute_text)
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError("time must use HH:MM format") from exc
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError("time must be a valid 24-hour time")
    return hour * 60 + minute


class _Model(BaseModel):
    model_config = ConfigDict(
        # 정의되지 않은 필드는 받지 않음
        extra="forbid",
        # 모든 문자열 필드에 대해 공백 제거
        str_strip_whitespace=True,
        # 필드 값이 바뀔 때마다 검증 수행
        validate_assignment=True,
    )


class ClassTime(_Model):
    """One meeting of a course; a course may meet in different rooms by day."""

    day: Day
    start: str
    end: str
    classroom: str = Field(min_length=1)
    building_code: str = Field(min_length=1)

    @field_validator("start", "end")
    @classmethod
    def validate_time(cls, value: str) -> str:
        time_to_minutes(value)
        return value

    @model_validator(mode="after")
    def validate_time_range(self) -> "ClassTime":
        if self.start_minutes >= self.end_minutes:
            raise ValueError("class end time must be later than start time")
        return self

    @property
    def start_minutes(self) -> int:
        return time_to_minutes(self.start)

    @property
    def end_minutes(self) -> int:
        return time_to_minutes(self.end)

    def overlaps(self, other: "ClassTime") -> bool:
        """Return whether two meetings overlap; touching endpoints are allowed."""

        return (
            self.day == other.day
            and self.start_minutes < other.end_minutes
            and other.start_minutes < self.end_minutes
        )


class Course(_Model):
    """A single course division that can be placed on a timetable."""

    course_id: str = Field(min_length=1)
    course_name: str = Field(min_length=1)
    category: Category
    area: int | None = Field(default=None, ge=1, le=7) # 교양 영역 번호
    credit: float = Field(gt=0) # 학점
    division: str = Field(min_length=1) # 분반
    professor: str = Field(min_length=1)
    class_times: list[ClassTime] = Field(min_length=1) # 수업 시간 목록

    @field_validator("category", mode="before")
    @classmethod
    def validate_category(cls, value: Any) -> Category:
        return normalize_course_category(value)

    @model_validator(mode="after")
    def validate_course(self) -> "Course":
        if self.category == Category.GENERAL_ELECTIVE and self.area is None:
            raise ValueError("general elective courses must specify an area")

        meetings = {(item.day, item.start, item.end) for item in self.class_times}
        if len(meetings) != len(self.class_times): # 겹치는 수업시간이 없는지 확인
            raise ValueError("class_times must not contain duplicate meetings")
        return self

    def conflicts_with(self, other: "Course") -> bool:
        return any(a.overlaps(b) for a in self.class_times for b in other.class_times)
