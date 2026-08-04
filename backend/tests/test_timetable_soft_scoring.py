from __future__ import annotations

from pydantic import ValidationError

from backend.app.agent_tools.timetable_scoring_tools import TimetableScoringTools
from backend.app.models.course import Category, ClassTime, Day
from backend.app.models.course_discovery import CourseSection
from backend.app.models.session_preferences import SoftPreferences
from backend.app.models.timetable_generation import (
    GeneratedTimetableCandidate,
    ResolvedSection,
    SectionSource,
    TimetableValidationResult,
    TimetableViolation,
    TimetableViolationCode,
)
from backend.app.models.timetable_scoring import (
    PreferenceEvidenceCode,
    ScoreComponentCode,
    ScoringErrorCode,
    TimetableScoringPolicy,
    TimetableScoringRequest,
)
from backend.app.services.timetable_scoring_service import TimetableScoringService
from backend.app.services.timetable_soft_ranking_service import TimetableRankingService


def _time(day: Day, start: str, end: str) -> ClassTime:
    return ClassTime(
        day=day,
        start=start,
        end=end,
        classroom="101",
        building_code="401",
    )


def _section(
    section_id: str,
    course_id: str | None = None,
    *,
    day: Day = Day.MON,
    start: str = "10:00",
    end: str = "11:00",
    times: list[ClassTime] | None = None,
) -> CourseSection:
    cid = course_id or section_id.rsplit("-", 1)[0]
    return CourseSection(
        section_id=section_id,
        course_id=cid,
        course_code=cid,
        course_name=f"강의 {cid}",
        category=Category.GENERAL_ELECTIVE,
        area=1,
        credit=3,
        division=section_id.rsplit("-", 1)[-1],
        professor="교수",
        class_times=times or [_time(day, start, end)],
    )


def _source(section_id: str) -> SectionSource:
    return SectionSource(catalog_id="catalog", section_id=section_id)


def _resolved(section: CourseSection) -> ResolvedSection:
    return ResolvedSection(catalog_id="catalog", section=section)


def _resolved_all(sections: list[CourseSection]) -> list[ResolvedSection]:
    return [_resolved(section) for section in sections]


def _candidate(
    candidate_id: str,
    section_ids: list[str],
    *,
    fixed: list[str] | None = None,
    valid: bool = True,
    order: int = 1,
) -> GeneratedTimetableCandidate:
    fixed_ids = fixed or []
    added_ids = [section_id for section_id in section_ids if section_id not in fixed_ids]
    return GeneratedTimetableCandidate(
        candidate_id=candidate_id,
        section_ids=section_ids,
        section_sources=[_source(section_id) for section_id in section_ids],
        fixed_section_ids=fixed_ids,
        fixed_section_sources=[_source(section_id) for section_id in fixed_ids],
        added_section_ids=added_ids,
        added_section_sources=[_source(section_id) for section_id in added_ids],
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
        generation_order=order,
    )


def _component(result, code: ScoreComponentCode):
    return next(component for component in result.score_components if component.code is code)


def test_scoring_request_policy_validation_and_empty_candidates() -> None:
    request = TimetableScoringRequest(candidates=[], max_ranked_results=1)
    assert request.candidates == []

    try:
        TimetableScoringRequest(max_ranked_results=0)
    except ValidationError as exc:
        assert "greater than or equal to 1" in str(exc)
    else:
        raise AssertionError("max_ranked_results=0 should fail")

    try:
        TimetableScoringPolicy(disliked_course_penalty=-1)
    except ValidationError as exc:
        assert "greater than or equal to 0" in str(exc)
    else:
        raise AssertionError("negative policy values should fail")

    result = TimetableRankingService().rank_candidates(request)
    assert result.success is True
    assert result.ranked_candidates == []
    assert result.returned_candidates == 0


def test_duplicate_candidate_ids_are_rejected() -> None:
    first = _candidate("same", ["A-001"])
    second = _candidate("same", ["B-001"])

    try:
        TimetableScoringRequest(candidates=[first, second])
    except ValidationError as exc:
        assert "duplicate candidate ids" in str(exc)
    else:
        raise AssertionError("duplicate candidate ids should fail")


