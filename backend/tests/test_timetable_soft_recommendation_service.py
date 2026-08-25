from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backend.app.models.course import Category, ClassTime, Day
from backend.app.models.course_discovery import CourseSection
from backend.app.models.planu_session_state import PlanuSessionState
from backend.app.models.session_preferences import HardConstraints, SoftPreferences
from backend.app.models.timetable_generation import (
    GeneratedTimetableCandidate,
    ResolvedSection,
    SectionSource,
    TimetableValidationResult,
    TimetableViolation,
    TimetableViolationCode,
)
from backend.app.models.timetable_selection import SelectedTimetable, SelectedTimetableStatus
from backend.app.models.timetable_soft_recommendation import (
    SoftPreferenceFeedbackTarget,
    SoftPreferenceRecommendationBlockedCode,
    SoftPreferenceRecommendationField,
    SoftPreferenceRecommendationMetricCode,
    SoftPreferenceRecommendationRequest,
    SoftPreferenceSuggestionBasis,
)
from backend.app.services.timetable_soft_recommendation_service import (
    TimetableSoftRecommendationService,
)


def _time(day: Day, start: str = "10:00", end: str = "11:00") -> ClassTime:
    return ClassTime(
        day=day,
        start=start,
        end=end,
        classroom="101",
        building_code="401",
    )


def _section(
    section_id: str,
    course_id: str,
    *,
    times: list[ClassTime],
) -> CourseSection:
    return CourseSection(
        section_id=section_id,
        course_id=course_id,
        course_code=course_id,
        course_name=f"강의 {course_id}",
        category=Category.GENERAL_ELECTIVE,
        area=1,
        credit=3,
        division=section_id.rsplit("-", 1)[-1],
        professor="교수",
        class_times=times,
    )


def _source(section_id: str) -> SectionSource:
    return SectionSource(catalog_id="catalog", section_id=section_id)


def _resolved(section: CourseSection) -> ResolvedSection:
    return ResolvedSection(catalog_id="catalog", section=section)


def _candidate(
    candidate_id: str,
    section_ids: list[str],
    *,
    valid: bool = True,
) -> GeneratedTimetableCandidate:
    return GeneratedTimetableCandidate(
        candidate_id=candidate_id,
        section_ids=section_ids,
        section_sources=[_source(section_id) for section_id in section_ids],
        fixed_section_ids=[],
        fixed_section_sources=[],
        added_section_ids=list(section_ids),
        added_section_sources=[_source(section_id) for section_id in section_ids],
        course_ids=list(dict.fromkeys(section_id.rsplit("-", 1)[0] for section_id in section_ids)),
        total_credits=3 * len(section_ids),
        validation=TimetableValidationResult(
            valid=valid,
            violations=[] if valid else [
                TimetableViolation(
                    code=TimetableViolationCode.TIME_CONFLICT,
                    message="conflict",
                )
            ],
            checked_section_ids=section_ids,
            checked_section_sources=[_source(section_id) for section_id in section_ids],
        ),
        generation_order=1,
    )


def _free_day_fixture() -> tuple[list[GeneratedTimetableCandidate], list[ResolvedSection]]:
    friday_class = _section("A-001", "A", times=[_time(Day.FRI)])
    tuesday_class = _section("B-001", "B", times=[_time(Day.TUE)])
    return (
        [
            _candidate("tt-a-tue-free", ["A-001"]),
            _candidate("tt-b-fri-free", ["B-001"]),
        ],
        [_resolved(friday_class), _resolved(tuesday_class)],
    )


