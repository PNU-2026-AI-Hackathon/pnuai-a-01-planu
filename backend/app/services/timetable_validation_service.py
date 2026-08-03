"""Deterministic validation for concrete timetable section selections."""

from __future__ import annotations

from collections.abc import Iterable
from itertools import combinations

from ..models.course import Course, time_to_minutes
from ..models.course_discovery import CourseSection
from ..models.timetable_generation import (
    TimetableValidationResult,
    TimetableViolation,
    TimetableViolationCode,
)
from .campus_rule_engine import CampusRuleEngine
from .general_course_pool_service import CourseRestrictionPolicy
from .timetable_validator import TimetableValidator


class TimetableValidationService:
    """Validate a complete or partial timetable against hard constraints."""

    def __init__(
        self,
        *,
        campus_rule_engine: CampusRuleEngine | None = None,
        restriction_policy: CourseRestrictionPolicy | None = None,
        travel_check_max_gap: int | None = 30,
    ) -> None:
        self.campus_rule_engine = campus_rule_engine or CampusRuleEngine()
        self.restriction_policy = restriction_policy or CourseRestrictionPolicy()
        self._validator = TimetableValidator(
            self.campus_rule_engine,
            travel_check_max_gap=travel_check_max_gap,
        )

    def validate_sections(
        self,
        sections: Iterable[CourseSection],
        *,
        required_course_ids: Iterable[str] = (),
        excluded_course_ids: Iterable[str] = (),
        required_free_days: Iterable[object] = (),
        earliest_start_time: str | None = None,
        latest_end_time: str | None = None,
        department: str | None = None,
    ) -> TimetableValidationResult:
        values = sorted(
            list(sections),
            key=lambda section: (section.course_id, section.section_id),
        )
        violations: list[TimetableViolation] = []
        required = set(required_course_ids)
        excluded = set(excluded_course_ids)
        selected_course_ids = [section.course_id for section in values]
        selected_course_id_set = set(selected_course_ids)

        duplicate_course_ids = sorted(
            {course_id for course_id in selected_course_ids if selected_course_ids.count(course_id) > 1}
        )
        for course_id in duplicate_course_ids:
            violations.append(TimetableViolation(
                code=TimetableViolationCode.DUPLICATE_COURSE,
                message="같은 과목의 분반이 둘 이상 포함되어 있습니다.",
                course_id=course_id,
                conflicting_section_ids=[
                    section.section_id for section in values if section.course_id == course_id
                ],
            ))

        for course_id in sorted(required - selected_course_id_set):
            violations.append(TimetableViolation(
                code=TimetableViolationCode.MISSING_REQUIRED_COURSE,
                message="필수 과목이 시간표에 포함되지 않았습니다.",
                course_id=course_id,
                constraint="required_course_ids",
            ))

        for section in values:
            if section.course_id in excluded:
                violations.append(TimetableViolation(
                    code=TimetableViolationCode.EXCLUDED_COURSE_INCLUDED,
                    message="제외 과목이 시간표에 포함되어 있습니다.",
                    course_id=section.course_id,
                    section_id=section.section_id,
                    constraint="excluded_course_ids",
                ))
            violations.extend(self._single_section_violations(
                section,
                required_free_days=required_free_days,
                earliest_start_time=earliest_start_time,
                latest_end_time=latest_end_time,
                department=department,
            ))

        courses_by_section_id = {
            section.section_id: _section_to_course(section) for section in values
        }
        for first, second in combinations(values, 2):
            if first.course_id == second.course_id:
                continue
            if courses_by_section_id[first.section_id].conflicts_with(
                courses_by_section_id[second.section_id]
            ):
                violations.append(TimetableViolation(
                    code=TimetableViolationCode.TIME_CONFLICT,
                    message="두 분반의 수업 시간이 겹칩니다.",
                    course_id=second.course_id,
                    section_id=second.section_id,
                    conflicting_section_ids=[first.section_id],
                ))

        validator_result = self._validator.validate(courses_by_section_id.values())
        for issue in validator_result.issues:
            if issue.code != "TRAVEL_NOT_POSSIBLE":
                continue
            violations.append(TimetableViolation(
                code=TimetableViolationCode.CAMPUS_MOVEMENT_VIOLATION,
                message=issue.message,
                conflicting_section_ids=list(issue.course_ids),
            ))

        return TimetableValidationResult(
            valid=not violations,
            violations=violations,
            checked_section_ids=[section.section_id for section in values],
        )

    def can_add_section(
        self,
        current: Iterable[CourseSection],
        section: CourseSection,
        **kwargs: object,
    ) -> TimetableValidationResult:
        return self.validate_sections([*current, section], **kwargs)

    def _single_section_violations(
        self,
        section: CourseSection,
        *,
        required_free_days: Iterable[object],
        earliest_start_time: str | None,
        latest_end_time: str | None,
        department: str | None,
    ) -> list[TimetableViolation]:
        violations: list[TimetableViolation] = []
        free_days = set(required_free_days)
        if free_days and any(meeting.day in free_days for meeting in section.class_times):
            violations.append(TimetableViolation(
                code=TimetableViolationCode.REQUIRED_FREE_DAY_VIOLATION,
                message="필수 공강일에 수업이 있습니다.",
                course_id=section.course_id,
                section_id=section.section_id,
                constraint="required_free_days",
            ))
        if earliest_start_time is not None:
            earliest = time_to_minutes(earliest_start_time)
            if any(meeting.start_minutes < earliest for meeting in section.class_times):
                violations.append(TimetableViolation(
                    code=TimetableViolationCode.EARLIEST_START_VIOLATION,
                    message="가장 이른 시작 시간 조건보다 먼저 시작하는 수업이 있습니다.",
                    course_id=section.course_id,
                    section_id=section.section_id,
                    constraint="earliest_start_time",
                ))
        if latest_end_time is not None:
            latest = time_to_minutes(latest_end_time)
            if any(meeting.end_minutes > latest for meeting in section.class_times):
                violations.append(TimetableViolation(
                    code=TimetableViolationCode.LATEST_END_VIOLATION,
                    message="가장 늦은 종료 시간 조건보다 늦게 끝나는 수업이 있습니다.",
                    course_id=section.course_id,
                    section_id=section.section_id,
                    constraint="latest_end_time",
                ))
        if department:
            decision = self.restriction_policy.evaluate(
                _section_to_course(section),
                department=department,
            )
            if not decision.allows_course:
                violations.append(TimetableViolation(
                    code=TimetableViolationCode.DEPARTMENT_INELIGIBLE,
                    message=decision.reason,
                    course_id=section.course_id,
                    section_id=section.section_id,
                    constraint="department",
                ))
        return violations


def _section_to_course(section: CourseSection) -> Course:
    return Course(
        course_id=section.section_id,
        course_name=section.course_name,
        category=section.category,
        area=section.area,
        credit=section.credit,
        division=section.division,
        professor=section.professor,
        class_times=section.class_times,
    )