def test_free_day_uses_complete_fixed_and_added_timetable() -> None:
    fixed_friday = _section("MAJ-001", "MAJ", day=Day.FRI)
    added_monday = _section("GEN-001", "GEN", day=Day.MON)
    candidate = _candidate("with-fixed-friday", ["MAJ-001", "GEN-001"], fixed=["MAJ-001"])

    scored = TimetableScoringService().score_candidate(
        candidate=candidate,
        sections=_resolved_all([fixed_friday, added_monday]),
        soft_preferences=SoftPreferences(preferred_free_days=[Day.FRI, Day.TUE]),
    )

    component = _component(scored, ScoreComponentCode.PREFERRED_FREE_DAYS)
    assert component.details["satisfied_count"] == 1
    assert component.details["unsatisfied_count"] == 1
    assert component.score == TimetableScoringPolicy().preferred_free_day_weight
    assert any(
        item.code is PreferenceEvidenceCode.FREE_DAY_PREFERENCE_UNSATISFIED
        and item.values["preferred_day"] == "FRI"
        for item in scored.unsatisfied_preferences
    )


def test_start_and_end_preferences_are_partial_linear_scores() -> None:
    early = _section("EARLY-001", "EARLY", day=Day.MON, start="09:00", end="18:30")
    late = _section("LATE-001", "LATE", day=Day.TUE, start="10:30", end="16:00")
    policy = TimetableScoringPolicy(
        preferred_start_time_weight=10,
        early_start_penalty_per_minute=0.1,
        preferred_end_time_weight=10,
        late_end_penalty_per_minute=0.2,
    )

    scored = TimetableScoringService(policy=policy).score_candidate(
        candidate=_candidate("time", ["EARLY-001", "LATE-001"]),
        sections=_resolved_all([early, late]),
        soft_preferences=SoftPreferences(
            preferred_earliest_start_time="10:00",
            preferred_latest_end_time="17:00",
        ),
        policy=policy,
    )

    start_component = _component(scored, ScoreComponentCode.PREFERRED_START_TIME)
    end_component = _component(scored, ScoreComponentCode.PREFERRED_END_TIME)
    assert start_component.score == 4
    assert start_component.details["max_difference_minutes"] == 60
    assert start_component.details["violated_days"] == ["MON"]
    assert end_component.score == -8
    assert end_component.details["max_difference_minutes"] == 90
    assert end_component.details["violated_days"] == ["MON"]
    assert scored.total_score == -4


def test_preferred_and_disliked_courses_are_counted_once_without_filtering() -> None:
    preferred_a = _section("PA-001", "PA", day=Day.MON)
    preferred_a_duplicate = _section("PA-002", "PA", day=Day.TUE)
    disliked = _section("BAD-001", "BAD", day=Day.WED)

    scored = TimetableScoringService().score_candidate(
        candidate=_candidate("courses", ["PA-001", "PA-002", "BAD-001"], fixed=["PA-001"]),
        sections=_resolved_all([preferred_a, preferred_a_duplicate, disliked]),
        soft_preferences=SoftPreferences(
            preferred_course_ids=["PA", "MISSING"],
            disliked_course_ids=["BAD"],
        ),
    )

    preferred = _component(scored, ScoreComponentCode.PREFERRED_COURSES)
    disliked_component = _component(scored, ScoreComponentCode.DISLIKED_COURSES)
    assert preferred.score == TimetableScoringPolicy().preferred_course_weight
    assert preferred.details["included_course_ids"] == ["PA"]
    assert disliked_component.score == -TimetableScoringPolicy().disliked_course_penalty
    assert any(
        item.code is PreferenceEvidenceCode.DISLIKED_COURSE_INCLUDED
        for item in scored.unsatisfied_preferences
    )


