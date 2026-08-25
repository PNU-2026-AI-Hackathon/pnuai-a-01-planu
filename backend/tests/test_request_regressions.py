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


def _candidate(
    candidate_id: str | None,
    section_ids: list[str],
    *,
    session_version: int | None = None,
    generation_revision: int | None = None,
) -> GeneratedTimetableCandidate:
    return GeneratedTimetableCandidate(
        candidate_id=candidate_id or GeneratedTimetableCandidate.build_id(section_ids),
        section_ids=section_ids,
        fixed_section_ids=[],
        added_section_ids=section_ids,
        course_ids=[sid.rsplit("-", 1)[0] for sid in section_ids],
        total_credits=3 * len(section_ids),
        validation=TimetableValidationResult(valid=True, checked_section_ids=section_ids),
        generation_order=1,
        session_id="session",
        session_version=session_version,
        generation_revision=generation_revision,
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


def test_candidate_selection_ignores_general_session_version_changes() -> None:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    service = SessionService(InMemorySessionRepository(), now_provider=lambda: now)
    state = service.create_session()
    repo = RecentTimetableCandidateRepository()
    candidate = _candidate(
        None,
        ["A-001"],
        session_version=state.version,
        generation_revision=state.generation_revision,
    )
    repo.save_candidates(state.session_id, [candidate.model_copy(update={"session_id": state.session_id})])
    service.update_preferences(state.session_id, hard_patch=None, soft_patch=None)
    tools = TimetableSelectionTools(
        session_service=service,
        revision_preparation_service=object(),
        recent_candidate_repository=repo,
    )
    result = tools.select_timetable_candidate({"session_id": state.session_id, "candidate_id": candidate.candidate_id})
    assert result.success is True


def test_stale_candidate_id_is_rejected_after_generation_input_changes() -> None:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    service = SessionService(InMemorySessionRepository(), now_provider=lambda: now)
    state = service.create_session()
    service.set_department(state.session_id, "컴퓨터공학과")
    state = service.get_session(state.session_id)
    repo = RecentTimetableCandidateRepository()
    candidate = _candidate(
        None,
        ["A-001"],
        session_version=state.version,
        generation_revision=state.generation_revision,
    )
    repo.save_candidates(state.session_id, [candidate.model_copy(update={"session_id": state.session_id})])
    service.set_department(state.session_id, "전자공학과")
    tools = TimetableSelectionTools(
        session_service=service,
        revision_preparation_service=object(),
        recent_candidate_repository=repo,
    )
    result = tools.select_timetable_candidate({"session_id": state.session_id, "candidate_id": candidate.candidate_id})
    assert result.success is False
    assert "이전 조건" in result.message







def test_validator_constructor_exclusive_minimum_is_used_without_call_flag() -> None:
    validator = TimetableValidator(min_credit=15, min_credit_inclusive=False)
    assert not validator.validate([_course("C-001", credit=15)]).valid


def test_preparation_request_preserves_inclusive_flags() -> None:
    from backend.app.agent_tools.schemas import SessionStateSummary
    from backend.app.models.course_discovery import CourseCandidate, CourseMatchType
    from backend.app.services.timetable_preparation_service import TimetablePreparationOptions, TimetablePreparationService

    summary = SessionStateSummary(
        session_id="s1",
        department="컴퓨터공학과",
        major_catalog_id="major",
        elective_catalog_id="elective",
        selected_major_course_ids=["M-001"],
        hard_constraints=HardConstraints(
            min_credit=15,
            min_credit_inclusive=False,
            max_credit=21,
            max_credit_inclusive=False,
        ),
        soft_preferences=SoftPreferences(),
        missing_information=[],
        updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        expires_at=datetime(2026, 1, 1, 1, tzinfo=timezone.utc),
    )
    result = TimetablePreparationService().prepare(
        summary,
        TimetablePreparationOptions(
            candidate_catalog_id="elective",
            fixed_section_sources=[SectionSource(catalog_id="major", section_id="M-001")],
            discovered_candidates=[],
            target_additional_course_count=1,
        ),
    )
    assert not result.ready
    result = TimetablePreparationService().prepare(
        summary,
        TimetablePreparationOptions(
            candidate_catalog_id="elective",
            fixed_section_sources=[SectionSource(catalog_id="major", section_id="M-001")],
            discovered_candidates=[CourseCandidate(course_id="E", course_code="E", course_name="E", category=Category.GENERAL_ELECTIVE, total_section_count=1, matching_section_count=1, matching_section_ids=["E-001"], match_reasons=["test"], match_type=CourseMatchType.CONDITION, rank_score=1)],
            target_additional_course_count=1,
        ),
    )
    assert result.ready
    assert result.request is not None
    assert result.request.min_credit_inclusive is False
    assert result.request.max_credit_inclusive is False


def test_exclusive_minimum_search_generates_candidate_above_boundary() -> None:
    from backend.app.models.course_load import CourseLoadTarget
    from backend.app.services.timetable_generator import TimetableGenerator

    fixed = [_course("M-001", credit=12)]
    electives = [
        Course(
            course_id="E1-001",
            course_name="E1",
            category=Category.GENERAL_ELECTIVE,
            area=1,
            credit=3,
            division="001",
            professor="교수",
            class_times=[ClassTime(day=Day.TUE, start="10:00", end="11:00", classroom="101", building_code="401")],
        ),
        Course(
            course_id="E2-001",
            course_name="E2",
            category=Category.GENERAL_ELECTIVE,
            area=1,
            credit=3,
            division="001",
            professor="교수",
            class_times=[ClassTime(day=Day.WED, start="10:00", end="11:00", classroom="101", building_code="401")],
        ),
    ]
    result = TimetableGenerator().generate_detailed(
        fixed_major_courses=fixed,
        elective_general_candidates=electives,
        course_load_target=CourseLoadTarget(additional_elective_count=1),
        min_credit=15,
        min_credit_inclusive=False,
        max_credit=18,
        max_credit_inclusive=True,
    )
    assert any(candidate.timetable.total_credit == 18 for candidate in result.candidates)


def test_compact_schedule_none_has_no_user_component() -> None:
    from backend.app.models.preference import PreferenceRules
    from backend.app.services.timetable_ranker import TimetableRanker

    ranked = TimetableRanker().rank([__import__("backend.app.models.timetable", fromlist=["Timetable"]).Timetable(courses=[_course("A-001")])], preferences=PreferenceRules())
    assert all(component.key != "compact_schedule" for component in ranked[0].score_components)


def test_legacy_logical_course_id_matches_section_suffix() -> None:
    from backend.app.models.preference import PreferenceRules
    from backend.app.models.timetable import Timetable
    from backend.app.services.timetable_ranker import TimetableRanker

    candidate = Timetable(courses=[_course("A100-001")])
    ranker = TimetableRanker()
    assert ranker.apply_hard_filters([candidate], preferences=PreferenceRules(required_course_ids=["A100"]))
    assert not ranker.apply_hard_filters([candidate], preferences=PreferenceRules(excluded_course_ids=["A100"]))
    ranked = ranker.rank([candidate], preferences=PreferenceRules(preferred_course_ids=["A100"], disliked_course_ids=["A100"]))
    keys = [component.key for component in ranked[0].score_components]
    assert "preferred_course" in keys
    assert "avoided_course" in keys


def test_session_unavailable_error_message_is_utf8() -> None:
    from backend.app.runtime import _session_unavailable_error

    assert _session_unavailable_error().message == "세션을 찾을 수 없거나 만료되었습니다."





def test_validation_normalizes_required_and_excluded_course_ids_with_division_suffix() -> None:
    from backend.app.services.timetable_validation_service import TimetableValidationService

    service = TimetableValidationService()
    section = _section("A100-001", "A100-001", "10:00", "11:00")

    assert service.validate_sections([section], required_course_ids=["A100"]).valid
    assert service.validate_sections([section], required_course_ids=["A100-001"]).valid

    excluded_logical = service.validate_sections([section], excluded_course_ids=["A100"])
    excluded_legacy = service.validate_sections([section], excluded_course_ids=["A100-001"])

    assert not excluded_logical.valid
    assert excluded_logical.violations[0].course_id == "A100"
    assert not excluded_legacy.valid
    assert excluded_legacy.violations[0].course_id == "A100"


def test_course_id_normalization_preserves_hyphenated_course_codes() -> None:
    from backend.app.services.timetable_validation_service import TimetableValidationService

    service = TimetableValidationService()
    section = _section("CS-A100-001", "CS-A100-001", "10:00", "11:00")

    assert service.validate_sections([section], required_course_ids=["CS-A100"]).valid
    assert service.validate_sections([section], required_course_ids=["CS-A100-001"]).valid

    missing = service.validate_sections([section], required_course_ids=["CS"])
    assert not missing.valid
    assert missing.violations[0].course_id == "CS"


def test_duplicate_course_violation_lists_both_section_ids_after_normalization() -> None:
    from backend.app.models.timetable_generation import TimetableViolationCode
    from backend.app.services.timetable_validation_service import TimetableValidationService

    first = _section("A100-001", "A100-001", "10:00", "11:00")
    second = _section("A100-002", "A100-002", "13:00", "14:00")

    result = TimetableValidationService().validate_sections([first, second])
    duplicate = next(
        item for item in result.violations
        if item.code is TimetableViolationCode.DUPLICATE_COURSE
    )

    assert duplicate.course_id == "A100"
    assert duplicate.conflicting_section_ids == ["A100-001", "A100-002"]


def test_agent_scoring_normalizes_legacy_course_ids_in_soft_preferences() -> None:
    from backend.app.models.timetable_scoring import ScoreComponentCode

    section = _section("A100-001", "A100-001", "10:00", "11:00")
    scorer = TimetableScoringService()

    preferred = scorer.score_candidate(
        candidate=_candidate("preferred-legacy", ["A100-001"]),
        sections=[ResolvedSection(catalog_id="catalog", section=section)],
        soft_preferences=SoftPreferences(preferred_course_ids=["A100-001"]),
    )
    disliked = scorer.score_candidate(
        candidate=_candidate("disliked-legacy", ["A100-001"]),
        sections=[ResolvedSection(catalog_id="catalog", section=section)],
        soft_preferences=SoftPreferences(disliked_course_ids=["A100"]),
    )

    preferred_component = next(
        component for component in preferred.score_components
        if component.code is ScoreComponentCode.PREFERRED_COURSES
    )
    disliked_component = next(
        component for component in disliked.score_components
        if component.code is ScoreComponentCode.DISLIKED_COURSES
    )

    assert preferred_component.details["included_course_ids"] == ["A100"]
    assert disliked_component.details["included_course_ids"] == ["A100"]
    assert disliked.total_score < 0


def test_compact_schedule_false_avoids_short_gaps_without_rewarding_longer_gaps() -> None:
    from backend.app.models.preference import PreferenceRules
    from backend.app.models.timetable import Timetable
    from backend.app.models.timetable_scoring import ScoreComponentCode
    from backend.app.services.timetable_ranker import TimetableRanker

    scorer = TimetableScoringService()
    adjacent = [_section("A-001", "A", "09:00", "10:00"), _section("B-001", "B", "10:00", "11:00")]
    gap_3h = [_section("C-001", "C", "09:00", "10:00"), _section("D-001", "D", "13:00", "14:00")]
    gap_6h = [_section("E-001", "E", "09:00", "10:00"), _section("F-001", "F", "16:00", "17:00")]

    adjacent_score = scorer.score_candidate(
        candidate=_candidate("adjacent", ["A-001", "B-001"]),
        sections=[ResolvedSection(catalog_id="catalog", section=item) for item in adjacent],
        soft_preferences=SoftPreferences(compact_schedule=False),
    )
    gap_3h_score = scorer.score_candidate(
        candidate=_candidate("gap-3h", ["C-001", "D-001"]),
        sections=[ResolvedSection(catalog_id="catalog", section=item) for item in gap_3h],
        soft_preferences=SoftPreferences(compact_schedule=False),
    )
    gap_6h_score = scorer.score_candidate(
        candidate=_candidate("gap-6h", ["E-001", "F-001"]),
        sections=[ResolvedSection(catalog_id="catalog", section=item) for item in gap_6h],
        soft_preferences=SoftPreferences(compact_schedule=False),
    )

    adjacent_component = next(
        component for component in adjacent_score.score_components
        if component.code is ScoreComponentCode.COMPACT_SCHEDULE
    )
    assert gap_3h_score.total_score > adjacent_score.total_score
    assert gap_6h_score.total_score == gap_3h_score.total_score
    assert adjacent_component.satisfied is False
    assert adjacent_component.details["short_gap_count"] == 1

    ranker = TimetableRanker()
    adjacent_timetable = Timetable(courses=[Course(course_id="RA-001", course_name="RA", category=Category.GENERAL_ELECTIVE, area=1, credit=3, division="001", professor="교수", class_times=[ClassTime(day=Day.MON, start="09:00", end="10:00", classroom="101", building_code="401")]), Course(course_id="RB-001", course_name="RB", category=Category.GENERAL_ELECTIVE, area=1, credit=3, division="001", professor="교수", class_times=[ClassTime(day=Day.MON, start="10:00", end="11:00", classroom="101", building_code="401")])])
    gap_3h_timetable = Timetable(courses=[Course(course_id="RC-001", course_name="RC", category=Category.GENERAL_ELECTIVE, area=1, credit=3, division="001", professor="교수", class_times=[ClassTime(day=Day.MON, start="09:00", end="10:00", classroom="101", building_code="401")]), Course(course_id="RD-001", course_name="RD", category=Category.GENERAL_ELECTIVE, area=1, credit=3, division="001", professor="교수", class_times=[ClassTime(day=Day.MON, start="13:00", end="14:00", classroom="101", building_code="401")])])
    gap_6h_timetable = Timetable(courses=[Course(course_id="RE-001", course_name="RE", category=Category.GENERAL_ELECTIVE, area=1, credit=3, division="001", professor="교수", class_times=[ClassTime(day=Day.MON, start="09:00", end="10:00", classroom="101", building_code="401")]), Course(course_id="RF-001", course_name="RF", category=Category.GENERAL_ELECTIVE, area=1, credit=3, division="001", professor="교수", class_times=[ClassTime(day=Day.MON, start="16:00", end="17:00", classroom="101", building_code="401")])])
    context = ranker.build_context(None, PreferenceRules(compact_schedule=False))

    adjacent_legacy = ranker._compact_schedule_component(adjacent_timetable, context, compact_preference=False)
    gap_3h_legacy = ranker._compact_schedule_component(gap_3h_timetable, context, compact_preference=False)
    gap_6h_legacy = ranker._compact_schedule_component(gap_6h_timetable, context, compact_preference=False)

    assert gap_3h_legacy.value > adjacent_legacy.value
    assert gap_6h_legacy.value == gap_3h_legacy.value
    assert "짧은 수업 간격" in adjacent_legacy.reason
    assert "깁니다" not in adjacent_legacy.reason


def test_morning_boundary_uses_shared_constant_for_parser_and_ranker() -> None:
    from backend.app.models.course import time_to_minutes
    from backend.app.services.preference_constants import MORNING_END_MINUTES, MORNING_END_TIME
    from backend.app.services.timetable_ranker import TimetableRanker

    assert time_to_minutes(MORNING_END_TIME) == MORNING_END_MINUTES

    ranker = TimetableRanker()
    before_boundary = Course(course_id="MORNING-001", course_name="MORNING", category=Category.GENERAL_ELECTIVE, area=1, credit=3, division="001", professor="교수", class_times=[ClassTime(day=Day.MON, start="09:59", end="10:30", classroom="101", building_code="401")])
    at_boundary = Course(course_id="TEN-001", course_name="TEN", category=Category.GENERAL_ELECTIVE, area=1, credit=3, division="001", professor="교수", class_times=[ClassTime(day=Day.MON, start="10:00", end="11:00", classroom="101", building_code="401")])
    after_boundary = Course(course_id="ELEVEN-001", course_name="ELEVEN", category=Category.GENERAL_ELECTIVE, area=1, credit=3, division="001", professor="교수", class_times=[ClassTime(day=Day.MON, start="11:00", end="12:00", classroom="101", building_code="401")])

    assert ranker._morning_class_count([before_boundary]) == 1
    assert ranker._morning_class_count([at_boundary]) == 0
    assert ranker._morning_class_count([after_boundary]) == 0


def test_normalize_requested_course_ids_matches_only_one_context_per_request_id() -> None:
    from backend.app.services.course_id_normalizer import normalize_requested_course_ids

    target = _section("A100-001", "A100-001", "10:00", "11:00")
    unrelated = _section("B200-002", "B200-002", "13:00", "14:00")

    assert normalize_requested_course_ids(["A100-001"], [target, unrelated]) == {"A100"}
    assert normalize_requested_course_ids(["MISSING-001"], [target, unrelated]) == {"MISSING-001"}


def test_validation_required_legacy_id_with_multiple_courses_is_not_reported_missing() -> None:
    from backend.app.models.timetable_generation import TimetableViolationCode
    from backend.app.services.timetable_validation_service import TimetableValidationService

    target = _section("A100-001", "A100-001", "10:00", "11:00")
    unrelated = _section("B200-002", "B200-002", "13:00", "14:00")

    result = TimetableValidationService().validate_sections(
        [target, unrelated],
        required_course_ids=["A100-001"],
    )

    assert result.valid
    assert not any(
        violation.code is TimetableViolationCode.MISSING_REQUIRED_COURSE
        and violation.course_id == "A100-001"
        for violation in result.violations
    )


def test_validation_excluded_legacy_id_with_multiple_courses_targets_only_matching_course() -> None:
    from backend.app.models.timetable_generation import TimetableViolationCode
    from backend.app.services.timetable_validation_service import TimetableValidationService

    target = _section("A100-001", "A100-001", "10:00", "11:00")
    unrelated = _section("B200-002", "B200-002", "13:00", "14:00")

    result = TimetableValidationService().validate_sections(
        [target, unrelated],
        excluded_course_ids=["A100-001"],
    )
    excluded = [
        violation for violation in result.violations
        if violation.code is TimetableViolationCode.EXCLUDED_COURSE_INCLUDED
    ]

    assert [violation.course_id for violation in excluded] == ["A100"]
    assert [violation.section_id for violation in excluded] == ["A100-001"]


def test_agent_scoring_legacy_ids_with_multiple_courses_do_not_count_included_as_missing() -> None:
    from backend.app.models.timetable_scoring import ScoreComponentCode

    target = _section("A100-001", "A100-001", "10:00", "11:00")
    unrelated = _section("B200-002", "B200-002", "13:00", "14:00")
    resolved = [ResolvedSection(catalog_id="catalog", section=item) for item in [target, unrelated]]
    scorer = TimetableScoringService()

    preferred = scorer.score_candidate(
        candidate=_candidate("preferred-multi", ["A100-001", "B200-002"]),
        sections=resolved,
        soft_preferences=SoftPreferences(preferred_course_ids=["A100-001"]),
    )
    disliked = scorer.score_candidate(
        candidate=_candidate("disliked-multi", ["A100-001", "B200-002"]),
        sections=resolved,
        soft_preferences=SoftPreferences(disliked_course_ids=["A100-001"]),
    )

    preferred_component = next(
        component for component in preferred.score_components
        if component.code is ScoreComponentCode.PREFERRED_COURSES
    )
    disliked_component = next(
        component for component in disliked.score_components
        if component.code is ScoreComponentCode.DISLIKED_COURSES
    )

    assert preferred_component.details["included_course_ids"] == ["A100"]
    assert preferred_component.details["missing_course_ids"] == []
    assert preferred.total_score == 8
    assert disliked_component.details["included_course_ids"] == ["A100"]
    assert disliked.tie_breaker["disliked_course_count"] == 1


def test_legacy_ranker_legacy_ids_with_multiple_courses_target_only_matching_course() -> None:
    from backend.app.models.preference import PreferenceRules
    from backend.app.models.timetable import Timetable
    from backend.app.services.timetable_ranker import TimetableRanker

    def rank_course(course_id: str, division: str, start: str, end: str) -> Course:
        return Course(
            course_id=course_id,
            course_name=course_id,
            category=Category.GENERAL_ELECTIVE,
            area=1,
            credit=3,
            division=division,
            professor="교수",
            class_times=[ClassTime(day=Day.MON, start=start, end=end, classroom="101", building_code="401")],
        )

    timetable = Timetable(courses=[
        rank_course("A100-001", "001", "09:00", "10:00"),
        rank_course("B200-002", "002", "13:00", "14:00"),
    ])
    ranker = TimetableRanker()

    assert ranker.apply_hard_filters(
        [timetable],
        preferences=PreferenceRules(required_course_ids=["A100-001"]),
    ) == [timetable]
    assert ranker.apply_hard_filters(
        [timetable],
        preferences=PreferenceRules(excluded_course_ids=["A100-001"]),
    ) == []

    ranked = ranker.rank(
        [timetable],
        preferences=PreferenceRules(
            preferred_course_ids=["A100-001"],
            disliked_course_ids=["A100-001"],
        ),
    )[0]
    components = {component.key: component for component in ranked.score_components}

    assert components["preferred_course"].reason.endswith("A100.")
    assert "preferred_course_missing" not in components
    assert components["avoided_course"].reason.endswith("A100.")
    assert "avoided_course_absent" not in components


def test_hyphenated_course_code_with_multiple_courses_is_not_truncated() -> None:
    from backend.app.services.course_id_normalizer import normalize_requested_course_ids
    from backend.app.services.timetable_validation_service import TimetableValidationService

    target = _section("CS-A100-001", "CS-A100-001", "10:00", "11:00")
    unrelated = _section("B200-002", "B200-002", "13:00", "14:00")

    assert normalize_requested_course_ids(["CS-A100-001"], [target, unrelated]) == {"CS-A100"}
    assert normalize_requested_course_ids(["CS-A100"], [target, unrelated]) == {"CS-A100"}
    assert normalize_requested_course_ids(["CS"], [target, unrelated]) == {"CS"}
    assert TimetableValidationService().validate_sections(
        [target, unrelated],
        required_course_ids=["CS-A100-001"],
    ).valid
