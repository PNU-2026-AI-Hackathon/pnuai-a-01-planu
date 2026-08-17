"""Typed patch DTOs for batched session updates."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from ..models import Day


ProfileField = Literal["department", "major_catalog_id", "elective_catalog_id"]
SelectedMajorCourseMode = Literal["replace", "add", "remove"]
HardPreferenceField = Literal[
    "required_free_days",
    "earliest_start_time",
    "latest_end_time",
    "required_course_ids",
    "excluded_course_ids",
    "min_credit",
    "max_credit",
]
SoftPreferenceField = Literal[
    "preferred_free_days",
    "preferred_earliest_start_time",
    "preferred_latest_end_time",
    "preferred_course_ids",
    "disliked_course_ids",
    "compact_schedule",
]


@dataclass(frozen=True)
class SessionProfileUpdate:
    """Service-level patch for profile fields.

    ``None`` means a field was not supplied. Clearing nullable profile fields is
    represented explicitly through ``clear_fields``.
    """

    department: str | None = None
    major_catalog_id: str | None = None
    elective_catalog_id: str | None = None
    clear_fields: tuple[ProfileField, ...] = ()


@dataclass(frozen=True)
class HardConstraintsUpdate:
    """Service-level patch for hard timetable constraints."""

    required_free_days: list[Day] | None = None
    earliest_start_time: str | None = None
    latest_end_time: str | None = None
    required_course_ids: list[str] | None = None
    excluded_course_ids: list[str] | None = None
    min_credit: float | None = None
    max_credit: float | None = None
    clear_fields: tuple[HardPreferenceField, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class SoftPreferencesUpdate:
    """Service-level patch for soft timetable preferences."""

    preferred_free_days: list[Day] | None = None
    preferred_earliest_start_time: str | None = None
    preferred_latest_end_time: str | None = None
    preferred_course_ids: list[str] | None = None
    disliked_course_ids: list[str] | None = None
    compact_schedule: bool | None = None
    clear_fields: tuple[SoftPreferenceField, ...] = field(default_factory=tuple)
