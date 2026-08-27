from __future__ import annotations

from backend.app.models.course import Category, ClassTime, Course, Day
from backend.app.services.campus_rule_engine import CampusRuleEngine
from backend.app.services.timetable_validator import TimetableValidator


def _course(
    course_id: str,
    name: str,
    *,
    start: str,
    end: str,
    classroom: str,
    building_code: str,
) -> Course:
    return Course(
        course_id=course_id,
        course_name=name,
        category=Category.GENERAL_ELECTIVE,
        area=1,
        credit=3,
        division=course_id.rsplit("-", 1)[-1],
        professor="교수",
        class_times=[
            ClassTime(
                day=Day.MON,
                start=start,
                end=end,
                classroom=classroom,
                building_code=building_code,
            )
        ],
    )


def test_default_campus_rule_blocks_buildings_when_first_digits_differ_by_three() -> None:
    first = _course(
        "A-001",
        "첫수업",
        start="09:00",
        end="10:00",
        classroom="401-101",
        building_code="401",
    )
    second = _course(
        "B-001",
        "다음수업",
        start="11:00",
        end="12:00",
        classroom="701-101",
        building_code="701",
    )

    result = TimetableValidator().validate([first, second])

    assert result.valid is False
    assert result.issues[0].code == "TRAVEL_NOT_POSSIBLE"
    assert "강의실 번호 앞자리 차이가 3 이상" in result.issues[0].message


def test_default_campus_rule_allows_buildings_when_first_digits_are_close() -> None:
    first = _course(
        "A-001",
        "첫수업",
        start="09:00",
        end="10:00",
        classroom="401-101",
        building_code="401",
    )
    second = _course(
        "B-001",
        "다음수업",
        start="11:00",
        end="12:00",
        classroom="601-101",
        building_code="601",
    )

    assert TimetableValidator().validate([first, second]).valid is True


def test_campus_rule_engine_ignores_first_digit_rule_without_numeric_codes() -> None:
    assert CampusRuleEngine().can_travel("A", "D", 0) is True


def test_total_credit_below_minimum_creates_validation_issue() -> None:
    course = _course("A-001", "수업", start="09:00", end="10:00", classroom="401-101", building_code="401")
    result = TimetableValidator().validate([course], min_credit=6)
    assert result.valid is False
    assert [issue.code for issue in result.issues] == ["CREDIT_BELOW_MINIMUM"]


def test_total_credit_above_maximum_creates_validation_issue() -> None:
    course = _course("A-001", "수업", start="09:00", end="10:00", classroom="401-101", building_code="401")
    result = TimetableValidator().validate([course], max_credit=2)
    assert result.valid is False
    assert [issue.code for issue in result.issues] == ["CREDIT_ABOVE_MAXIMUM"]


def test_total_credit_inside_range_has_no_credit_issue() -> None:
    course = _course("A-001", "수업", start="09:00", end="10:00", classroom="401-101", building_code="401")
    result = TimetableValidator().validate([course], min_credit=3, max_credit=3)
    assert result.valid is True


def test_omitted_credit_bound_does_not_apply_that_direction() -> None:
    course = _course("A-001", "수업", start="09:00", end="10:00", classroom="401-101", building_code="401")

    no_upper = TimetableValidator().validate([course], min_credit=3)
    no_lower = TimetableValidator().validate([course], max_credit=3)

    assert no_upper.valid is True
    assert no_lower.valid is True


def test_validator_credit_bounds_reject_negative_and_inverted_values() -> None:
    try:
        TimetableValidator(min_credit=-1)
    except ValueError as exc:
        assert str(exc) == "min_credit must not be negative"
    else:
        raise AssertionError("negative min_credit should be rejected")

    try:
        TimetableValidator(max_credit=-1)
    except ValueError as exc:
        assert str(exc) == "max_credit must not be negative"
    else:
        raise AssertionError("negative max_credit should be rejected")

    try:
        TimetableValidator(min_credit=4, max_credit=3)
    except ValueError as exc:
        assert str(exc) == "min_credit must not exceed max_credit"
    else:
        raise AssertionError("inverted credit range should be rejected")
