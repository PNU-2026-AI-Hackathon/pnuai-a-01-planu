"""Tests for recommendation course-load targets and interpretation."""

from __future__ import annotations

import inspect

import pytest
from pydantic import ValidationError

from backend.app.models import Category, ClassTime, Course, CourseLoadTarget, Day
from backend.app.services.course_load_calculator import calculate_course_load_target


def _course(
    course_id: str,
    *,
    category: Category,
    credit: float = 3,
    day: Day = Day.MON,
    area: int | None = None,
) -> Course:
    return Course(
        course_id=course_id,
        course_name=f"강의 {course_id}",
        category=category,
        area=area,
        credit=credit,
        division="001",
        professor="김교수",
        class_times=[
            ClassTime(
                day=day,
                start="09:00",
                end="10:00",
                classroom="강의실",
                building_code="A",
            )
        ],
    )


def _major(course_id: str = "MAJ-001", *, credit: float = 6) -> Course:
    return _course(course_id, category=Category.MAJOR_REQUIRED, credit=credit)


def _required(course_id: str, *, credit: float = 2) -> Course:
    return _course(course_id, category=Category.GENERAL_REQUIRED, credit=credit)


def test_course_load_target_accepts_both_fields() -> None:
    target = CourseLoadTarget(
        target_total_credits=18,
        additional_elective_count=2,
    )

    assert target.target_total_credits == 18
    assert target.additional_elective_count == 2


@pytest.mark.parametrize(
    "payload",
    [
        {"target_total_credits": 0},
        {"target_total_credits": -1},
        {"additional_elective_count": -1},
        {"unknown": 1},
    ],
)
def test_course_load_target_rejects_invalid_values(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        CourseLoadTarget(**payload)


def test_without_target_calculates_base_major_and_required_general_credits() -> None:
    result = calculate_course_load_target(
        fixed_major_courses=[_major(credit=6)],
        required_general_courses=[
            _required("REQ-001", credit=2),
            _required("REQ-002", credit=1),
        ],
    )

    assert result.fixed_major_credits == 6
    assert result.required_general_credits == 3
    assert result.base_total_credits == 9
    assert result.target_total_credits is None
    assert result.remaining_elective_credit_capacity is None
    assert result.additional_elective_count is None
    assert result.warnings == []


def test_required_general_credits_are_kept_when_base_exceeds_target() -> None:
    result = calculate_course_load_target(
        fixed_major_courses=[_major(credit=10)],
        required_general_courses=[_required("REQ-001", credit=3)],
        target=CourseLoadTarget(target_total_credits=12, additional_elective_count=1),
    )

    assert result.fixed_major_credits == 10
    assert result.required_general_credits == 3
    assert result.base_total_credits == 13
    assert result.remaining_elective_credit_capacity == 0
    assert [warning.code for warning in result.warnings] == [
        "REQUIRED_COURSES_EXCEED_TARGET",
        "ELECTIVE_CREDIT_CAPACITY_UNAVAILABLE",
    ]


def test_remaining_elective_credit_capacity_is_calculated_from_base_total() -> None:
    result = calculate_course_load_target(
        fixed_major_courses=[_major(credit=9)],
        required_general_courses=[_required("REQ-001", credit=2)],
        target=CourseLoadTarget(target_total_credits=17),
    )

    assert result.base_total_credits == 11
    assert result.remaining_elective_credit_capacity == 6


def test_target_total_and_elective_count_are_preserved_together() -> None:
    result = calculate_course_load_target(
        fixed_major_courses=[_major(credit=9)],
        required_general_courses=[_required("REQ-001", credit=2)],
        target=CourseLoadTarget(target_total_credits=18, additional_elective_count=2),
    )

    assert result.target_total_credits == 18
    assert result.remaining_elective_credit_capacity == 7
    assert result.additional_elective_count == 2
    assert result.warnings == []


def test_calculator_signature_has_no_elective_course_list_input() -> None:
    signature = inspect.signature(calculate_course_load_target)

    assert list(signature.parameters) == [
        "fixed_major_courses",
        "required_general_courses",
        "target",
    ]
    assert "selected_required_general_courses" not in signature.parameters
    assert "selected_elective_general_courses" not in signature.parameters


def test_required_general_input_contract_is_one_course_per_requirement() -> None:
    """Do not pass every section of the same required general course here."""

    first = calculate_course_load_target(
        fixed_major_courses=[_major(credit=9)],
        required_general_courses=[
            _required("REQ-001", credit=2),
            _required("REQ-002", credit=1),
        ],
        target=CourseLoadTarget(target_total_credits=18, additional_elective_count=2),
    )
    second = calculate_course_load_target(
        fixed_major_courses=[_major(credit=9)],
        required_general_courses=[
            _required("REQ-002", credit=1),
            _required("REQ-001", credit=2),
        ],
        target=CourseLoadTarget(target_total_credits=18, additional_elective_count=2),
    )

    assert second.model_dump() == first.model_dump()


def test_calculation_result_does_not_include_selected_course_lists() -> None:
    result = calculate_course_load_target(
        fixed_major_courses=[_major()],
        required_general_courses=[_required("REQ-001")],
    )

    dumped = result.model_dump()

    assert "selected_required_general_courses" not in dumped
    assert "selected_elective_general_courses" not in dumped
    assert not hasattr(result, "selected_required_general_courses")
    assert not hasattr(result, "selected_elective_general_courses")
