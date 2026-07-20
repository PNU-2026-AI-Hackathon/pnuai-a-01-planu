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
from backend.app.services.timetable_ranker import rank_timetables


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
    assert any(component.key == "late_start" for component in no_morning.score_components)


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
