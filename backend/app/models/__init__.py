"""Public domain models for the PlaNU backend."""

from .course import Category, ClassTime, Course, Day, normalize_course_category, time_to_minutes
from .input_timetable import InputTimetable
from .preference import (
    ExcludedTimeRange,
    PreferenceParseResult,
    PreferenceParseStatus,
    PreferenceRules,
    PreferenceTemplate,
    PreferenceToolStatus,
    PreferenceToolUsage,
    PreferenceTraceEvent,
    TimeRange,
    merge_preference_rules,
)
from .timetable import ScheduleItem, ScoreDetail, Timetable, TimetableCandidate

__all__ = [
    "Category",
    "ClassTime",
    "Course",
    "Day",
    "ExcludedTimeRange",
    "InputTimetable",
    "PreferenceParseResult",
    "PreferenceParseStatus",
    "PreferenceRules",
    "PreferenceTemplate",
    "PreferenceToolStatus",
    "PreferenceToolUsage",
    "PreferenceTraceEvent",
    "ScheduleItem",
    "ScoreDetail",
    "TimeRange",
    "Timetable",
    "TimetableCandidate",
    "merge_preference_rules",
    "normalize_course_category",
    "time_to_minutes",
]
