"""Tests for recommendation course-load targets and calculations."""

from __future__ import annotations

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
    start: str = "09:00",
    end: str = "10:00",
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
                start=start,
                end=end,
                classroom="강의실",
                building_code="A",
            )
        ],
    )


def _major(course_id: str = "MAJ-001", *, credit: float = 6) -> Course:
    return _course(course_id, category=Category.MAJOR_REQUIRED, credit=credit)


def _required(course_id: str, *, credit: float = 2, day: Day = Day.TUE) -> Course:
    return _course(
        course_id,
        category=Category.GENERAL_REQUIRED,
        credit=credit,
        day=day,
    )


def _elective(
    course_id: str,
    *,
    credit: float = 3,
    day: Day = Day.WED,
    start: str = "09:00",
    end: str = "10:00",
) -> Course:
    return _course(
        course_id,
        category=Category.GENERAL_ELECTIVE,
        area=1,
        credit=credit,
        day=day,
        start=start,
        end=end,
    )


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


def test_without_target_adds_required_general_only() -> None:
    result = calculate_course_load_target(
        fixed_major_courses=[_major()],
        general_required_candidates=[_required("REQ-001")],
        general_elective_candidates=[_elective("EL-001")],
    )

    assert [course.course_id for course in result.selected_required_general_courses] == [
        "REQ-001"
    ]
    assert result.selected_elective_general_courses == []
    assert result.final_total_credits == 8
    assert result.warnings == []


def test_required_general_candidates_are_prioritized_over_electives() -> None:
    result = calculate_course_load_target(
        fixed_major_courses=[_major(credit=10)],
        general_required_candidates=[_required("REQ-001", credit=2)],
        general_elective_candidates=[_elective("EL-001", credit=3)],
        target=CourseLoadTarget(target_total_credits=12, additional_elective_count=1),
    )

    assert [course.course_id for course in result.selected_required_general_courses] == [
        "REQ-001"
    ]
    assert result.selected_elective_general_courses == []
    assert result.final_total_credits == 12
    assert result.warnings[0].code == "ELECTIVE_COUNT_NOT_FULFILLED"
    assert result.warnings[0].requested_elective_count == 1
    assert result.warnings[0].actual_elective_count == 0
    assert result.warnings[0].reason == "credit_limit_reached"


def test_fixed_major_credits_at_target_returns_warning_without_generals() -> None:
    result = calculate_course_load_target(
        fixed_major_courses=[_major(credit=15)],
        general_required_candidates=[_required("REQ-001")],
        general_elective_candidates=[_elective("EL-001")],
        target=CourseLoadTarget(target_total_credits=15, additional_elective_count=1),
    )

    assert result.selected_required_general_courses == []
    assert result.selected_elective_general_courses == []
    assert result.final_total_credits == 15
    assert result.remaining_credit_capacity == 0
    assert result.warnings[0].code == "FIXED_CREDITS_MEET_OR_EXCEED_TARGET"


def test_elective_shortfall_reports_requested_actual_and_reason() -> None:
    result = calculate_course_load_target(
        fixed_major_courses=[_major(credit=9)],
        general_elective_candidates=[
            _elective("EL-001", credit=3, day=Day.WED),
            _elective("EL-002", credit=3, day=Day.THU),
        ],
        target=CourseLoadTarget(target_total_credits=12, additional_elective_count=2),
    )

    assert [course.course_id for course in result.selected_elective_general_courses] == [
        "EL-001"
    ]
    assert result.final_total_credits == 12
    assert result.warnings[0].requested_elective_count == 2
    assert result.warnings[0].actual_elective_count == 1
    assert result.warnings[0].reason == "credit_limit_reached"