def _compact_fixture() -> tuple[list[GeneratedTimetableCandidate], list[ResolvedSection]]:
    adjacent_a = _section("A-001", "A", times=[_time(Day.MON, "09:00", "10:00")])
    adjacent_b = _section("B-001", "B", times=[_time(Day.MON, "10:00", "11:00")])
    short_a = _section("C-001", "C", times=[_time(Day.MON, "09:00", "10:00")])
    short_b = _section("D-001", "D", times=[_time(Day.MON, "10:30", "11:30")])
    medium_a = _section("E-001", "E", times=[_time(Day.MON, "09:00", "10:00")])
    medium_b = _section("F-001", "F", times=[_time(Day.MON, "11:00", "12:00")])
    loose_a = _section("G-001", "G", times=[_time(Day.MON, "09:00", "10:00")])
    loose_b = _section("H-001", "H", times=[_time(Day.MON, "13:00", "14:00")])
    return (
        [
            _candidate("tt-adjacent", ["A-001", "B-001"]),
            _candidate("tt-short-gap", ["C-001", "D-001"]),
            _candidate("tt-medium-gap", ["E-001", "F-001"]),
            _candidate("tt-loose", ["G-001", "H-001"]),
        ],
        [
            _resolved(adjacent_a),
            _resolved(adjacent_b),
            _resolved(short_a),
            _resolved(short_b),
            _resolved(medium_a),
            _resolved(medium_b),
            _resolved(loose_a),
            _resolved(loose_b),
        ],
    )


def _analyze_free_day(
    *,
    request: SoftPreferenceRecommendationRequest | None = None,
    soft_preferences: SoftPreferences | None = None,
):
    candidates, sections = _free_day_fixture()
    return TimetableSoftRecommendationService().analyze(
        request=request
        or SoftPreferenceRecommendationRequest(
            session_id="session-1",
            feedback_target=SoftPreferenceFeedbackTarget.DIFFERENT_FREE_DAY,
        ),
        candidates=candidates,
        sections=sections,
        soft_preferences=soft_preferences or SoftPreferences(preferred_free_days=[Day.FRI]),
        hard_constraints=HardConstraints(required_course_ids=["MAJ101"]),
    )


def test_service_reranks_same_valid_candidate_set() -> None:
    result = _analyze_free_day()
    suggestion = result.suggestions[0]

    assert result.analyzed_candidate_count == 2
    assert set(suggestion.evidence.before_top_candidate_ids) == {
        "tt-a-tue-free",
        "tt-b-fri-free",
    }
    assert set(suggestion.evidence.after_top_candidate_ids) == {
        "tt-a-tue-free",
        "tt-b-fri-free",
    }
    assert suggestion.evidence.before_top_candidate_ids != suggestion.evidence.after_top_candidate_ids


def test_soft_change_keeps_valid_candidate_count_and_hard_constraints_identical() -> None:
    hard = HardConstraints(required_course_ids=["MAJ101"], min_credit=9)
    hard_before = hard.model_dump(mode="json")
    candidates, sections = _free_day_fixture()

    result = TimetableSoftRecommendationService().analyze(
        request=SoftPreferenceRecommendationRequest(
            session_id="session-1",
            feedback_target=SoftPreferenceFeedbackTarget.DIFFERENT_FREE_DAY,
        ),
        candidates=candidates,
        sections=sections,
        soft_preferences=SoftPreferences(preferred_free_days=[Day.FRI]),
        hard_constraints=hard,
    )

    assert result.analyzed_candidate_count == 2
    assert hard.model_dump(mode="json") == hard_before


def test_analysis_does_not_mutate_original_session_soft_or_candidates() -> None:
    candidates, sections = _free_day_fixture()
    now = datetime.now(timezone.utc)
    state = PlanuSessionState(
        session_id="session-1",
        department="컴퓨터공학과",
        selected_major_course_ids=["MAJ101"],
        hard_constraints=HardConstraints(required_course_ids=["MAJ101"]),
        soft_preferences=SoftPreferences(preferred_free_days=[Day.FRI]),
        selected_timetable=SelectedTimetable(
            candidate_id="tt-b-fri-free",
            section_ids=["B-001"],
            added_section_ids=["B-001"],
            course_ids=["B"],
            section_sources=[_source("B-001")],
            added_section_sources=[_source("B-001")],
            selected_at=now,
        ),
        selected_timetable_status=SelectedTimetableStatus.CURRENT,
        generation_preferences_confirmed_at=now,
        generation_preferences_confirmed_version=1,
        created_at=now,
        updated_at=now,
        last_accessed_at=now,
        expires_at=now + timedelta(minutes=30),
    )
    state_before = state.model_dump(mode="json")
    candidates_before = [candidate.model_dump(mode="json") for candidate in candidates]

    TimetableSoftRecommendationService().analyze_session(
        request=SoftPreferenceRecommendationRequest(
            session_id=state.session_id,
            feedback_target=SoftPreferenceFeedbackTarget.DIFFERENT_FREE_DAY,
        ),
        state=state,
        candidates=candidates,
        sections=sections,
    )

    assert state.model_dump(mode="json") == state_before
    assert [candidate.model_dump(mode="json") for candidate in candidates] == candidates_before
    assert state.selected_timetable_status is SelectedTimetableStatus.CURRENT
    assert state.generation_preferences_confirmed_at == now


