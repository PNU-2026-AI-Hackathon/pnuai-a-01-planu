"""First-pass filtering for general-education recommendation candidates."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from ..models.course import Category, Course, time_to_minutes
from ..models.preference import PreferenceRules


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

    def __init__(
        self,
        *,
        restricted_course_ids_by_department: dict[str, set[str]] | None = None,
        restricted_course_names_by_department: dict[str, set[str]] | None = None,
    ) -> None:
        self.restricted_course_ids_by_department = (
            restricted_course_ids_by_department or {}
        )
        self.restricted_course_names_by_department = (
            restricted_course_names_by_department or {}
        )

    def filter(
        self,
        courses: Iterable[Course],
        *,
        fixed_courses: Iterable[Course] = (),
        preferences: PreferenceRules | None = None,
        department: str | None = None,
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
            if self._is_restricted(course, department):
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

    def _is_restricted(self, course: Course, department: str | None) -> bool:
        if not department:
            return False
        restricted_ids = self.restricted_course_ids_by_department.get(department, set())
        restricted_names = self.restricted_course_names_by_department.get(
            department, set()
        )
        return course.course_id in restricted_ids or course.course_name in restricted_names

    @staticmethod
    def _fails_preference_hard_filters(
        course: Course, preferences: PreferenceRules
    ) -> bool:
        if preferences.excluded_days and any(
            meeting.day in preferences.excluded_days for meeting in course.class_times
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

        if (
            course.category == Category.GENERAL_ELECTIVE
            and preferences.preferred_elective_areas
            and course.area not in preferences.preferred_elective_areas
        ):
            return True

        searchable = f"{course.course_name} {course.professor}".casefold()
        if preferences.required_keywords and not all(
            keyword.casefold() in searchable
            for keyword in preferences.required_keywords
        ):
            return True

        return any(
            keyword.casefold() in searchable
            for keyword in preferences.excluded_keywords
        )


def filter_general_courses(
    courses: Iterable[Course],
    *,
    fixed_courses: Iterable[Course] = (),
    preferences: PreferenceRules | None = None,
    department: str | None = None,
    restricted_course_ids_by_department: dict[str, set[str]] | None = None,
    restricted_course_names_by_department: dict[str, set[str]] | None = None,
) -> CourseFilterResult:
    """Functional convenience API used by route handlers and tests."""

    return CourseFilter(
        restricted_course_ids_by_department=restricted_course_ids_by_department,
        restricted_course_names_by_department=restricted_course_names_by_department,
    ).filter(
        courses,
        fixed_courses=fixed_courses,
        preferences=preferences,
        department=department,
    )
