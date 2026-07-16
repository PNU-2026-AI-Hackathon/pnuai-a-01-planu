"""Regression tests for preference filtering and ranking."""

from __future__ import annotations

from backend.app.models import (
    Category,
    ClassTime,
    Course,
    Day,
    PreferenceTemplate,
    PreferenceRules,
    Timetable,
    merge_preference_rules,
)
from backend.app.services.timetable_ranker import (
    RankingWeights,
    build_ranking_weights,
    rank_timetables,
)


def _course(
    course_id: str,
    *,
    course_name: str | None = None,
    day: Day = Day.MON,
    start: str = "11:00",
    end: str = "12:00",
    professor: str = "김교수",
    category: Category = Category.GENERAL_REQUIRED,
    area: int | None = None,
) -> Course:
    return Course(
        course_id=course_id,
        course_name=course_name or f"강의 {course_id}",
        category=category,
        area=area,
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


def test_preferred_course_names_raise_matching_candidate_rank() -> None:
    preferred = Timetable(courses=[_course("GEN-A", course_name="대학영어")])
    other = Timetable(courses=[_course("GEN-B", course_name="고전읽기와토론")])

    ranked = rank_timetables(
        [other, preferred],
        preferences=PreferenceRules(preferred_course_names=["대학영어"]),
        top_n=2,
    )

    assert ranked[0].timetable.courses[0].course_name == "대학영어"
    assert ranked[0].raw_score > ranked[1].raw_score


def test_avoided_course_names_penalize_matching_candidate() -> None:
    avoided = Timetable(courses=[_course("GEN-A", course_name="고전읽기와토론")])
    other = Timetable(courses=[_course("GEN-B", course_name="대학영어")])

    ranked = rank_timetables(
        [avoided, other],
        preferences=PreferenceRules(avoided_course_names=["고전읽기와토론"]),
        top_n=2,
    )
    component = [
        item
        for item in ranked[1].score_components
        if item.key == "avoided_course"
    ][0]

    assert ranked[0].timetable.courses[0].course_name == "대학영어"
    assert component.value < 0


def test_more_preferred_free_time_ranges_satisfied_ranks_higher() -> None:
    satisfies_all = Timetable(courses=[_course("GEN-A", day=Day.MON)])
    satisfies_one = Timetable(courses=[_course("GEN-B", day=Day.TUE, start="09:00", end="10:00")])
    preferences = PreferenceRules(
        preferred_free_time_ranges=[
            {"day": Day.TUE, "start": "09:00", "end": "10:00"},
            {"day": Day.WED, "start": "09:00", "end": "10:00"},
        ]
    )

    ranked = rank_timetables([satisfies_one, satisfies_all], preferences=preferences, top_n=2)

    assert ranked[0].timetable.courses[0].course_id == "GEN-A"
    assert ranked[0].raw_score > ranked[1].raw_score


def test_preferred_elective_area_ranks_matching_candidate_higher() -> None:
    matching = Timetable(courses=[
        _course(
            "ELEC-A",
            category=Category.GENERAL_ELECTIVE,
            area=2,
        )
    ])
    other = Timetable(courses=[
        _course(
            "ELEC-B",
            category=Category.GENERAL_ELECTIVE,
            area=4,
        )
    ])

    ranked = rank_timetables(
        [other, matching],
        preferences=PreferenceRules(preferred_elective_areas=[2]),
        top_n=2,
    )

    assert ranked[0].timetable.courses[0].area == 2
    assert ranked[0].raw_score > ranked[1].raw_score


def test_prompt_soft_preferences_use_default_weights_without_template() -> None:
    preferred = Timetable(courses=[_course("GEN-A", course_name="대학영어")])
    other = Timetable(courses=[_course("GEN-B", course_name="고전읽기와토론")])

    ranked = rank_timetables(
        [other, preferred],
        preferences=PreferenceRules(preferred_course_names=["대학영어"]),
        top_n=2,
    )
    component = [
        item
        for item in ranked[0].score_components
        if item.key == "preferred_course"
    ][0]

    assert component.value == RankingWeights().preferred_course
    assert ranked[0].timetable.courses[0].course_name == "대학영어"


def test_template_selection_strengthens_related_weights() -> None:
    default = build_ranking_weights(PreferenceRules())
    templated = build_ranking_weights(
        PreferenceRules(selected_templates=[PreferenceTemplate.PREFER_FREE_DAY])
    )

    assert templated.preferred_free_day > default.preferred_free_day
    assert abs(templated.preferred_free_day_missing) > abs(default.preferred_free_day_missing)


def test_duplicate_templates_or_conditions_are_not_applied_twice() -> None:
    duplicate_templates = build_ranking_weights(
        PreferenceRules(
            selected_templates=[
                PreferenceTemplate.PREFER_FREE_DAY,
                PreferenceTemplate.PREFER_FREE_DAY,
            ]
        )
    )
    single_template = build_ranking_weights(
        PreferenceRules(selected_templates=[PreferenceTemplate.PREFER_FREE_DAY])
    )
    preferences = PreferenceRules(preferred_course_names=["대학영어", "대학영어"])
    candidate = Timetable(courses=[_course("GEN-A", course_name="대학영어")])

    ranked = rank_timetables([candidate], preferences=preferences)
    component = [
        item
        for item in ranked[0].score_components
        if item.key == "preferred_course"
    ][0]

    assert duplicate_templates == single_template
    assert component.value == RankingWeights().preferred_course


def test_zero_value_component_reason_is_not_exposed_to_reasons_or_warnings() -> None:
    candidate = Timetable(courses=[_course("GEN-A", course_name="고전읽기와토론")])
    weights = RankingWeights(preferred_course=0, preferred_course_missing=0)

    ranked = rank_timetables(
        [candidate],
        preferences=PreferenceRules(preferred_course_names=["대학영어"]),
        weights=weights,
    )
    result = ranked[0]

    assert any(
        component.key == "preferred_course_missing" and component.value == 0
        for component in result.score_components
    )
    assert not any("선호 과목은 포함되지 않았습니다" in reason for reason in result.timetable.reasons)
    assert not any("선호 과목은 포함되지 않았습니다" in warning for warning in result.timetable.warnings)


def test_explicit_ranking_weights_override_template_generated_weights() -> None:
    candidate = Timetable(courses=[_course("GEN-A", day=Day.TUE)])
    weights = RankingWeights(preferred_free_day=1)

    ranked = rank_timetables(
        [candidate],
        preferences=PreferenceRules(
            preferred_free_days=[Day.MON],
            selected_templates=[PreferenceTemplate.PREFER_FREE_DAY],
        ),
        weights=weights,
    )
    component = [
        item for item in ranked[0].score_components if item.key == "preferred_free_day"
    ][0]

    assert component.value == 1