def test_only_adjustments_with_improved_related_metrics_are_recommended() -> None:
    result = _analyze_free_day()
    suggestion = result.suggestions[0]

    assert suggestion.field is SoftPreferenceRecommendationField.PREFERRED_FREE_DAYS
    assert any(
        metric.code is SoftPreferenceRecommendationMetricCode.PREFERRED_FREE_DAY_SATISFIED_COUNT
        for metric in suggestion.evidence.improved_metrics
    )


def test_no_recommendation_when_top_candidates_do_not_change() -> None:
    first = _section("A-001", "A", times=[_time(Day.MON)])
    second = _section("B-001", "B", times=[_time(Day.WED)])
    result = TimetableSoftRecommendationService().analyze(
        request=SoftPreferenceRecommendationRequest(
            session_id="session-1",
            feedback_target=SoftPreferenceFeedbackTarget.DIFFERENT_FREE_DAY,
        ),
        candidates=[_candidate("tt-a", ["A-001"]), _candidate("tt-b", ["B-001"])],
        sections=[_resolved(first), _resolved(second)],
        soft_preferences=SoftPreferences(preferred_free_days=[Day.FRI]),
    )

    assert result.suggestions == []
    assert result.blocked_reasons[0].code is SoftPreferenceRecommendationBlockedCode.NOT_DETERMINABLE_WITH_CURRENT_DATA


def test_tradeoff_only_adjustment_is_not_recommended() -> None:
    result = _analyze_free_day(
        request=SoftPreferenceRecommendationRequest(
            session_id="session-1",
            feedback_target=SoftPreferenceFeedbackTarget.DIFFERENT_FREE_DAY,
        ),
        soft_preferences=SoftPreferences(preferred_free_days=[Day.TUE]),
    )

    assert result.suggestions == []
    assert result.blocked_reasons[0].code is SoftPreferenceRecommendationBlockedCode.NOT_DETERMINABLE_WITH_CURRENT_DATA


def test_structured_feedback_target_related_recommendation_is_prioritized() -> None:
    candidates, sections = _compact_fixture()
    result = TimetableSoftRecommendationService().analyze(
        request=SoftPreferenceRecommendationRequest(
            session_id="session-1",
            feedback_target=SoftPreferenceFeedbackTarget.LESS_COMPACT,
        ),
        candidates=candidates,
        sections=sections,
        soft_preferences=SoftPreferences(compact_schedule=True),
    )

    assert result.suggestions
    assert result.suggestions[0].field is SoftPreferenceRecommendationField.COMPACT_SCHEDULE
    assert result.suggestions[0].basis is SoftPreferenceSuggestionBasis.STRUCTURED_USER_FEEDBACK


def test_protected_soft_preference_is_not_changed() -> None:
    result = _analyze_free_day(
        request=SoftPreferenceRecommendationRequest(
            session_id="session-1",
            feedback_target=SoftPreferenceFeedbackTarget.DIFFERENT_FREE_DAY,
            protected_soft_preferences=[
                SoftPreferenceRecommendationField.PREFERRED_FREE_DAYS
            ],
        )
    )

    assert result.suggestions == []
    assert result.blocked_reasons[0].code is SoftPreferenceRecommendationBlockedCode.ALL_CHANGEABLE_FIELDS_PROTECTED


def test_recommendations_are_limited_to_three() -> None:
    candidates, sections = _compact_fixture()
    result = TimetableSoftRecommendationService().analyze(
        request=SoftPreferenceRecommendationRequest(
            session_id="session-1",
            feedback_target=SoftPreferenceFeedbackTarget.DIFFERENT_TOP_CANDIDATES,
            max_suggestions=3,
        ),
        candidates=candidates,
        sections=sections,
        soft_preferences=SoftPreferences(compact_schedule=True),
    )

    assert len(result.suggestions) <= 3


