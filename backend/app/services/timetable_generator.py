"""Generate valid timetable candidates from fixed majors and general courses."""

from __future__ import annotations

from collections.abc import Iterable
from itertools import combinations

from ..models.course import Course
from ..models.timetable import Timetable, TimetableCandidate
from .campus_rule_engine import CampusRuleEngine
from .timetable_validator import TimetableValidator


class TimetableGenerator:
    """Backtracking-style generator for PlaNU recommendation candidates."""

    def __init__(
        self,
        validator: TimetableValidator | None = None,
        *,
        campus_rule_engine: CampusRuleEngine | None = None,
        max_candidates: int = 200,
        min_credit: float | None = None,
        max_credit: float | None = None,
    ) -> None:
        if max_candidates <= 0:
            raise ValueError("max_candidates must be positive")
        self.validator = validator or TimetableValidator(
            campus_rule_engine,
            min_credit=min_credit,
            max_credit=max_credit,
        )
        self.max_candidates = max_candidates

    def generate(
        self,
        *,
        fixed_courses: Iterable[Course],
        general_required_candidates: Iterable[Course] = (),
        general_elective_candidates: Iterable[Course] = (),
        required_general_count: int = 0,
        elective_general_count: int = 0,
        max_candidates: int | None = None,
        min_credit: float | None = None,
        max_credit: float | None = None,
    ) -> list[TimetableCandidate]:
        if required_general_count < 0 or elective_general_count < 0:
            raise ValueError("general course counts must not be negative")

        fixed = list(fixed_courses)
        required_candidates = self._dedupe_by_course_identity(
            general_required_candidates
        )
        elective_candidates = self._dedupe_by_course_identity(
            general_elective_candidates
        )
        limit = self.max_candidates if max_candidates is None else max_candidates
        if limit <= 0:
            raise ValueError("max_candidates must be positive")

        candidates: list[TimetableCandidate] = []
        for required_group in combinations(required_candidates, required_general_count):
            if not self.validator.is_valid(required_group, fixed_courses=fixed):
                continue
            for elective_group in combinations(
                elective_candidates, elective_general_count
            ):
                selected = [*required_group, *elective_group]
                result = self.validator.validate(
                    selected,
                    fixed_courses=fixed,
                    min_credit=min_credit,
                    max_credit=max_credit,
                )
                if not result.valid:
                    continue
                candidates.append(Timetable(courses=[*fixed, *selected]))
                if len(candidates) >= limit:
                    return candidates
        return candidates

    @staticmethod
    def _dedupe_by_course_identity(courses: Iterable[Course]) -> list[Course]:
        deduped: list[Course] = []
        seen: set[tuple[str, str]] = set()
        for course in courses:
            key = (course.course_id, course.division)
            if key in seen:
                continue
            deduped.append(course)
            seen.add(key)
        return deduped

    @staticmethod
    def _dedupe_by_course_id(courses: Iterable[Course]) -> list[Course]:
        """Backward-compatible alias; division is part of candidate identity."""

        return TimetableGenerator._dedupe_by_course_identity(courses)


def generate_timetables(
    *,
    fixed_courses: Iterable[Course],
    general_required_candidates: Iterable[Course] = (),
    general_elective_candidates: Iterable[Course] = (),
    required_general_count: int = 0,
    elective_general_count: int = 0,
    campus_rule_engine: CampusRuleEngine | None = None,
    max_candidates: int = 200,
    min_credit: float | None = None,
    max_credit: float | None = None,
) -> list[TimetableCandidate]:
    """Functional convenience API for recommendation route handlers."""

    return TimetableGenerator(
        campus_rule_engine=campus_rule_engine,
        max_candidates=max_candidates,
        min_credit=min_credit,
        max_credit=max_credit,
    ).generate(
        fixed_courses=fixed_courses,
        general_required_candidates=general_required_candidates,
        general_elective_candidates=general_elective_candidates,
        required_general_count=required_general_count,
        elective_general_count=elective_general_count,
        min_credit=min_credit,
        max_credit=max_credit,
    )
