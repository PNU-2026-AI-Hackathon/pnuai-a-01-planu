"""Tests for template-based, session-aware timetable ranking."""

from __future__ import annotations

import pytest

from backend.app.models import (
    Category,
    ClassTime,
    Course,
    CourseLoadSatisfaction,
    Day,
    PreferenceRules,
    RankingTemplate,
    Timetable,
)
from backend.app.services.ranking_template_service import RankingTemplateService
from backend.app.services.session_store import SessionStage, SessionStore
from backend.app.services.timetable_ranking_service import (
    InvalidRankingSessionStageError,
    NoGeneratedCandidatesError,
    TimetableRankingService,
)
from backend.app.services.timetable_ranker import TimetableRanker, rank_timetables


def _course(
    course_id: str,
    *,
    day: Day = Day.MON,
    start: str = "11:00",
    end: str = "12:00",
) -> Course:
    return Course(
        course_id=course_id,
        course_name=f"강의 {course_id}",
        category=Category.GENERAL_REQUIRED,
        credit=1,
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


def _timetable(course_id_prefix: str, meetings: list[tuple[Day, str, str]]) -> Timetable:
    return Timetable(
        courses=[
            _course(
                f"{course_id_prefix}-{index}",
                day=day,
                start=start,
                end=end,
            )
            for index, (day, start, end) in enumerate(meetings, start=1)
        ]
    )


def test_ranking_template_service_returns_mvp_templates() -> None:
    service = RankingTemplateService()

    definitions = service.list_templates()

    assert {definition.template for definition in definitions} == set(RankingTemplate)
    assert all(definition.name for definition in definitions)
    assert all(definition.description for definition in definitions)
    assert service.get_weights(RankingTemplate.BALANCED).valid_candidate == 70
    with pytest.raises(ValueError):
        service.get_weights("unknown_template")


def test_explicit_ranking_template_changes_raw_score_without_changing_preferences() -> None:
    early = Timetable(courses=[_course("GEN-A", start="08:00", end="09:00")])

    balanced = rank_timetables(
        [early],
        template=RankingTemplate.BALANCED,
    )[0]
    no_morning = rank_timetables(
        [early],
        template=RankingTemplate.NO_MORNING_PRIORITY,
    )[0]

    assert balanced.template is RankingTemplate.BALANCED
    assert no_morning.template is RankingTemplate.NO_MORNING_PRIORITY
    assert no_morning.raw_score < balanced.raw_score
    assert any(
        component.key == "daily_first_start"
        for component in no_morning.score_components
    )


def test_top_n_none_returns_all_rankable_candidates() -> None:
    store = SessionStore()
    session = store.create("정보컴퓨터공학부")
    store.update_generated_candidates(
        session.session_id,
        candidates=[Timetable(courses=[_course("GEN-A")]), Timetable(courses=[_course("GEN-B")])],
    )

    result = TimetableRankingService(store).rank_for_session(
        session_id=session.session_id,
        top_n=None,
    )

    assert len(result.ranked_candidates) == 2
    assert not any(
        diagnostic.code == "RANKING_RESULT_TRUNCATED"
        for diagnostic in result.diagnostics
    )


@pytest.mark.parametrize("top_n", [0, -1])
def test_top_n_must_be_positive(top_n: int) -> None:
    store = SessionStore()
    session = store.create("정보컴퓨터공학부")
    store.update_generated_candidates(
        session.session_id,
        candidates=[Timetable(courses=[_course("GEN-A")])],
    )

    with pytest.raises(ValueError, match="top_n must be positive"):
        TimetableRankingService(store).rank_for_session(
            session_id=session.session_id,
            top_n=top_n,
        )


def test_top_n_larger_than_candidates_returns_all_without_truncation() -> None:
    store = SessionStore()
    session = store.create("정보컴퓨터공학부")
    store.update_generated_candidates(
        session.session_id,
        candidates=[Timetable(courses=[_course("GEN-A")]), Timetable(courses=[_course("GEN-B")])],
    )

    result = TimetableRankingService(store).rank_for_session(
        session_id=session.session_id,
        top_n=10,
    )

    assert len(result.ranked_candidates) == 2
    assert not any(
        diagnostic.code == "RANKING_RESULT_TRUNCATED"
        for diagnostic in result.diagnostics
    )


def test_truncation_diagnostic_only_when_result_is_cut() -> None:
    store = SessionStore()
    session = store.create("정보컴퓨터공학부")
    store.update_generated_candidates(
        session.session_id,
        candidates=[Timetable(courses=[_course("GEN-A")]), Timetable(courses=[_course("GEN-B")])],
    )

    result = TimetableRankingService(store).rank_for_session(
        session_id=session.session_id,
        top_n=1,
    )

    assert len(result.ranked_candidates) == 1
    assert any(
        diagnostic.code == "RANKING_RESULT_TRUNCATED"
        for diagnostic in result.diagnostics
    )


def test_no_morning_template_scores_daily_first_start_per_attendance_day() -> None:
    one_early_day = _timetable("ONE", [(Day.MON, "08:00", "09:00")])
    five_early_days = _timetable(
        "FIVE",
        [
            (Day.MON, "08:00", "09:00"),
            (Day.TUE, "08:00", "09:00"),
            (Day.WED, "08:00", "09:00"),
            (Day.THU, "08:00", "09:00"),
            (Day.FRI, "08:00", "09:00"),
        ],
    )
    all_late_days = _timetable(
        "LATE",
        [
            (Day.MON, "11:00", "12:00"),
            (Day.TUE, "11:00", "12:00"),
            (Day.WED, "11:00", "12:00"),
            (Day.THU, "11:00", "12:00"),
            (Day.FRI, "11:00", "12:00"),
        ],
    )

    ranked = rank_timetables(
        [five_early_days, one_early_day, all_late_days],
        template=RankingTemplate.NO_MORNING_PRIORITY,
        top_n=3,
    )

    assert [item.timetable.courses[0].course_id.split("-")[0] for item in ranked] == [
        "LATE",
        "ONE",
        "FIVE",
    ]
    component = [
        item
        for item in ranked[-1].score_components
        if item.key == "daily_first_start"
    ][0]
    assert "요일별 첫 수업" in component.reason
    assert "5개 등교일" in component.reason


def test_same_ranker_instance_does_not_share_template_state() -> None:
    ranker = TimetableRanker()
    candidate = Timetable(courses=[_course("GEN-A", start="08:00", end="09:00")])

    no_morning = ranker.rank(
        [candidate],
        template=RankingTemplate.NO_MORNING_PRIORITY,
    )[0]
    balanced = ranker.rank(
        [candidate],
        template=RankingTemplate.BALANCED,
    )[0]
    no_morning_again = ranker.rank(
        [candidate],
        template=RankingTemplate.NO_MORNING_PRIORITY,
    )[0]

    assert no_morning.raw_score == no_morning_again.raw_score
    assert no_morning.raw_score < balanced.raw_score


def test_balanced_template_averages_daily_first_start_score() -> None:
    two_late_days = _timetable(
        "TWO",
        [(Day.MON, "11:00", "12:00"), (Day.TUE, "11:00", "12:00")],
    )
    five_late_days = _timetable(
        "FIVE",
        [
            (Day.MON, "11:00", "12:00"),
            (Day.TUE, "11:00", "12:00"),
            (Day.WED, "11:00", "12:00"),
            (Day.THU, "11:00", "12:00"),
            (Day.FRI, "11:00", "12:00"),
        ],
    )

    ranked = rank_timetables(
        [two_late_days, five_late_days],
        template=RankingTemplate.BALANCED,
        top_n=2,
    )
    daily_components = {
        item.timetable.courses[0].course_id.split("-")[0]: [
            component
            for component in item.score_components
            if component.key == "daily_first_start"
        ][0]
        for item in ranked
    }

    assert daily_components["TWO"].value == daily_components["FIVE"].value


def test_no_morning_template_sums_daily_first_start_score() -> None:
    two_late_days = _timetable(
        "TWO",
        [(Day.MON, "11:00", "12:00"), (Day.TUE, "11:00", "12:00")],
    )
    five_late_days = _timetable(
        "FIVE",
        [
            (Day.MON, "11:00", "12:00"),
            (Day.TUE, "11:00", "12:00"),
            (Day.WED, "11:00", "12:00"),
            (Day.THU, "11:00", "12:00"),
            (Day.FRI, "11:00", "12:00"),
        ],
    )

    ranked = rank_timetables(
        [two_late_days, five_late_days],
        template=RankingTemplate.NO_MORNING_PRIORITY,
        top_n=2,
    )
    daily_components = {
        item.timetable.courses[0].course_id.split("-")[0]: [
            component
            for component in item.score_components
            if component.key == "daily_first_start"
        ][0]
        for item in ranked
    }

    assert daily_components["FIVE"].value > daily_components["TWO"].value


def test_compact_schedule_prefers_shorter_idle_time_with_same_attendance_days() -> None:
    short_idle = _timetable(
        "SHORT",
        [(Day.MON, "09:00", "10:00"), (Day.MON, "10:30", "11:30")],
    )
    long_idle = _timetable(
        "LONG",
        [(Day.MON, "09:00", "10:00"), (Day.MON, "13:00", "14:00")],
    )

    ranked = rank_timetables(
        [long_idle, short_idle],
        template=RankingTemplate.COMPACT_SCHEDULE,
        top_n=2,
    )

    assert ranked[0].timetable.courses[0].course_id.startswith("SHORT")


def test_compact_schedule_does_not_reward_only_single_class_days_as_best() -> None:
    single_class_each_day = _timetable(
        "SPREAD",
        [
            (Day.MON, "09:00", "10:00"),
            (Day.TUE, "09:00", "10:00"),
            (Day.WED, "09:00", "10:00"),
            (Day.THU, "09:00", "10:00"),
            (Day.FRI, "09:00", "10:00"),
        ],
    )
    compact_one_day = _timetable(
        "COMPACT",
        [(Day.MON, "09:00", "10:00"), (Day.MON, "10:00", "11:00")],
    )

    ranked = rank_timetables(
        [single_class_each_day, compact_one_day],
        template=RankingTemplate.COMPACT_SCHEDULE,
        top_n=2,
    )
    spread_component = [
        component
        for component in ranked[1].score_components
        if component.key == "compact_schedule"
    ][0]

    assert ranked[0].timetable.courses[0].course_id.startswith("COMPACT")
    assert spread_component.value == 0
    assert "수업이 2개 이상인 날" in spread_component.reason


def test_movement_checker_receives_course_and_class_time_context() -> None:
    candidate = _timetable(
        "MOVE",
        [(Day.MON, "09:00", "10:00"), (Day.MON, "10:00", "11:00")],
    )
    calls: list[tuple[Course, ClassTime, Course, ClassTime]] = []

    def checker(
        previous_course: Course,
        previous_meeting: ClassTime,
        following_course: Course,
        following_meeting: ClassTime,
    ) -> bool:
        calls.append(
            (
                previous_course,
                previous_meeting,
                following_course,
                following_meeting,
            )
        )
        return True

    TimetableRanker(movement_checker=checker).rank(
        [candidate],
        template=RankingTemplate.COMPACT_SCHEDULE,
    )

    assert len(calls) == 1
    previous_course, previous_meeting, following_course, following_meeting = calls[0]
    assert previous_course.course_id == "MOVE-1"
    assert previous_meeting.day is Day.MON
    assert previous_meeting.end == "10:00"
    assert following_course.course_id == "MOVE-2"
    assert following_meeting.start == "10:00"


def test_movement_checker_can_exempt_movable_consecutive_classes() -> None:
    candidate = _timetable(
        "MOVE",
        [(Day.MON, "09:00", "10:00"), (Day.MON, "10:00", "11:00")],
    )

    def movable_checker(
        _previous_course: Course,
        _previous_meeting: ClassTime,
        _following_course: Course,
        _following_meeting: ClassTime,
    ) -> bool:
        return True

    movable = TimetableRanker(movement_checker=movable_checker).rank(
        [candidate],
        template=RankingTemplate.COMPACT_SCHEDULE,
    )[0]
    unknown = TimetableRanker().rank(
        [candidate],
        template=RankingTemplate.COMPACT_SCHEDULE,
    )[0]

    movable_component = [
        component
        for component in movable.score_components
        if component.key == "consecutive_classes"
    ][0]
    unknown_component = [
        component
        for component in unknown.score_components
        if component.key == "consecutive_classes"
    ][0]

    assert movable_component.value > unknown_component.value
    assert movable_component.value == 0
    assert "모두 이동 가능한 구간" in movable_component.reason
    assert "연강 없음" not in movable_component.reason


def test_difficult_consecutive_classes_are_penalized_by_difficult_count() -> None:
    candidate = _timetable(
        "MOVE",
        [
            (Day.MON, "09:00", "10:00"),
            (Day.MON, "10:00", "11:00"),
            (Day.MON, "11:00", "12:00"),
        ],
    )

    def mixed_checker(
        previous_course: Course,
        _previous_meeting: ClassTime,
        _following_course: Course,
        _following_meeting: ClassTime,
    ) -> bool:
        return previous_course.course_id == "MOVE-1"

    ranked = TimetableRanker(movement_checker=mixed_checker).rank(
        [candidate],
        template=RankingTemplate.COMPACT_SCHEDULE,
    )[0]
    component = [
        item
        for item in ranked.score_components
        if item.key == "consecutive_classes"
    ][0]

    assert component.value == -4
    assert "연강 2개 중 1개" in component.reason


def test_missing_movement_checker_uses_existing_consecutive_fallback() -> None:
    candidate = _timetable(
        "MOVE",
        [(Day.MON, "09:00", "10:00"), (Day.MON, "10:00", "11:00")],
    )

    ranked = TimetableRanker().rank(
        [candidate],
        template=RankingTemplate.COMPACT_SCHEDULE,
    )[0]
    component = [
        item
        for item in ranked.score_components
        if item.key == "consecutive_classes"
    ][0]

    assert component.value == -4
    assert "이동이 어려운 구간" in component.reason


def test_course_load_satisfaction_sorts_before_raw_score() -> None:
    higher_raw_score = Timetable(
        courses=[_course("GEN-A", day=Day.TUE, start="11:00", end="12:00")],
        load_satisfaction=CourseLoadSatisfaction(
            satisfied_required_group_count=0,
            requested_required_group_count=1,
        ),
    )
    lower_raw_score_better_load = Timetable(
        courses=[_course("GEN-B", day=Day.MON, start="08:00", end="09:00")],
        load_satisfaction=CourseLoadSatisfaction(
            satisfied_required_group_count=1,
            requested_required_group_count=1,
        ),
    )

    ranked = rank_timetables(
        [higher_raw_score, lower_raw_score_better_load],
        template=RankingTemplate.NO_MORNING_PRIORITY,
        top_n=2,
    )

    assert ranked[0].timetable.courses[0].course_id == "GEN-B"


def test_ranking_service_removes_duplicates_and_saves_result() -> None:
    store = SessionStore()
    session = store.create("정보컴퓨터공학부")
    candidate = Timetable(courses=[_course("GEN-A")])
    duplicate = Timetable(courses=[_course("GEN-A")])
    store.update_generated_candidates(
        session.session_id,
        candidates=[candidate, duplicate],
    )

    result = TimetableRankingService(store).rank_for_session(
        session_id=session.session_id,
        template=RankingTemplate.COMPACT_SCHEDULE,
    )
    saved = store.get(session.session_id)

    assert len(result.ranked_candidates) == 1
    assert result.total_candidate_count == 2
    duplicate_diagnostic = [
        diagnostic
        for diagnostic in result.diagnostics
        if diagnostic.code == "DUPLICATE_CANDIDATE_REMOVED"
    ][0]
    assert duplicate_diagnostic.details["removed_count"] == 1
    assert any(
        diagnostic.code == "DUPLICATE_CANDIDATE_REMOVED"
        for diagnostic in result.diagnostics
    )
    assert saved.session_stage is SessionStage.RANKING_COMPLETED
    assert saved.latest_ranking_result == result


def test_ranking_service_removes_user_facing_duplicate_timetables() -> None:
    store = SessionStore()
    session = store.create("computer science")
    original = Timetable(courses=[_course("GEN-A", day=Day.MON)])
    visible_duplicate = Timetable(
        courses=[
            _course("GEN-A-HIDDEN-COPY", day=Day.MON).model_copy(
                update={"course_name": original.courses[0].course_name}
            )
        ]
    )
    alternative_1 = Timetable(courses=[_course("GEN-B", day=Day.TUE)])
    alternative_2 = Timetable(courses=[_course("GEN-C", day=Day.WED)])
    store.update_generated_candidates(
        session.session_id,
        candidates=[original, visible_duplicate, alternative_1, alternative_2],
    )

    result = TimetableRankingService(store).rank_for_session(
        session_id=session.session_id,
        template=RankingTemplate.BALANCED,
        top_n=3,
    )

    signatures = [
        tuple(
            sorted(
                (
                    course.course_name,
                    course.division,
                    tuple((item.day, item.start, item.end) for item in timetable.schedule_items),
                )
                for course in timetable.courses
            )
        )
        for timetable in (item.timetable for item in result.ranked_candidates)
    ]
    assert len(result.ranked_candidates) == 3
    assert len(set(signatures)) == 3
    assert any(
        diagnostic.code == "DUPLICATE_VISIBLE_TIMETABLE_REMOVED"
        and diagnostic.details["removed_count"] == 1
        for diagnostic in result.diagnostics
    )


def test_ranking_service_returns_only_real_unique_candidates_when_top_three_unavailable() -> None:
    store = SessionStore()
    session = store.create("computer science")
    original = Timetable(courses=[_course("GEN-A", day=Day.MON)])
    visible_duplicate = Timetable(
        courses=[
            _course("GEN-A-HIDDEN-COPY", day=Day.MON).model_copy(
                update={"course_name": original.courses[0].course_name}
            )
        ]
    )
    store.update_generated_candidates(
        session.session_id,
        candidates=[original, visible_duplicate],
    )

    result = TimetableRankingService(store).rank_for_session(
        session_id=session.session_id,
        template=RankingTemplate.BALANCED,
        top_n=3,
    )

    assert len(result.ranked_candidates) == 1
    assert result.ranked_candidates[0].timetable.courses[0].course_id == "GEN-A"


def test_ranking_service_hard_filter_diagnostic_matches_ranked_count() -> None:
    store = SessionStore()
    session = store.create("정보컴퓨터공학부")
    valid = Timetable(courses=[_course("GEN-A", day=Day.MON)])
    hard_violation = Timetable(courses=[_course("GEN-B", day=Day.FRI)])
    store.update_generated_candidates(
        session.session_id,
        candidates=[valid, hard_violation],
        preferences=PreferenceRules(excluded_days=[Day.FRI]),
    )

    result = TimetableRankingService(store).rank_for_session(
        session_id=session.session_id,
        template=RankingTemplate.BALANCED,
    )
    diagnostic = [
        item
        for item in result.diagnostics
        if item.code == "HARD_CONDITION_CANDIDATE_DETECTED"
    ][0]

    assert diagnostic.details["removed_count"] == 1
    assert len(result.ranked_candidates) == 1
    assert result.ranked_candidates[0].timetable.courses[0].course_id == "GEN-A"


def test_ranking_service_requires_generated_candidate_stage() -> None:
    store = SessionStore()
    session = store.create("정보컴퓨터공학부")

    with pytest.raises(InvalidRankingSessionStageError):
        TimetableRankingService(store).rank_for_session(
            session_id=session.session_id,
            template=RankingTemplate.BALANCED,
        )


def test_ranking_service_rejects_empty_generated_candidates() -> None:
    store = SessionStore()
    session = store.create("정보컴퓨터공학부")
    store.update(
        session.session_id,
        session_stage=SessionStage.CANDIDATES_GENERATED,
    )

    with pytest.raises(NoGeneratedCandidatesError):
        TimetableRankingService(store).rank_for_session(
            session_id=session.session_id,
            template=RankingTemplate.BALANCED,
        )