def test_compact_schedule_counts_only_between_classes_on_same_day() -> None:
    morning = _section("A-001", "A", day=Day.MON, start="09:00", end="10:00")
    afternoon = _section("B-001", "B", day=Day.MON, start="13:00", end="14:00")
    next_day = _section("C-001", "C", day=Day.TUE, start="09:00", end="10:00")
    policy = TimetableScoringPolicy(gap_penalty_per_minute=0.05, long_gap_penalty=5)

    scored = TimetableScoringService(policy=policy).score_candidate(
        candidate=_candidate("gap", ["A-001", "B-001", "C-001"]),
        sections=_resolved_all([morning, afternoon, next_day]),
        soft_preferences=SoftPreferences(compact_schedule=True),
        policy=policy,
    )

    component = _component(scored, ScoreComponentCode.COMPACT_SCHEDULE)
    assert component.details["total_gap_minutes"] == 180
    assert component.details["long_gap_count"] == 1
    assert component.score == -6
    assert component.satisfied is False
    assert any(
        item.code is PreferenceEvidenceCode.COMPACT_SCHEDULE_MODERATE
        for item in scored.unsatisfied_preferences
    )
    assert not any(
        item.code is PreferenceEvidenceCode.COMPACT_SCHEDULE_MODERATE
        for item in scored.satisfied_preferences
    )
    assert scored.trade_offs[0].values["gaps_by_day"] == {"MON": [180]}


def test_compact_false_and_empty_soft_preferences_do_not_add_implicit_scores() -> None:
    sections = [
        _section("A-001", "A", day=Day.MON, start="09:00", end="10:00"),
        _section("B-001", "B", day=Day.MON, start="13:00", end="14:00"),
    ]
    candidate = _candidate("no-prefs", ["A-001", "B-001"])

    compact_false = TimetableScoringService().score_candidate(
        candidate=candidate,
        sections=_resolved_all(sections),
        soft_preferences=SoftPreferences(compact_schedule=False),
    )
    empty = TimetableScoringService().score_candidate(
        candidate=candidate,
        sections=_resolved_all(sections),
        soft_preferences=SoftPreferences(),
    )

    assert compact_false.total_score == 0
    assert empty.total_score == 0
    assert compact_false.score_components == []
    assert empty.score_components == []
    assert empty.trade_offs[-1].code is PreferenceEvidenceCode.NO_SOFT_PREFERENCES


def test_scores_are_absolute_not_relative_and_allow_values_above_100() -> None:
    section = _section("A-001", "A", day=Day.TUE, start="10:00", end="11:00")
    candidate = _candidate("absolute", ["A-001"])
    prefs = SoftPreferences(
        preferred_free_days=[Day.MON],
        preferred_earliest_start_time="09:00",
        preferred_latest_end_time="18:00",
        preferred_course_ids=["A"],
    )
    policy = TimetableScoringPolicy(
        preferred_free_day_weight=60,
        preferred_start_time_weight=30,
        preferred_end_time_weight=30,
        preferred_course_weight=20,
    )
    service = TimetableScoringService(policy=policy)

    solo = service.score_candidate(
        candidate=candidate,
        sections=_resolved_all([section]),
        soft_preferences=prefs,
        policy=policy,
    )
    with_other = TimetableRankingService(scoring_service=service, policy=policy).rank(
        candidates=[candidate, _candidate("other", ["A-001"], order=2)],
        sections=_resolved_all([section]),
        soft_preferences=prefs,
        scoring_policy=policy,
    )

    assert solo.total_score == 140
    assert with_other.ranked_candidates[0].total_score == solo.total_score


