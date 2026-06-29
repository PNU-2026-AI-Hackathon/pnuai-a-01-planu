"""Examples and regression tests for the PlaNU domain models."""

import pytest
from pydantic import ValidationError

from backend.app.models import (
    Category,
    ClassTime,
    Course,
    Day,
    InputTimetable,
    PreferenceRules,
    Timetable,
    time_to_minutes,
)


@pytest.fixture
def major_course() -> Course:
    """A realistic course object shared by timetable tests."""

    return Course(
        course_id="MAJ001-001",
        course_name="컴퓨터프로그래밍",
        category=Category.MAJOR_BASIC,
        credit=3,
        division="001",
        professor="김교수",
        class_times=[
            ClassTime(
                day=Day.MON,
                start="09:00",
                end="10:15",
                classroom="제6공학관 6201",
                building_code="6201",
            )
        ],
    )


@pytest.fixture
def general_course() -> Course:
    return Course(
        course_id="GEN001-023",
        course_name="고전읽기와토론",
        category=Category.GENERAL_REQUIRED,
        credit=2,
        division="023",
        professor="박교수",
        class_times=[
            ClassTime(
                day=Day.TUE,
                start="10:30",
                end="11:45",
                classroom="인문관 301",
                building_code="301",
            )
        ],
    )


def test_time_to_minutes() -> None:
    assert time_to_minutes("09:00") == 540
    assert time_to_minutes("10:15") == 615


@pytest.mark.parametrize("invalid_time", ["9:00", "24:00", "10:60", "오전 9시"])
def test_invalid_time_is_rejected(invalid_time: str) -> None:
    with pytest.raises(ValueError):
        time_to_minutes(invalid_time)


def test_class_time_overlap_allows_touching_endpoints() -> None:
    first = ClassTime(
        day="MON",
        start="09:00",
        end="10:15",
        classroom="A101",
        building_code="A",
    )
    touching = ClassTime(
        day="MON",
        start="10:15",
        end="11:30",
        classroom="B201",
        building_code="B",
    )
    overlapping = ClassTime(
        day="MON",
        start="10:00",
        end="11:00",
        classroom="C301",
        building_code="C",
    )

    assert first.overlaps(touching) is False
    assert first.overlaps(overlapping) is True


def test_class_end_must_be_later_than_start() -> None:
    with pytest.raises(ValidationError, match="later than start"):
        ClassTime(
            day="FRI",
            start="11:00",
            end="10:00",
            classroom="A101",
            building_code="A",
        )


def test_general_elective_requires_area() -> None:
    with pytest.raises(ValidationError, match="must specify an area"):
        Course(
            course_id="GEN-E-001",
            course_name="교양선택 예시",
            category="GENERAL_ELECTIVE",
            credit=3,
            division="001",
            professor="이교수",
            class_times=[
                {
                    "day": "WED",
                    "start": "13:00",
                    "end": "14:15",
                    "classroom": "A101",
                    "building_code": "A",
                }
            ],
        )


def test_empty_preference_rules_are_safe_fallback() -> None:
    rules = PreferenceRules()

    assert rules.preferred_free_days == []
    assert rules.avoid_morning_classes is False
    assert rules.morning_end_time == "10:00"


def test_preference_rules_validate_and_deduplicate_values() -> None:
    rules = PreferenceRules(
        preferred_free_days=["FRI", "FRI"],
        preferred_elective_areas=[1, 3, 3],
        earliest_start_time="10:00",
        latest_end_time="18:00",
    )

    assert rules.preferred_free_days == [Day.FRI]
    assert rules.preferred_elective_areas == [1, 3]


def test_timetable_calculates_credit_and_sorts_schedule(
    major_course: Course, general_course: Course
) -> None:
    # TUE course is intentionally supplied first; output must be MON then TUE.
    timetable = Timetable(courses=[general_course, major_course], score=92, rank=1)

    assert timetable.total_credit == 5
    assert [item.day for item in timetable.schedule_items] == [Day.MON, Day.TUE]
    assert timetable.schedule_items[0].course_name == "컴퓨터프로그래밍"
    assert timetable.model_dump(mode="json")["score"] == 92.0


def test_timetable_rejects_incorrect_total_credit(major_course: Course) -> None:
    with pytest.raises(ValidationError, match="sum of course credits"):
        Timetable(courses=[major_course], total_credit=2)


def test_timetable_rejects_duplicate_courses(major_course: Course) -> None:
    with pytest.raises(ValidationError, match="duplicate course_id"):
        Timetable(courses=[major_course, major_course])


def test_input_timetable_calculates_credit_and_schedule_items(
    major_course: Course, general_course: Course
) -> None:
    timetable = InputTimetable(courses=[general_course, major_course])

    assert timetable.total_credit == 5
    assert [item.day for item in timetable.schedule_items] == [Day.MON, Day.TUE]
    assert set(InputTimetable.model_fields) == {
        "courses",
        "total_credit",
        "schedule_items",
    }


def test_input_timetable_rejects_duplicate_course_id(major_course: Course) -> None:
    duplicate = major_course.model_copy(update={"course_name": "중복 과목"})

    with pytest.raises(ValidationError, match="duplicate course_id"):
        InputTimetable(courses=[major_course, duplicate])


def test_input_timetable_rejects_time_conflict(major_course: Course) -> None:
    conflicting = Course(
        course_id="MAJ002-001",
        course_name="컴퓨팅사고와인공지능",
        category=Category.MAJOR_REQUIRED,
        credit=3,
        division="001",
        professor="이교수",
        class_times=[
            ClassTime(
                day=Day.MON,
                start="10:00",
                end="11:15",
                classroom="제6공학관 6301",
                building_code="6301",
            )
        ],
    )

    with pytest.raises(ValidationError, match="time conflict.*MAJ001-001.*MAJ002-001"):
        InputTimetable(courses=[major_course, conflicting])

    # Recommendation candidates are validated later by the backtracking service.
    assert Timetable(courses=[major_course, conflicting]).total_credit == 6


def test_input_timetable_rejects_incorrect_total_credit(
    major_course: Course,
) -> None:
    with pytest.raises(ValidationError, match="sum of course credits"):
        InputTimetable(courses=[major_course], total_credit=2)


def test_input_timetable_has_no_recommendation_fields(major_course: Course) -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        InputTimetable(courses=[major_course], rank=1)
