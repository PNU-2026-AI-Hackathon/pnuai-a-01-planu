"""Regression tests for preference filtering and ranking."""

from __future__ import annotations

from backend.app.models import (
    Category,
    ClassTime,
    Course,
    Day,
    PreferenceRules,
    Timetable,
    merge_preference_rules,
)
from backend.app.services.timetable_ranker import rank_timetables


def _course(
    course_id: str,
    *,
    day: Day = Day.MON,
    start: str = "11:00",
    end: str = "12:00",
    professor: str = "김교수",
) -> Course:
    return Course(
        course_id=course_id,
        course_name=f"강의 {course_id}",
        category=Category.GENERAL_REQUIRED,
        credit=1,
        division="001",
        professor=professor,
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


def test_score_can_exceed_100_without_clamping() -> None:
    candidate = Timetable(courses=[_course("GEN-HIGH", day=Day.TUE)])
    preferences = PreferenceRules(
        preferred_free_days=[Day.MON, Day.WED, Day.THU, Day.FRI],
        avoid_morning_classes=True,
        prefer_late_start=True,
        minimize_attendance_days=True,
        minimize_consecutive_classes=True,
        compact_schedule=True,
    )

    ranked = rank_timetables([candidate], preferences=preferences)

    assert ranked[0].score > 100
    assert ranked[0].score == sum(detail.value for detail in ranked[0].score_details)


def test_score_can_be_negative_without_clamping() -> None:
    courses = [
        _course(f"GEN-LOW-{index}", start="08:00", end="09:00")
        for index in range(20)
    ]
    candidate = Timetable(courses=courses)

    ranked = rank_timetables(
        [candidate],
        preferences=PreferenceRules(avoid_morning_classes=True),
    )

    assert ranked[0].score < 0
    assert ranked[0].score == sum(detail.value for detail in ranked[0].score_details)


def test_hard_condition_filters_candidate_before_ranking() -> None:
    morning = Timetable(courses=[_course("GEN-MORNING", start="09:00", end="10:00")])
    afternoon = Timetable(courses=[_course("GEN-AFTERNOON", start="13:00", end="14:00")])

    ranked = rank_timetables(
        [morning, afternoon],
        preferences=PreferenceRules(no_morning_classes=True),
    )

    assert [course.course_id for course in ranked[0].courses] == ["GEN-AFTERNOON"]
    assert len(ranked) == 1


def test_ui_and_llm_duplicate_conditions_are_applied_once() -> None:
    preferences = merge_preference_rules(
        PreferenceRules(avoid_morning_classes=True),
        PreferenceRules(avoid_morning_classes=True),
    )
    candidate = Timetable(courses=[_course("GEN-MORNING", start="09:00", end="10:00")])

    ranked = rank_timetables([candidate], preferences=preferences)
    morning_details = [
        detail for detail in ranked[0].score_details if detail.key == "morning_class"
    ]

    assert len(morning_details) == 1
    assert morning_details[0].value == -4


def test_ui_condition_wins_when_llm_condition_conflicts() -> None:
    preferences = merge_preference_rules(
        PreferenceRules(no_morning_classes=False),
        PreferenceRules(no_morning_classes=True),
    )
    candidate = Timetable(courses=[_course("GEN-MORNING", start="09:00", end="10:00")])

    ranked = rank_timetables([candidate], preferences=preferences)

    assert len(ranked) == 1
    assert ranked[0].courses[0].course_id == "GEN-MORNING"


def test_score_details_sum_matches_final_score() -> None:
    candidate = Timetable(courses=[_course("GEN-SUM", day=Day.TUE)])
    preferences = PreferenceRules(
        preferred_free_days=[Day.FRI],
        avoid_morning_classes=True,
        compact_schedule=True,
    )

    ranked = rank_timetables([candidate], preferences=preferences)

    assert ranked[0].score == sum(detail.value for detail in ranked[0].score_details)
    assert ranked[0].score_details[0].key == "valid_candidate"


def test_same_input_always_produces_same_sort_order() -> None:
    first = Timetable(courses=[_course("GEN-B", start="11:00", end="12:00")])
    second = Timetable(courses=[_course("GEN-A", start="11:00", end="12:00")])
    preferences = PreferenceRules(compact_schedule=True)

    first_run = rank_timetables([first, second], preferences=preferences, top_n=2)
    second_run = rank_timetables([first, second], preferences=preferences, top_n=2)

    assert [item.courses[0].course_id for item in first_run] == [
        item.courses[0].course_id for item in second_run
    ]
    assert [item.courses[0].course_id for item in first_run] == ["GEN-A", "GEN-B"]