def test_empty_soft_preferences_do_not_use_gap_as_tie_breaker() -> None:
    no_gap = _candidate("c-no-gap", ["A-001", "B-001"], order=1)
    gap = _candidate("a-gap", ["C-001", "D-001"], order=2)
    sections = [
        _section("A-001", "A", day=Day.MON, start="09:00", end="10:00"),
        _section("B-001", "B", day=Day.MON, start="10:00", end="11:00"),
        _section("C-001", "C", day=Day.MON, start="09:00", end="10:00"),
        _section("D-001", "D", day=Day.MON, start="13:00", end="14:00"),
    ]

    ranked = TimetableRankingService().rank(
        candidates=[gap, no_gap],
        sections=_resolved_all(sections),
        soft_preferences=SoftPreferences(),
        max_ranked_results=2,
    )

    assert [item.candidate_id for item in ranked.ranked_candidates] == [
        "a-gap",
        "c-no-gap",
    ]
    assert [item.rank for item in ranked.ranked_candidates] == [1, 2]


def test_compact_schedule_true_uses_gap_as_tie_breaker_when_scores_match() -> None:
    no_gap = _candidate("z-no-gap", ["A-001", "B-001"], order=1)
    short_gap = _candidate("a-short-gap", ["C-001", "D-001"], order=2)
    sections = [
        _section("A-001", "A", day=Day.MON, start="09:00", end="10:00"),
        _section("B-001", "B", day=Day.MON, start="10:00", end="11:00"),
        _section("C-001", "C", day=Day.MON, start="09:00", end="10:00"),
        _section("D-001", "D", day=Day.MON, start="11:00", end="12:00"),
    ]
    policy = TimetableScoringPolicy(gap_penalty_per_minute=0, long_gap_penalty=0)

    ranked = TimetableRankingService(policy=policy).rank(
        candidates=[short_gap, no_gap],
        sections=_resolved_all(sections),
        soft_preferences=SoftPreferences(compact_schedule=True),
        max_ranked_results=2,
        scoring_policy=policy,
    )

    assert [item.total_score for item in ranked.ranked_candidates] == [8, 8]
    assert [item.candidate_id for item in ranked.ranked_candidates] == [
        "z-no-gap",
        "a-short-gap",
    ]


def test_latest_end_is_ignored_without_end_time_preference() -> None:
    early_end = _candidate("z-early-end", ["A-001"])
    late_end = _candidate("a-late-end", ["B-001"])
    sections = [
        _section("A-001", "A", day=Day.MON, start="14:00", end="15:00"),
        _section("B-001", "B", day=Day.MON, start="17:00", end="18:00"),
    ]

    ranked = TimetableRankingService().rank(
        candidates=[early_end, late_end],
        sections=_resolved_all(sections),
        soft_preferences=SoftPreferences(),
        max_ranked_results=2,
    )

    assert [item.candidate_id for item in ranked.ranked_candidates] == [
        "a-late-end",
        "z-early-end",
    ]


def test_latest_end_is_used_when_end_time_preference_is_set_and_scores_match() -> None:
    early_end = _candidate("z-early-end", ["A-001"])
    late_end = _candidate("a-late-end", ["B-001"])
    sections = [
        _section("A-001", "A", day=Day.MON, start="14:00", end="15:00"),
        _section("B-001", "B", day=Day.MON, start="17:00", end="18:00"),
    ]

    ranked = TimetableRankingService().rank(
        candidates=[late_end, early_end],
        sections=_resolved_all(sections),
        soft_preferences=SoftPreferences(preferred_latest_end_time="19:00"),
        max_ranked_results=2,
    )

    assert [item.total_score for item in ranked.ranked_candidates] == [10, 10]
    assert [item.candidate_id for item in ranked.ranked_candidates] == [
        "z-early-end",
        "a-late-end",
    ]


def test_compact_schedule_satisfied_evidence_matches_component_status() -> None:
    sections = [
        _section("A-001", "A", day=Day.MON, start="09:00", end="10:00"),
        _section("B-001", "B", day=Day.MON, start="10:30", end="11:30"),
    ]

    scored = TimetableScoringService().score_candidate(
        candidate=_candidate("compact-ok", ["A-001", "B-001"]),
        sections=_resolved_all(sections),
        soft_preferences=SoftPreferences(compact_schedule=True),
    )

    component = _component(scored, ScoreComponentCode.COMPACT_SCHEDULE)
    assert component.satisfied is True
    assert any(
        item.code is PreferenceEvidenceCode.COMPACT_SCHEDULE_STRONG
        for item in scored.satisfied_preferences
    )
    assert not any(
        item.code is PreferenceEvidenceCode.COMPACT_SCHEDULE_STRONG
        for item in scored.unsatisfied_preferences
    )


