"""First-pass filtering for general-education recommendation candidates."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from ..models.course import Category, Course, time_to_minutes
from ..models.preference import ExcludedTimeRange, PreferenceRules
from .course_name_matcher import course_name_matches


@dataclass(frozen=True, slots=True)
class CourseFilterResult:
    """Filtered candidates grouped for the timetable generator."""

    general_required: list[Course] = field(default_factory=list)
    general_elective: list[Course] = field(default_factory=list)
    rejected_count: int = 0

    @property
    def total_count(self) -> int:
        return len(self.general_required) + len(self.general_elective)


class CourseFilter:
    """Apply deterministic hard filters before timetable generation.

    The LLM only produces ``PreferenceRules``. This service interprets the hard
    parts of those rules and keeps ranking-only preferences for the ranker.
    """

    def filter(
        self,
        courses: Iterable[Course],
        *,
        fixed_courses: Iterable[Course] = (),
        preferences: PreferenceRules | None = None,
    ) -> CourseFilterResult:
        rules = preferences or PreferenceRules()
        fixed = list(fixed_courses)
        required: list[Course] = []
        elective: list[Course] = []
        rejected_count = 0

        for course in courses:
            if course.category not in {
                Category.GENERAL_REQUIRED,
                Category.GENERAL_ELECTIVE,
            }:
                rejected_count += 1
                continue
            if self._fails_preference_hard_filters(course, rules):
                rejected_count += 1
                continue
            if any(course.conflicts_with(fixed_course) for fixed_course in fixed):
                rejected_count += 1
                continue

            if course.category == Category.GENERAL_REQUIRED:
                required.append(course)
            else:
                elective.append(course)

        return CourseFilterResult(
            general_required=required,
            general_elective=elective,
            rejected_count=rejected_count,
        )

    def split_by_category(self, courses: Iterable[Course]) -> CourseFilterResult:
        """Group already-filtered courses by general-education category."""

        values = list(courses)
        required = [
            course for course in values if course.category == Category.GENERAL_REQUIRED
        ]
        elective = [
            course for course in values if course.category == Category.GENERAL_ELECTIVE
        ]
        rejected = len(values) - len(required) - len(elective)
        return CourseFilterResult(required, elective, rejected)

    @staticmethod
    def _fails_preference_hard_filters(
        course: Course, preferences: PreferenceRules
    ) -> bool:
        if preferences.excluded_days and any(
            meeting.day in preferences.excluded_days for meeting in course.class_times
        ):
            return True

        if preferences.required_free_days and any(
            meeting.day in preferences.required_free_days for meeting in course.class_times
        ):
            return True

        if preferences.earliest_start_time is not None:
            earliest = time_to_minutes(preferences.earliest_start_time)
            if any(meeting.start_minutes < earliest for meeting in course.class_times):
                return True

        if preferences.latest_end_time is not None:
            latest = time_to_minutes(preferences.latest_end_time)
            if any(meeting.end_minutes > latest for meeting in course.class_times):
                return True

        if preferences.excluded_time_ranges and any(
            CourseFilter._overlaps_excluded_range(meeting, excluded)
            for meeting in course.class_times
            for excluded in preferences.excluded_time_ranges
        ):
            return True

        excluded_professors = {
            professor.casefold() for professor in preferences.excluded_professors
        }
        if excluded_professors and course.professor.casefold() in excluded_professors:
            return True

        return any(
            course_name_matches(name, course.course_name)
            for name in preferences.excluded_course_names
        )

    @staticmethod
    def _overlaps_excluded_range(
        meeting: object, excluded: ExcludedTimeRange
    ) -> bool:
        return (
            meeting.day == excluded.day
            and meeting.start_minutes < excluded.end_minutes
            and excluded.start_minutes < meeting.end_minutes
        )


def filter_general_courses(
    courses: Iterable[Course],
    *,
    fixed_courses: Iterable[Course] = (),
    preferences: PreferenceRules | None = None,
) -> CourseFilterResult:
    """Functional convenience API used by route handlers and tests."""

    return CourseFilter().filter(
        courses,
        fixed_courses=fixed_courses,
        preferences=preferences,
    )
