"""Tests for template-based, session-aware timetable ranking."""

from __future__ import annotations

import pytest

from backend.app.models import (
    Category,
    ClassTime,
    Course,
    CourseLoadSatisfaction,
    Day,
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


def test_movement_checker_can_exempt_movable_consecutive_classes() -> None:
    candidate = _timetable(
        "MOVE",
        [(Day.MON, "09:00", "10:00"), (Day.MON, "10:00", "11:00")],
    )

    movable = TimetableRanker(movement_checker=lambda _previous, _following: True).rank(
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
