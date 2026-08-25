"""Validation of generated timetable candidates."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Iterable

from ..models.course import ClassTime, Course
from .campus_rule_engine import CampusRuleEngine


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    code: str
    message: str
    course_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ValidationResult:
    valid: bool
    issues: tuple[ValidationIssue, ...] = ()

    def __bool__(self) -> bool:
        return self.valid


class TimetableValidator:
    def __init__(
        self,
        campus_rule_engine: CampusRuleEngine | None = None,
        *,
        min_credit: float | None = None,
        min_credit_inclusive: bool | None = None,
        max_credit: float | None = None,
        max_credit_inclusive: bool | None = None,
        travel_check_max_gap: int | None = None,
    ) -> None:
        if min_credit is not None and min_credit < 0:
            raise ValueError("min_credit must not be negative")
        if max_credit is not None and max_credit < 0:
            raise ValueError("max_credit must not be negative")
        if min_credit is not None and max_credit is not None and min_credit > max_credit:
            raise ValueError("min_credit must not exceed max_credit")
        self.campus_rule_engine = campus_rule_engine or CampusRuleEngine()
        self.min_credit = min_credit
        self.min_credit_inclusive = (True if min_credit_inclusive is None else min_credit_inclusive) if min_credit is not None else True
        self.max_credit = max_credit
        self.max_credit_inclusive = (True if max_credit_inclusive is None else max_credit_inclusive) if max_credit is not None else True
        self.travel_check_max_gap = travel_check_max_gap

    def validate(
        self,
        courses: Iterable[Course],
        *,
        fixed_courses: Iterable[Course] = (),
        min_credit: float | None = None,
        min_credit_inclusive: bool | None = None,
        max_credit: float | None = None,
        max_credit_inclusive: bool | None = None,
    ) -> ValidationResult:
        selected = list(courses)
        fixed = list(fixed_courses)
        combined = self._deduplicate_same_objects(fixed + selected)
        issues: list[ValidationIssue] = []

        ids = [course.course_id for course in combined]
        duplicate_ids = sorted({course_id for course_id in ids if ids.count(course_id) > 1})
        if duplicate_ids:
            issues.append(ValidationIssue(
                "DUPLICATE_COURSE",
                "같은 분반이 시간표에 중복 포함되어 있습니다.",
                tuple(duplicate_ids),
            ))

        for first, second in combinations(combined, 2):
            if first.course_id == second.course_id:
                continue
            if first.conflicts_with(second):
                issues.append(ValidationIssue(
                    "TIME_CONFLICT",
                    f"{first.course_name}과(와) {second.course_name}의 시간이 겹칩니다.",
                    (first.course_id, second.course_id),
                ))

        issues.extend(self._travel_issues(combined))

        total_credit = sum(course.credit for course in combined)
        lower = self.min_credit if min_credit is None else min_credit
        lower_inclusive = self.min_credit_inclusive if min_credit_inclusive is None else min_credit_inclusive
        upper = self.max_credit if max_credit is None else max_credit
        upper_inclusive = self.max_credit_inclusive if max_credit_inclusive is None else max_credit_inclusive
        if lower is not None and (total_credit < lower if lower_inclusive else total_credit <= lower):
            issues.append(ValidationIssue(
                "CREDIT_BELOW_MINIMUM",
                f"총 학점 {total_credit:g}은 최소 학점 {lower:g}보다 적습니다.",
            ))
        if upper is not None and (total_credit > upper if upper_inclusive else total_credit >= upper):
            issues.append(ValidationIssue(
                "CREDIT_ABOVE_MAXIMUM",
                f"총 학점 {total_credit:g}은 최대 학점 {upper:g}보다 많습니다.",
            ))
        return ValidationResult(not issues, tuple(issues))

    def is_valid(self, courses: Iterable[Course], **kwargs: object) -> bool:
        return self.validate(courses, **kwargs).valid

    @staticmethod
    def has_time_conflict(courses: Iterable[Course]) -> bool:
        values = list(courses)
        return any(first.conflicts_with(second) for first, second in combinations(values, 2))

    @staticmethod
    def calculate_total_credit(courses: Iterable[Course]) -> float:
        return sum(course.credit for course in courses)

    def _travel_issues(self, courses: list[Course]) -> list[ValidationIssue]:
        meetings: list[tuple[ClassTime, Course]] = [
            (meeting, course) for course in courses for meeting in course.class_times
        ]
        issues: list[ValidationIssue] = []
        for day in {meeting.day for meeting, _ in meetings}:
            daily = sorted(
                ((meeting, course) for meeting, course in meetings if meeting.day == day),
                key=lambda value: value[0].start_minutes,
            )
            # Only adjacent classes matter: any class between them consumes the gap.
            for (previous, previous_course), (following, following_course) in zip(daily, daily[1:]):
                if previous.overlaps(following):
                    continue
                gap = following.start_minutes - previous.end_minutes
                if self.travel_check_max_gap is not None and gap > self.travel_check_max_gap:
                    continue
                if not self.campus_rule_engine.can_travel(
                    previous.building_code, following.building_code, gap
                ):
                    if self.campus_rule_engine.has_blocked_building_prefix_distance(
                        previous.building_code, following.building_code
                    ):
                        message = (
                            f"{previous_course.course_name}에서 {following_course.course_name}까지 "
                            "강의실 번호 앞자리 차이가 3 이상이라 이동할 수 없습니다."
                        )
                    else:
                        required = self.campus_rule_engine.required_travel_minutes(
                            previous.building_code, following.building_code
                        )
                        message = (
                            f"{previous_course.course_name}에서 {following_course.course_name}까지 "
                            f"이동에 {required}분이 필요하지만 공백은 {gap}분입니다."
                        )
                    issues.append(ValidationIssue(
                        "TRAVEL_NOT_POSSIBLE",
                        message,
                        (previous_course.course_id, following_course.course_id),
                    ))
        return issues

    @staticmethod
    def _deduplicate_same_objects(courses: list[Course]) -> list[Course]:
        """Avoid counting a fixed course twice if callers also include it in courses."""

        result: list[Course] = []
        seen_objects: set[int] = set()
        for course in courses:
            if id(course) not in seen_objects:
                result.append(course)
                seen_objects.add(id(course))
        return result


def validate_timetable(
    courses: Iterable[Course],
    *,
    fixed_courses: Iterable[Course] = (),
    campus_rule_engine: CampusRuleEngine | None = None,
    min_credit: float | None = None,
    min_credit_inclusive: bool = True,
    max_credit: float | None = None,
    max_credit_inclusive: bool = True,
) -> ValidationResult:
    """Functional convenience API for generators that do not retain a validator."""

    return TimetableValidator(
        campus_rule_engine,
        min_credit=min_credit,
        min_credit_inclusive=min_credit_inclusive,
        max_credit=max_credit,
        max_credit_inclusive=max_credit_inclusive,
    ).validate(courses, fixed_courses=fixed_courses)