def test_time_preference_details_include_all_violated_days() -> None:
    sections = [
        _section("M-001", "M", day=Day.MON, start="09:00", end="18:30"),
        _section("W-001", "W", day=Day.WED, start="09:00", end="16:00"),
        _section("F-001", "F", day=Day.FRI, start="09:00", end="17:30"),
        _section("T-001", "T", day=Day.TUE, start="11:00", end="18:30"),
        _section("R-001", "R", day=Day.THU, start="11:00", end="18:30"),
    ]

    scored = TimetableScoringService().score_candidate(
        candidate=_candidate(
            "violated-days",
            ["M-001", "W-001", "F-001", "T-001", "R-001"],
        ),
        sections=_resolved_all(sections),
        soft_preferences=SoftPreferences(
            preferred_earliest_start_time="10:00",
            preferred_latest_end_time="17:00",
        ),
    )

    assert _component(
        scored,
        ScoreComponentCode.PREFERRED_START_TIME,
    ).details["violated_days"] == ["MON", "WED", "FRI"]
    assert _component(
        scored,
        ScoreComponentCode.PREFERRED_END_TIME,
    ).details["violated_days"] == ["MON", "TUE", "THU", "FRI"]


def test_final_tie_uses_candidate_id() -> None:
    first = _candidate("b-candidate", ["A-001"])
    second = _candidate("a-candidate", ["B-001"])
    sections = [
        _section("A-001", "A", day=Day.MON),
        _section("B-001", "B", day=Day.MON),
    ]

    ranked = TimetableRankingService().rank(
        candidates=[first, second],
        sections=_resolved_all(sections),
        soft_preferences=SoftPreferences(),
        max_ranked_results=2,
    )

    assert [item.candidate_id for item in ranked.ranked_candidates] == [
        "a-candidate",
        "b-candidate",
    ]


def test_invalid_hard_candidate_and_missing_sections_fail_without_ranked_results() -> None:
    invalid = _candidate("invalid", ["A-001"], valid=False)
    missing = _candidate("missing", ["MISSING-001"])

    invalid_result = TimetableRankingService().rank(
        candidates=[invalid],
        sections=_resolved_all([_section("A-001", "A")]),
        soft_preferences=SoftPreferences(),
    )
    missing_result = TimetableRankingService().rank(
        candidates=[missing],
        sections=[],
        soft_preferences=SoftPreferences(),
    )

    assert invalid_result.success is False
    assert invalid_result.error is not None
    assert invalid_result.error.code is ScoringErrorCode.INVALID_CANDIDATE
    assert missing_result.success is False
    assert missing_result.error is not None
    assert missing_result.error.code is ScoringErrorCode.SECTION_DETAILS_MISSING


def test_agent_tools_delegate_to_services_and_do_not_mutate_inputs() -> None:
    candidate = _candidate("tool", ["A-001"])
    section = _section("A-001", "A")
    tools = TimetableScoringTools()

    scored = tools.score_timetable_candidate(
        {
            "candidate": candidate.model_dump(),
            "sections": [_resolved(section).model_dump()],
            "soft_preferences": {"preferred_course_ids": ["A"]},
        }
    )
    ranked = tools.rank_timetable_candidates(
        {
            "candidates": [candidate.model_dump()],
            "sections": [_resolved(section).model_dump()],
            "soft_preferences": {"preferred_course_ids": ["A"]},
            "max_ranked_results": 1,
        }
    )

    assert not isinstance(scored, TimetableScoringPolicy)
    assert scored.candidate_id == "tool"
    assert ranked.success is True
    assert ranked.ranked_candidates[0].candidate_id == "tool"
    assert candidate.validation.valid is True