def test_same_input_produces_same_recommendation_order() -> None:
    first = _analyze_free_day()
    second = _analyze_free_day()

    assert first.model_dump(mode="json") == second.model_dump(mode="json")


def test_zero_candidates_returns_blocked_reason_without_hard_relaxation() -> None:
    result = TimetableSoftRecommendationService().analyze(
        request=SoftPreferenceRecommendationRequest(session_id="session-1"),
        candidates=[],
        sections=[],
        soft_preferences=SoftPreferences(),
        hard_constraints=HardConstraints(required_course_ids=["MAJ101"]),
    )

    assert result.suggestions == []
    assert result.blocked_reasons[0].code is SoftPreferenceRecommendationBlockedCode.NO_CANDIDATES
    assert "hard" not in result.blocked_reasons[0].details


def test_hard_invalid_candidates_are_blocked_without_soft_suggestion() -> None:
    section = _section("A-001", "A", times=[_time(Day.MON)])
    result = TimetableSoftRecommendationService().analyze(
        request=SoftPreferenceRecommendationRequest(session_id="session-1"),
        candidates=[_candidate("tt-invalid", ["A-001"], valid=False)],
        sections=[_resolved(section)],
        soft_preferences=SoftPreferences(preferred_free_days=[Day.FRI]),
        hard_constraints=HardConstraints(required_course_ids=["MAJ101"]),
    )

    assert result.suggestions == []
    assert result.blocked_reasons[0].code is SoftPreferenceRecommendationBlockedCode.HARD_CONSTRAINT_CAUSE


def test_no_score_evidence_returns_blocked_reason_without_feedback() -> None:
    candidates, sections = _free_day_fixture()
    result = TimetableSoftRecommendationService().analyze(
        request=SoftPreferenceRecommendationRequest(session_id="session-1"),
        candidates=candidates,
        sections=sections,
        soft_preferences=SoftPreferences(),
    )

    assert result.suggestions == []
    assert result.blocked_reasons[0].code is SoftPreferenceRecommendationBlockedCode.INSUFFICIENT_SCORE_EVIDENCE


def test_data_absent_feedback_does_not_create_unsupported_recommendation() -> None:
    section = _section("A-001", "A", times=[_time(Day.MON)])
    result = TimetableSoftRecommendationService().analyze(
        request=SoftPreferenceRecommendationRequest(
            session_id="session-1",
            feedback_target=SoftPreferenceFeedbackTarget.AVOID_COURSE,
        ),
        candidates=[_candidate("tt-only", ["A-001"])],
        sections=[_resolved(section)],
        soft_preferences=SoftPreferences(),
    )

    assert result.suggestions == []
    assert result.blocked_reasons[0].code is SoftPreferenceRecommendationBlockedCode.NOT_DETERMINABLE_WITH_CURRENT_DATA


def test_analysis_does_not_invalidate_candidate_or_confirmation_state() -> None:
    candidates, sections = _free_day_fixture()
    now = datetime.now(timezone.utc)
    state = PlanuSessionState(
        session_id="session-1",
        department="컴퓨터공학과",
        selected_major_course_ids=["MAJ101"],
        soft_preferences=SoftPreferences(preferred_free_days=[Day.FRI]),
        selected_timetable=SelectedTimetable(
            candidate_id="tt-b-fri-free",
            section_ids=["B-001"],
            added_section_ids=["B-001"],
            course_ids=["B"],
            section_sources=[_source("B-001")],
            added_section_sources=[_source("B-001")],
            selected_at=now,
        ),
        selected_timetable_status=SelectedTimetableStatus.CURRENT,
        generation_preferences_confirmed_at=now,
        generation_preferences_confirmed_version=1,
        created_at=now,
        updated_at=now,
        last_accessed_at=now,
        expires_at=now + timedelta(minutes=30),
    )

    TimetableSoftRecommendationService().analyze_session(
        request=SoftPreferenceRecommendationRequest(
            session_id=state.session_id,
            feedback_target=SoftPreferenceFeedbackTarget.DIFFERENT_FREE_DAY,
        ),
        state=state,
        candidates=candidates,
        sections=sections,
    )

    assert state.selected_timetable is not None
    assert state.selected_timetable_status is SelectedTimetableStatus.CURRENT
    assert state.generation_preferences_confirmed_at == now
    assert state.generation_preferences_confirmed_version == 1



