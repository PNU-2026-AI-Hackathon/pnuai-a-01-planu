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
    course_name: str | None = None,
    day: Day = Day.MON,
    start: str = "11:00",
    end: str = "12:00",
    professor: str = "김교수",
) -> Course:
    return Course(
        course_id=course_id,
        course_name=course_name or f"강의 {course_id}",
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
        preferred_first_class_time="10:00",
        minimize_attendance_days=True,
        minimize_consecutive_classes=True,
        compact_schedule=True,
    )

    ranked = rank_timetables([candidate], preferences=preferences)

    assert ranked[0].raw_score > 100
    assert ranked[0].raw_score == sum(
        component.value for component in ranked[0].score_components
    )
    assert ranked[0].timetable.score == ranked[0].raw_score


def test_preferred_first_class_time_penalizes_early_start_without_filtering() -> None:
    courses = [
        _course(f"GEN-LOW-{index}", start="08:00", end="09:00")
        for index in range(20)
    ]
    candidate = Timetable(courses=courses)

    ranked = rank_timetables(
        [candidate],
        preferences=PreferenceRules(preferred_first_class_time="10:00"),
    )

    detail = [
        item
        for item in ranked[0].score_components
        if item.key == "preferred_first_class_time"
    ][0]
    assert detail.value < 0
    assert ranked[0].raw_score == sum(
        component.value for component in ranked[0].score_components
    )


def test_hard_condition_filters_candidate_before_ranking() -> None:
    morning = Timetable(courses=[_course("GEN-MORNING", start="09:00", end="10:00")])
    afternoon = Timetable(courses=[_course("GEN-AFTERNOON", start="13:00", end="14:00")])

    ranked = rank_timetables(
        [morning, afternoon],
        preferences=PreferenceRules(earliest_start_time="10:00"),
    )

    assert [course.course_id for course in ranked[0].timetable.courses] == ["GEN-AFTERNOON"]
    assert len(ranked) == 1


def test_ui_and_llm_duplicate_conditions_are_applied_once() -> None:
    preferences = merge_preference_rules(
        PreferenceRules(preferred_first_class_time="10:00"),
        PreferenceRules(preferred_first_class_time="10:00"),
    )
    candidate = Timetable(courses=[_course("GEN-MORNING", start="09:00", end="10:00")])

    ranked = rank_timetables([candidate], preferences=preferences)
    details = [
        detail
        for detail in ranked[0].score_components
        if detail.key == "preferred_first_class_time"
    ]

    assert len(details) == 1


def test_ui_condition_wins_when_llm_condition_conflicts() -> None:
    preferences = merge_preference_rules(
        PreferenceRules(earliest_start_time=None),
        PreferenceRules(earliest_start_time="10:00"),
    )
    candidate = Timetable(courses=[_course("GEN-MORNING", start="09:00", end="10:00")])

    ranked = rank_timetables([candidate], preferences=preferences)

    assert len(ranked) == 1
    assert ranked[0].timetable.courses[0].course_id == "GEN-MORNING"


def test_score_components_sum_matches_raw_score() -> None:
    candidate = Timetable(courses=[_course("GEN-SUM", day=Day.TUE)])
    preferences = PreferenceRules(
        preferred_free_days=[Day.FRI],
        preferred_first_class_time="10:00",
        compact_schedule=True,
    )

    ranked = rank_timetables([candidate], preferences=preferences)

    assert ranked[0].raw_score == sum(
        component.value for component in ranked[0].score_components
    )
    assert ranked[0].score_components[0].key == "valid_candidate"


def test_required_and_excluded_course_names_are_hard_filters() -> None:
    required = Timetable(
        courses=[_course("GEN-REQ", course_name="대학영어")]
    )
    other = Timetable(
        courses=[_course("GEN-OTHER", course_name="고전읽기와토론")]
    )

    ranked = rank_timetables(
        [required, other],
        preferences=PreferenceRules(required_course_names=["대학영어"]),
        top_n=2,
    )

    assert len(ranked) == 1
    assert ranked[0].timetable.courses[0].course_name == "대학영어"

    ranked = rank_timetables(
        [required, other],
        preferences=PreferenceRules(excluded_course_names=["대학영어"]),
        top_n=2,
    )

    assert len(ranked) == 1
    assert ranked[0].timetable.courses[0].course_name == "고전읽기와토론"


def test_same_input_always_produces_same_sort_order() -> None:
    first = Timetable(courses=[_course("GEN-B", start="11:00", end="12:00")])
    second = Timetable(courses=[_course("GEN-A", start="11:00", end="12:00")])
    preferences = PreferenceRules(compact_schedule=True)

    first_run = rank_timetables([first, second], preferences=preferences, top_n=2)
    second_run = rank_timetables([first, second], preferences=preferences, top_n=2)

    assert [item.timetable.courses[0].course_id for item in first_run] == [
        item.timetable.courses[0].course_id for item in second_run
    ]
    assert [item.timetable.courses[0].course_id for item in first_run] == ["GEN-A", "GEN-B"]


def test_score_components_include_positive_reward_negative_penalty_and_reasons() -> None:
    candidate = Timetable(courses=[_course("GEN-MIX", day=Day.MON, start="08:00", end="09:00")])
    preferences = PreferenceRules(
        preferred_free_days=[Day.FRI, Day.MON],
        preferred_first_class_time="10:00",
    )

    ranked = rank_timetables([candidate], preferences=preferences)
    components = ranked[0].score_components

    assert any(component.value > 0 for component in components)
    assert any(component.value < 0 for component in components)
    assert all(component.reason for component in components)
    assert any("공강 선호를 만족합니다" in component.reason for component in components)
    assert any("일찍 시작합니다" in component.reason for component in components)
