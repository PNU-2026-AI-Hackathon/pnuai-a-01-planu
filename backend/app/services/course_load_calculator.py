"""Course-load target calculation for recommendation planning."""

from __future__ import annotations

from collections.abc import Iterable

from ..models.course import Course
from ..models.course_load import (
    CourseLoadCalculationResult,
    CourseLoadTarget,
    CourseLoadWarning,
)
from .timetable_validator import TimetableValidator


def calculate_course_load_target(
    *,
    fixed_major_courses: Iterable[Course],
    general_required_candidates: Iterable[Course] = (),
    general_elective_candidates: Iterable[Course] = (),
    target: CourseLoadTarget | None = None,
    validator: TimetableValidator | None = None,
) -> CourseLoadCalculationResult:
    """Select feasible general courses under a course-load target.

    Required general courses are considered before elective general courses.
    When the requested elective count conflicts with the credit target, the
    credit target wins and the elective count is satisfied as far as possible.
    """

    resolved_target = target or CourseLoadTarget()
    fixed = list(fixed_major_courses)
    checker = validator or TimetableValidator()
    fixed_credit = sum(course.credit for course in fixed)
    credit_limit = resolved_target.target_total_credits
    warnings: list[CourseLoadWarning] = []

    if credit_limit is not None and fixed_credit >= credit_limit:
        warnings.append(
            CourseLoadWarning(
                code="FIXED_CREDITS_MEET_OR_EXCEED_TARGET",
                message=(
                    f"확정 전공 학점 {fixed_credit:g}이 목표 총학점 "
                    f"{credit_limit:g} 이상이어서 교양을 추가하지 않습니다."
                ),
                reason="fixed_credits_meet_or_exceed_target",
            )
        )
        return CourseLoadCalculationResult(
            target=resolved_target,
            fixed_major_credits=fixed_credit,
            target_total_credits=credit_limit,
            final_total_credits=fixed_credit,
            remaining_credit_capacity=0,
            warnings=warnings,
        )

    selected_required = _select_feasible_courses(
        candidates=general_required_candidates,
        fixed_courses=fixed,
        already_selected=[],
        validator=checker,
        credit_limit=credit_limit,
    )

    desired_elective_count = resolved_target.additional_elective_count
    elective_max_count = (
        desired_elective_count
        if desired_elective_count is not None
        else None if credit_limit is not None else 0
    )
    selected_elective = _select_feasible_courses(
        candidates=general_elective_candidates,
        fixed_courses=fixed,
        already_selected=selected_required,
        validator=checker,
        credit_limit=credit_limit,
        max_count=elective_max_count,
    )

    if (
        desired_elective_count is not None
        and len(selected_elective) < desired_elective_count
    ):
        warnings.append(
            CourseLoadWarning(
                code="ELECTIVE_COUNT_NOT_FULFILLED",
                message=(
                    f"요청한 교양선택 {desired_elective_count}개 중 "
                    f"{len(selected_elective)}개만 포함할 수 있습니다."
                ),
                requested_elective_count=desired_elective_count,
                actual_elective_count=len(selected_elective),
                reason=_elective_shortfall_reason(
                    fixed_courses=fixed,
                    required_courses=selected_required,
                    elective_candidates=general_elective_candidates,
                    selected_electives=selected_elective,
                    validator=checker,
                    credit_limit=credit_limit,
                ),
            )
        )

    final_total = fixed_credit + sum(
        course.credit for course in [*selected_required, *selected_elective]
    )
    remaining_capacity = (
        None if credit_limit is None else max(credit_limit - final_total, 0)
    )

    return CourseLoadCalculationResult(
        target=resolved_target,
        fixed_major_credits=fixed_credit,
        target_total_credits=credit_limit,
        selected_required_general_courses=selected_required,
        selected_elective_general_courses=selected_elective,
        final_total_credits=final_total,
        remaining_credit_capacity=remaining_capacity,
        warnings=warnings,
    )


def _select_feasible_courses(
    *,
    candidates: Iterable[Course],
    fixed_courses: list[Course],
    already_selected: list[Course],
    validator: TimetableValidator,
    credit_limit: float | None,
    max_count: int | None = None,
) -> list[Course]:
    selected: list[Course] = []
    seen: set[tuple[str, str]] = set()

    for course in candidates:
        key = (course.course_id, course.division)
        if key in seen:
            continue
        seen.add(key)
        if max_count is not None and len(selected) >= max_count:
            break
        tentative = [*already_selected, *selected, course]
        if validator.is_valid(
            tentative,
            fixed_courses=fixed_courses,
            max_credit=credit_limit,
        ):
            selected.append(course)

    return selected


def _elective_shortfall_reason(
    *,
    fixed_courses: list[Course],
    required_courses: list[Course],
    elective_candidates: Iterable[Course],
    selected_electives: list[Course],
    validator: TimetableValidator,
    credit_limit: float | None,
) -> str:
    selected_keys = {
        (course.course_id, course.division) for course in selected_electives
    }
    rejected_by_credit = False
    rejected_by_constraints = False
    unselected_count = 0

    for course in elective_candidates:
        key = (course.course_id, course.division)
        if key in selected_keys:
            continue
        unselected_count += 1
        without_limit = validator.is_valid(
            [*required_courses, *selected_electives, course],
            fixed_courses=fixed_courses,
        )
        with_limit = validator.is_valid(
            [*required_courses, *selected_electives, course],
            fixed_courses=fixed_courses,
            max_credit=credit_limit,
        )
        if without_limit and not with_limit:
            rejected_by_credit = True
        elif not with_limit:
            rejected_by_constraints = True

    if unselected_count == 0:
        return "not_enough_candidates"
    if rejected_by_credit:
        return "credit_limit_reached"
    if rejected_by_constraints:
        return "course_constraints"
    return "not_enough_candidates"
