from datetime import datetime, timedelta, timezone

from backend.app.agent_tools.timetable_selection_tools import TimetableSelectionTools
from backend.app.agents.simple_session_model import SimpleSessionStateModel
from backend.app.models.course import Category, ClassTime, Course, Day
from backend.app.models.course_discovery import CourseSection
from backend.app.models.session_preferences import HardConstraints, SoftPreferences
from backend.app.models.timetable_generation import (
    GeneratedTimetableCandidate,
    ResolvedSection,
    SectionSource,
    TimetableValidationResult,
)
from backend.app.repositories.in_memory_session_repository import InMemorySessionRepository
from backend.app.repositories.recent_timetable_candidate_repository import RecentTimetableCandidateRepository
from backend.app.services.session_service import SessionService
from backend.app.services.timetable_scoring_service import TimetableScoringService
from backend.app.services.timetable_validator import TimetableValidator


def _course(course_id: str, credit: float = 3) -> Course:
    return Course(
        course_id=course_id,
        course_name=course_id,
        category=Category.GENERAL_ELECTIVE,
        area=1,
        credit=credit,
        division="001",
        professor="교수",
        class_times=[ClassTime(day=Day.MON, start="10:00", end="11:00", classroom="101", building_code="401")],
    )


def _section(section_id: str, course_id: str, start: str, end: str) -> CourseSection:
    return CourseSection(
        section_id=section_id,
        course_id=course_id,
        course_code=course_id,
        course_name=course_id,
        category=Category.GENERAL_ELECTIVE,
        area=1,
        credit=3,
        division=section_id.rsplit("-", 1)[-1],
        professor="교수",
        class_times=[ClassTime(day=Day.MON, start=start, end=end, classroom="101", building_code="401")],
    )


def _candidate(candidate_id: str, section_ids: list[str], *, session_version: int | None = None) -> GeneratedTimetableCandidate:
    return GeneratedTimetableCandidate(
        candidate_id=candidate_id,
        section_ids=section_ids,
        fixed_section_ids=[],
        added_section_ids=section_ids,
        course_ids=[sid.rsplit("-", 1)[0] for sid in section_ids],
        total_credits=3 * len(section_ids),
        validation=TimetableValidationResult(valid=True, checked_section_ids=section_ids),
        generation_order=1,
        session_id="session",
        session_version=session_version,
    )


def test_credit_boundaries_keep_inclusive_flags_and_validate_directly() -> None:
    course = _course("C-001", credit=15)
    assert TimetableValidator().validate([course], min_credit=15, min_credit_inclusive=True).valid
    assert not TimetableValidator().validate([course], min_credit=15, min_credit_inclusive=False).valid
    assert TimetableValidator().validate([course], max_credit=15, max_credit_inclusive=True).valid
    assert not TimetableValidator().validate([course], max_credit=15, max_credit_inclusive=False).valid


def test_exact_credit_request_sets_equal_inclusive_min_and_max() -> None:
    model = SimpleSessionStateModel()
    result = model({"messages": [{"role": "user", "content": {"user_message": "총 18학점으로 맞춰줘"}}]})
    hard = result["tool_calls"][0]["arguments"]["hard"]
    assert hard == {
        "min_credit": 18.0,
        "min_credit_inclusive": True,
        "max_credit": 18.0,
        "max_credit_inclusive": True,
    }
    assert TimetableValidator().validate([_course("A", 18)], min_credit=18, max_credit=18).valid
    assert not TimetableValidator().validate([_course("A", 17)], min_credit=18, max_credit=18).valid


def test_morning_preference_uses_default_without_unresolved_request() -> None:
    model = SimpleSessionStateModel()
    soft = model({"messages": [{"role": "user", "content": {"user_message": "아침 수업은 피하고 싶어"}}]})
    hard = model({"messages": [{"role": "user", "content": {"user_message": "아침 수업은 절대 안 돼"}}]})
    assert soft["tool_calls"][0]["arguments"] == {"soft": {"preferred_earliest_start_time": "10:00"}}
    assert soft["unresolved_requests"] == []
    assert hard["tool_calls"][0]["arguments"] == {"hard": {"earliest_start_time": "10:00"}}
    assert hard["unresolved_requests"] == []


def test_latest_end_and_compact_false_affect_soft_scores() -> None:
    early = _section("EARLY-001", "EARLY", "10:00", "11:00")
    late = _section("LATE-001", "LATE", "17:00", "18:00")
    scorer = TimetableScoringService()
    early_score = scorer.score_candidate(
        candidate=_candidate("early", ["EARLY-001"]),
        sections=[ResolvedSection(catalog_id="catalog", section=early)],
        soft_preferences=SoftPreferences(preferred_latest_end_time="16:00"),
    )
    late_score = scorer.score_candidate(
        candidate=_candidate("late", ["LATE-001"]),
        sections=[ResolvedSection(catalog_id="catalog", section=late)],
        soft_preferences=SoftPreferences(preferred_latest_end_time="16:00"),
    )
    assert early_score.total_score > late_score.total_score

    compact = [_section("A-001", "A", "09:00", "10:00"), _section("B-001", "B", "10:00", "11:00")]
    spread = [_section("A-001", "A", "09:00", "10:00"), _section("B-001", "B", "13:00", "14:00")]
    compact_score = scorer.score_candidate(
        candidate=_candidate("compact", ["A-001", "B-001"]),
        sections=[ResolvedSection(catalog_id="catalog", section=item) for item in compact],
        soft_preferences=SoftPreferences(compact_schedule=False),
    )
    spread_score = scorer.score_candidate(
        candidate=_candidate("spread", ["A-001", "B-001"]),
        sections=[ResolvedSection(catalog_id="catalog", section=item) for item in spread],
        soft_preferences=SoftPreferences(compact_schedule=False),
    )
    assert spread_score.total_score > compact_score.total_score


def test_course_id_preferences_affect_scoring() -> None:
    wanted = _section("W-001", "WANTED", "10:00", "11:00")
    bad = _section("B-001", "BAD", "12:00", "13:00")
    scorer = TimetableScoringService()
    preferred = scorer.score_candidate(
        candidate=_candidate("preferred", ["W-001"]),
        sections=[ResolvedSection(catalog_id="catalog", section=wanted)],
        soft_preferences=SoftPreferences(preferred_course_ids=["WANTED"]),
    )
    disliked = scorer.score_candidate(
        candidate=_candidate("disliked", ["B-001"]),
        sections=[ResolvedSection(catalog_id="catalog", section=bad)],
        soft_preferences=SoftPreferences(disliked_course_ids=["BAD"]),
    )
    assert preferred.total_score > 0
    assert disliked.total_score < 0


def test_stale_candidate_id_is_rejected_after_session_version_changes() -> None:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    service = SessionService(InMemorySessionRepository(), now_provider=lambda: now)
    state = service.create_session()
    repo = RecentTimetableCandidateRepository()
    candidate = _candidate("tt-old", ["A-001"], session_version=state.version)
    repo.save_candidates(state.session_id, [candidate.model_copy(update={"session_id": state.session_id})])
    service.update_preferences(state.session_id, hard_patch=None, soft_patch=None)
    service.set_department(state.session_id, "컴퓨터공학과")
    tools = TimetableSelectionTools(
        session_service=service,
        revision_preparation_service=object(),
        recent_candidate_repository=repo,
    )
    result = tools.select_timetable_candidate({"session_id": state.session_id, "candidate_id": "tt-old"})
    assert result.success is False
    assert "이전 조건" in result.message
