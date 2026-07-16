"""Interpret course-load targets and calculate credit capacity.

This service is deliberately limited to credit arithmetic and structured goal
warnings. It does not generate actual general-course combinations, inspect time
conflicts, check campus travel feasibility, or prevent multiple sections of the
same course from being selected. Those responsibilities belong to the future
backtracking engine, which will group available sections at the course level.
"""

from __future__ import annotations

from collections.abc import Iterable

from ..models.course import Course
from ..models.course_load import (
    CourseLoadCalculationResult,
    CourseLoadTarget,
    CourseLoadWarning,
)


def calculate_course_load_target(
    *,
    fixed_major_courses: Iterable[Course],
    required_general_courses: Iterable[Course] = (),
    target: CourseLoadTarget | None = None,
) -> CourseLoadCalculationResult:
    """Return the credit goals that backtracking should optimize against.

    ``required_general_courses`` is not a list of every available required
    general-course section. It must contain one representative ``Course`` per
    required general course, or an already-fixed course, as determined by
    department rules. Passing multiple sections of the same course would count
    credits multiple times and violates this function's input contract.

    When both goals are present, the policy is: stay within the target total
    credits if possible while satisfying ``additional_elective_count`` as much
    as possible. This function expresses that policy as remaining credit
    capacity and warnings; it does not choose actual required or elective
    sections.
    """

    resolved_target = target or CourseLoadTarget()
    fixed_major_credits = _sum_credits(fixed_major_courses)
    required_general_credits = _sum_credits(required_general_courses)
    base_total_credits = fixed_major_credits + required_general_credits
    target_total_credits = resolved_target.target_total_credits
    remaining_capacity = (
        None
        if target_total_credits is None
        else max(target_total_credits - base_total_credits, 0)
    )
    warnings = _build_warnings(
        fixed_major_credits=fixed_major_credits,
        required_general_credits=required_general_credits,
        base_total_credits=base_total_credits,
        target_total_credits=target_total_credits,
        additional_elective_count=resolved_target.additional_elective_count,
        remaining_elective_credit_capacity=remaining_capacity,
    )

    return CourseLoadCalculationResult(
        target=resolved_target,
        fixed_major_credits=fixed_major_credits,
        required_general_credits=required_general_credits,
        base_total_credits=base_total_credits,
        target_total_credits=target_total_credits,
        remaining_elective_credit_capacity=remaining_capacity,
        additional_elective_count=resolved_target.additional_elective_count,
        warnings=warnings,
    )


def _sum_credits(courses: Iterable[Course]) -> float:
    return sum(course.credit for course in courses)


def _build_warnings(
    *,
    fixed_major_credits: float,
    required_general_credits: float,
    base_total_credits: float,
    target_total_credits: float | None,
    additional_elective_count: int | None,
    remaining_elective_credit_capacity: float | None,
) -> list[CourseLoadWarning]:
    if target_total_credits is None:
        return []

    warnings: list[CourseLoadWarning] = []

    if base_total_credits > target_total_credits and required_general_credits > 0:
        warnings.append(
            CourseLoadWarning(
                code="REQUIRED_COURSES_EXCEED_TARGET",
                message=(
                    f"확정 전공과 교양필수 학점 합계 {base_total_credits:g}이 "
                    f"목표 총학점 {target_total_credits:g}을 초과합니다. "
                    "교양필수는 유지하고 교양선택 학점 용량을 0으로 계산합니다."
                ),
                reason="required_courses_exceed_target",
            )
        )
    elif fixed_major_credits >= target_total_credits:
        warnings.append(
            CourseLoadWarning(
                code="FIXED_MAJOR_CREDITS_MEET_OR_EXCEED_TARGET",
                message=(
                    f"확정 전공 학점 {fixed_major_credits:g}이 목표 총학점 "
                    f"{target_total_credits:g} 이상입니다. "
                    "교양선택 학점 용량을 0으로 계산합니다."
                ),
                reason="fixed_major_credits_meet_or_exceed_target",
            )
        )

    if additional_elective_count and remaining_elective_credit_capacity == 0:
        warnings.append(
            CourseLoadWarning(
                code="ELECTIVE_CREDIT_CAPACITY_UNAVAILABLE",
                message=(
                    f"교양선택 {additional_elective_count}개가 요청되었지만 "
                    "목표 총학점까지 남은 학점 용량이 없습니다."
                ),
                requested_elective_count=additional_elective_count,
                reason="no_remaining_elective_credit_capacity",
            )
        )

    return warnings
