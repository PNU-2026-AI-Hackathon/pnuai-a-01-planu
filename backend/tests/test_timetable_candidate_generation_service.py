from __future__ import annotations

from backend.app.agent_tools.timetable_generation_tools import TimetableGenerationTools
from backend.app import deps
from backend.app.models.course import Category, ClassTime, Course, Day
from backend.app.models.course_discovery import CatalogKind
from backend.app.models.timetable_generation import (
    GenerationFailureCode,
    SearchTerminationReason,
    SectionSource,
    TimetableGenerationRequest,
    TimetableValidationRequest,
    TimetableViolationCode,
)
from backend.app.repositories.in_memory_catalog_repository import InMemoryCatalogRepository
from backend.app.services.general_course_pool_service import (
    CourseRestrictionPolicy,
    DepartmentRestrictionRule,
)
from backend.app.services.timetable_candidate_generation_service import (
    TimetableCandidateGenerationService,
)
from backend.app.services.timetable_candidate_validation_service import (
    TimetableCandidateValidationService,
)
from backend.app.services.timetable_validation_service import TimetableValidationService


def _course(
    section_id: str,
    course_name: str,
    *,
    day: Day = Day.MON,
    start: str = "09:00",
    end: str = "10:00",
    building_code: str = "401",
    category: Category = Category.GENERAL_ELECTIVE,
    area: int | None = 1,
    credit: float = 3,
    division: str | None = None,
) -> Course:
    return Course(
        course_id=section_id,
        course_name=course_name,
        category=category,
        area=area,
        credit=credit,
        division=division or section_id.rsplit("-", 1)[-1],
        professor="교수",
        class_times=[
            ClassTime(
                day=day,
                start=start,
                end=end,
                classroom=f"{building_code}-101",
                building_code=building_code,
            )
        ],
    )


def _repo() -> InMemoryCatalogRepository:
    repo = InMemoryCatalogRepository()
    repo.register(
        "major",
        kind=CatalogKind.MAJOR,
        courses=[
            _course(
                "M001-001",
                "전공",
                start="09:00",
                end="10:00",
                category=Category.MAJOR_REQUIRED,
                area=None,
            )
        ],
    )
    repo.register(
        "general",
        kind=CatalogKind.ELECTIVE,
        courses=[
            _course("G101-001", "교양A", start="10:30", end="11:30"),
            _course("G101-002", "교양A", start="09:30", end="10:30"),
            _course("G102-001", "교양B", day=Day.TUE, start="11:00", end="12:00"),
            _course("G103-001", "교양C", day=Day.WED, start="08:00", end="09:00"),
            _course("G104-001", "교양D", day=Day.THU, start="17:00", end="19:00"),
            _course("G105-001", "교양E", start="10:10", end="11:00", building_code="701"),
        ],
    )
    return repo


def _credit_repo() -> InMemoryCatalogRepository:
    repo = InMemoryCatalogRepository()
    repo.register(
        "credits",
        kind=CatalogKind.ELECTIVE,
        courses=[
            _course("C101-001", "저학점A", day=Day.MON, start="09:00", end="10:00", credit=1),
            _course("C102-001", "저학점B", day=Day.TUE, start="09:00", end="10:00", credit=1),
            _course("C103-001", "고학점C", day=Day.WED, start="09:00", end="10:00", credit=3),
            _course("C104-001", "고학점D", day=Day.THU, start="09:00", end="10:00", credit=3),
        ],
    )
    return repo


def _source(catalog_id: str, section_id: str) -> SectionSource:
    return SectionSource(catalog_id=catalog_id, section_id=section_id)


def _service(repo: InMemoryCatalogRepository) -> TimetableCandidateGenerationService:
    return TimetableCandidateGenerationService(catalog_repository=repo)


def _restricted_tool_repo() -> InMemoryCatalogRepository:
    repo = InMemoryCatalogRepository()
    repo.register(
        "restricted",
        kind=CatalogKind.ELECTIVE,
        courses=[
            _course(
                "REQ101-001",
                "열린교필",
                category=Category.GENERAL_REQUIRED,
                day=Day.MON,
                start="09:00",
                end="10:00",
            ),
            _course(
                "REQ102-001",
                "규칙없는교필",
                category=Category.GENERAL_REQUIRED,
                day=Day.TUE,
                start="09:00",
                end="10:00",
            ),
        ],
    )
    return repo


def _restricted_tools(repo: InMemoryCatalogRepository) -> TimetableGenerationTools:
    validation_service = TimetableValidationService(
        restriction_policy=CourseRestrictionPolicy(
            rules=[
                DepartmentRestrictionRule(
                    course_code="REQ101",
                    division="001",
                    allowed_departments=frozenset({"정보컴퓨터공학부"}),
                    blocked_departments=frozenset({"기계공학부"}),
                )
            ]
        )
    )
    return TimetableGenerationTools(
        generation_service=TimetableCandidateGenerationService(
            catalog_repository=repo,
            validation_service=validation_service,
        ),
        validation_service=TimetableCandidateValidationService(
            catalog_repository=repo,
            validation_service=validation_service,
        ),
    )


def test_generation_request_normalizes_duplicates_and_rejects_bad_values() -> None:
    request = TimetableGenerationRequest(
        fixed_section_sources=[
            _source("major", "M001-001"),
            _source("major", "M001-001"),
        ],
        candidate_course_ids=["G101", "G101"],
        candidate_section_sources_by_course={
            "G101": [_source("general", "G101-001")],
        },
    )

    assert request.fixed_section_sources == [_source("major", "M001-001")]
    assert request.candidate_course_ids == ["G101"]
    assert request.candidate_course_ids_for_search == ["G101"]
    assert request.ordered_candidate_course_ids == ["G101"]

    try:
        TimetableGenerationRequest(
            candidate_course_ids=["G101"],
            candidate_section_sources_by_course={"G101": [_source("general", "G101-001")]},
            target_additional_course_count=-1,
        )
    except ValueError as exc:
        assert "greater than or equal to 0" in str(exc)
    else:
        raise AssertionError("negative target should fail")


def test_agent_tool_generation_applies_allowed_department_restriction() -> None:
    tools = _restricted_tools(_restricted_tool_repo())

    result = tools.generate_timetable_candidates(
        {
            "candidate_course_ids": ["REQ101"],
            "candidate_section_sources_by_course": {
                "REQ101": [{"catalog_id": "restricted", "section_id": "REQ101-001"}]
            },
            "department": "정보컴퓨터공학부",
            "target_additional_course_count": 1,
        }
    )

    assert result.success is True
    assert result.candidates[0].section_sources == [_source("restricted", "REQ101-001")]
    assert result.failure_reasons == []


def test_dependency_provider_injects_shared_real_restriction_policy(monkeypatch) -> None:
    rules = [
        DepartmentRestrictionRule(
            course_code="REQ101",
            division="001",
            allowed_departments=frozenset({"정보컴퓨터공학부"}),
            blocked_departments=frozenset({"기계공학부"}),
        )
    ]
    monkeypatch.setattr(
        deps,
        "load_department_restriction_rules",
        lambda _path: rules,
    )
    deps.clear_dependency_caches()

    validation_service = deps.get_timetable_validation_service()
    generation_service = deps.get_timetable_candidate_generation_service()
    candidate_validation_service = deps.get_timetable_candidate_validation_service()

    assert generation_service.validation_service is validation_service
    assert candidate_validation_service.validation_service is validation_service
    assert validation_service.restriction_policy.rules_by_course_section

    deps.clear_dependency_caches()


def test_agent_tool_generation_rejects_blocked_department() -> None:
    tools = _restricted_tools(_restricted_tool_repo())

    result = tools.generate_timetable_candidates(
        {
            "candidate_course_ids": ["REQ101"],
            "candidate_section_sources_by_course": {
                "REQ101": [{"catalog_id": "restricted", "section_id": "REQ101-001"}]
            },
            "department": "기계공학부",
            "target_additional_course_count": 1,
        }
    )

    assert result.success is False
    assert GenerationFailureCode.DEPARTMENT_INELIGIBLE in {
        reason.code for reason in result.failure_reasons
    }


def test_agent_tool_generation_rejects_missing_general_required_rule() -> None:
    tools = _restricted_tools(_restricted_tool_repo())

    result = tools.generate_timetable_candidates(
        {
            "candidate_course_ids": ["REQ102"],
            "candidate_section_sources_by_course": {
                "REQ102": [{"catalog_id": "restricted", "section_id": "REQ102-001"}]
            },
            "department": "정보컴퓨터공학부",
            "target_additional_course_count": 1,
        }
    )

    assert result.success is False
    assert GenerationFailureCode.DEPARTMENT_INELIGIBLE in {
        reason.code for reason in result.failure_reasons
    }
    assert any("규칙" in reason.message for reason in result.failure_reasons)


def test_same_section_id_from_different_catalogs_remains_distinct_in_validation() -> None:
    repo = InMemoryCatalogRepository()
    repo.register(
        "catalog-a",
        kind=CatalogKind.ELECTIVE,
        courses=[_course("DUP101-001", "중복A", day=Day.MON, start="09:00", end="10:00")],
    )
    repo.register(
        "catalog-b",
        kind=CatalogKind.ELECTIVE,
        courses=[_course("DUP101-001", "중복B", day=Day.MON, start="09:30", end="10:30")],
    )
    tools = TimetableGenerationTools(
        generation_service=TimetableCandidateGenerationService(catalog_repository=repo),
        validation_service=TimetableCandidateValidationService(catalog_repository=repo),
    )

    result = tools.validate_timetable_candidate(
        {
            "section_sources": [
                {"catalog_id": "catalog-a", "section_id": "DUP101-001"},
                {"catalog_id": "catalog-b", "section_id": "DUP101-001"},
            ]
        }
    )

    assert result.checked_section_ids == ["DUP101-001", "DUP101-001"]
    assert result.checked_section_sources == [
        _source("catalog-a", "DUP101-001"),
        _source("catalog-b", "DUP101-001"),
    ]


def test_same_section_id_from_different_catalogs_builds_distinct_candidate_ids() -> None:
    repo = InMemoryCatalogRepository()
    for catalog_id, course_name in (("catalog-a", "중복A"), ("catalog-b", "중복B")):
        repo.register(
            catalog_id,
            kind=CatalogKind.ELECTIVE,
            courses=[
                _course(
                    "DUP101-001",
                    course_name,
                    day=Day.MON,
                    start="09:00",
                    end="10:00",
                ),
                _course(
                    "GEN201-001",
                    "추가교양",
                    day=Day.TUE,
                    start="10:00",
                    end="11:00",
                ),
            ],
        )
    service = TimetableCandidateGenerationService(catalog_repository=repo)

    first = service.generate(
        TimetableGenerationRequest(
            fixed_section_sources=[_source("catalog-a", "DUP101-001")],
            candidate_course_ids=["GEN201"],
            candidate_section_sources_by_course={
                "GEN201": [_source("catalog-a", "GEN201-001")]
            },
        )
    )
    second = service.generate(
        TimetableGenerationRequest(
            fixed_section_sources=[_source("catalog-b", "DUP101-001")],
            candidate_course_ids=["GEN201"],
            candidate_section_sources_by_course={
                "GEN201": [_source("catalog-b", "GEN201-001")]
            },
        )
    )

    assert first.candidates[0].candidate_id != second.candidates[0].candidate_id
    assert first.candidates[0].fixed_section_sources == [_source("catalog-a", "DUP101-001")]
    assert second.candidates[0].fixed_section_sources == [_source("catalog-b", "DUP101-001")]


def test_generate_prunes_conflicts_and_keeps_one_section_per_course() -> None:
    result = _service(_repo()).generate(
        TimetableGenerationRequest(
            fixed_section_sources=[_source("major", "M001-001")],
            candidate_course_ids=["G101", "G102"],
            candidate_section_sources_by_course={
                "G101": [_source("general", "G101-001"), _source("general", "G101-002")],
                "G102": [_source("general", "G102-001")],
            },
            target_additional_course_count=2,
            max_results=3,
        )
    )

    assert result.success is True
    assert result.search_nodes_visited > 0
    assert result.candidates[0].added_section_ids == ["G101-001", "G102-001"]
    assert all(candidate.validation.valid for candidate in result.candidates)
    assert all(
        len(candidate.added_section_ids) == len(set(candidate.course_ids) - {"M001"})
        for candidate in result.candidates
    )
    assert result.failure_reasons == []
    assert any(
        reason.code == GenerationFailureCode.TIME_CONFLICT
        for reason in result.search_diagnostics
    )


def test_fixed_timetable_is_validated_before_search_starts() -> None:
    repo = _repo()
    repo.register(
        "bad-major",
        kind=CatalogKind.MAJOR,
        courses=[
            _course("M002-001", "전공2", start="09:30", end="10:30", category=Category.MAJOR_REQUIRED, area=None)
        ],
    )

    result = _service(repo).generate(
        TimetableGenerationRequest(
            fixed_section_sources=[
                _source("major", "M001-001"),
                _source("bad-major", "M002-001"),
            ],
            candidate_course_ids=["G102"],
            candidate_section_sources_by_course={"G102": [_source("general", "G102-001")]},
            target_additional_course_count=1,
        )
    )

    assert result.success is False
    assert result.search_nodes_visited == 0
    assert result.error is not None
    assert result.error.code == GenerationFailureCode.FIXED_TIMETABLE_CONFLICT


def test_required_course_unavailable_and_hard_filtered_sections_are_structured() -> None:
    result = _service(_repo()).generate(
        TimetableGenerationRequest(
            fixed_section_sources=[_source("major", "M001-001")],
            candidate_course_ids=["G103"],
            candidate_section_sources_by_course={"G103": [_source("general", "G103-001")]},
            required_course_ids=["G103"],
            required_free_days=[Day.WED],
            target_additional_course_count=1,
        )
    )

    assert result.success is False
    assert any(
        reason.code == GenerationFailureCode.REQUIRED_FREE_DAY_VIOLATION
        for reason in result.failure_reasons
    )
    assert any(
        reason.code == GenerationFailureCode.REQUIRED_COURSE_UNAVAILABLE
        for reason in result.failure_reasons
    )


def test_department_and_campus_rules_are_reused() -> None:
    repo = _repo()
    validation = TimetableValidationService(
        restriction_policy=CourseRestrictionPolicy(
            rules=[
                DepartmentRestrictionRule(
                    course_code="G102",
                    division="001",
                    allowed_departments=frozenset(),
                    blocked_departments=frozenset({"국어국문학과"}),
                )
            ]
        )
    )
    generation = TimetableCandidateGenerationService(
        catalog_repository=repo,
        validation_service=validation,
    )

    ineligible = generation.generate(
        TimetableGenerationRequest(
            candidate_course_ids=["G102"],
            candidate_section_sources_by_course={"G102": [_source("general", "G102-001")]},
            department="국어국문학과",
            target_additional_course_count=1,
        )
    )
    movement = generation.generate(
        TimetableGenerationRequest(
            fixed_section_sources=[_source("major", "M001-001")],
            candidate_course_ids=["G105"],
            candidate_section_sources_by_course={"G105": [_source("general", "G105-001")]},
            target_additional_course_count=1,
        )
    )

    assert any(reason.code == GenerationFailureCode.DEPARTMENT_INELIGIBLE for reason in ineligible.failure_reasons)
    assert any(reason.code == GenerationFailureCode.CAMPUS_MOVEMENT_VIOLATION for reason in movement.failure_reasons)


def test_limits_and_order_are_deterministic() -> None:
    request = TimetableGenerationRequest(
        candidate_course_ids=["G102", "G101"],
        candidate_section_sources_by_course={
            "G102": [_source("general", "G102-001")],
            "G101": [_source("general", "G101-001")],
        },
        target_additional_course_count=1,
        max_results=1,
    )
    first = _service(_repo()).generate(request)
    second = _service(_repo()).generate(request)

    assert first.search_truncated is True
    assert first.termination_reason == SearchTerminationReason.MAX_RESULTS_REACHED
    assert [candidate.candidate_id for candidate in first.candidates] == [
        candidate.candidate_id for candidate in second.candidates
    ]
    assert first.candidates[0].added_section_ids == second.candidates[0].added_section_ids
    assert first.termination_reason == second.termination_reason


def test_duplicate_candidates_are_not_returned_when_target_count_is_met_early() -> None:
    result = _service(_repo()).generate(
        TimetableGenerationRequest(
            candidate_course_ids=["G101", "G102", "G103"],
            candidate_section_sources_by_course={
                "G101": [_source("general", "G101-001")],
                "G102": [_source("general", "G102-001")],
                "G103": [_source("general", "G103-001")],
            },
            target_additional_course_count=1,
            max_results=10,
        )
    )

    candidate_ids = [candidate.candidate_id for candidate in result.candidates]

    assert len(candidate_ids) == len(set(candidate_ids))
    assert len(result.candidates) == 3
    assert result.termination_reason == SearchTerminationReason.SEARCH_EXHAUSTED


def test_max_results_is_filled_with_distinct_candidates() -> None:
    result = _service(_repo()).generate(
        TimetableGenerationRequest(
            candidate_course_ids=["G101", "G102", "G103", "G104"],
            candidate_section_sources_by_course={
                "G101": [_source("general", "G101-001")],
                "G102": [_source("general", "G102-001")],
                "G103": [_source("general", "G103-001")],
                "G104": [_source("general", "G104-001")],
            },
            target_additional_course_count=1,
            max_results=3,
        )
    )

    candidate_ids = [candidate.candidate_id for candidate in result.candidates]

    assert len(result.candidates) == 3
    assert len(candidate_ids) == len(set(candidate_ids))
    assert len({tuple(candidate.section_ids) for candidate in result.candidates}) == 3
    assert result.termination_reason == SearchTerminationReason.MAX_RESULTS_REACHED
    assert not any(
        reason.code == GenerationFailureCode.SEARCH_LIMIT_REACHED
        for reason in result.failure_reasons
    )


def test_search_node_limit_has_its_own_termination_reason() -> None:
    result = _service(_repo()).generate(
        TimetableGenerationRequest(
            candidate_course_ids=["G101", "G102"],
            candidate_section_sources_by_course={
                "G101": [_source("general", "G101-001")],
                "G102": [_source("general", "G102-001")],
            },
            target_additional_course_count=1,
            max_results=10,
            max_search_nodes=1,
        )
    )

    assert result.search_truncated is True
    assert result.termination_reason == SearchTerminationReason.MAX_SEARCH_NODES_REACHED
    assert any(
        reason.code == GenerationFailureCode.SEARCH_LIMIT_REACHED
        for reason in result.failure_reasons
    )


def test_skip_branch_stops_immediately_after_max_results() -> None:
    request = TimetableGenerationRequest(
        candidate_course_ids=["G101", "G102"],
        candidate_section_sources_by_course={
            "G101": [_source("general", "G101-001")],
            "G102": [_source("general", "G102-001")],
        },
        target_additional_course_count=1,
        max_results=1,
        max_search_nodes=10,
    )

    first = _service(_repo()).generate(request)
    second = _service(_repo()).generate(request)

    assert len(first.candidates) == 1
    assert first.termination_reason == SearchTerminationReason.MAX_RESULTS_REACHED
    assert first.search_nodes_visited == 1
    assert first.search_nodes_visited == second.search_nodes_visited


def test_search_nodes_never_exceed_max_search_nodes() -> None:
    request = TimetableGenerationRequest(
        candidate_course_ids=["G101", "G102"],
        candidate_section_sources_by_course={
            "G101": [_source("general", "G101-001")],
            "G102": [_source("general", "G102-001")],
        },
        target_additional_course_count=1,
        max_results=10,
        max_search_nodes=1,
    )

    result = _service(_repo()).generate(request)

    assert result.search_nodes_visited <= request.max_search_nodes
    assert result.termination_reason == SearchTerminationReason.MAX_SEARCH_NODES_REACHED
    assert any(
        reason.code == GenerationFailureCode.SEARCH_LIMIT_REACHED
        for reason in result.failure_reasons
    )


def test_target_credit_unreachable_uses_credit_failure_code() -> None:
    result = _service(_credit_repo()).generate(
        TimetableGenerationRequest(
            candidate_course_ids=["C101", "C102"],
            candidate_section_sources_by_course={
                "C101": [_source("credits", "C101-001")],
                "C102": [_source("credits", "C102-001")],
            },
            target_additional_course_count=None,
            target_additional_credits=3,
        )
    )

    assert any(
        reason.code == GenerationFailureCode.TARGET_CREDITS_UNREACHABLE
        for reason in result.failure_reasons
    )
    assert not all(
        reason.code == GenerationFailureCode.TARGET_COURSE_COUNT_UNREACHABLE
        for reason in result.failure_reasons
    )


def test_target_course_count_unreachable_uses_course_count_failure_code() -> None:
    result = _service(_credit_repo()).generate(
        TimetableGenerationRequest(
            candidate_course_ids=["C103"],
            candidate_section_sources_by_course={
                "C103": [_source("credits", "C103-001")],
            },
            target_additional_course_count=2,
        )
    )

    assert any(
        reason.code == GenerationFailureCode.TARGET_COURSE_COUNT_UNREACHABLE
        for reason in result.failure_reasons
    )


def test_course_count_and_credit_targets_are_both_hard_constraints() -> None:
    credit_short = _service(_credit_repo()).generate(
        TimetableGenerationRequest(
            candidate_course_ids=["C101", "C102"],
            candidate_section_sources_by_course={
                "C101": [_source("credits", "C101-001")],
                "C102": [_source("credits", "C102-001")],
            },
            target_additional_course_count=2,
            target_additional_credits=5,
        )
    )
    count_short = _service(_credit_repo()).generate(
        TimetableGenerationRequest(
            candidate_course_ids=["C103"],
            candidate_section_sources_by_course={
                "C103": [_source("credits", "C103-001")],
            },
            target_additional_course_count=2,
            target_additional_credits=3,
        )
    )
    success = _service(_credit_repo()).generate(
        TimetableGenerationRequest(
            candidate_course_ids=["C103", "C104"],
            candidate_section_sources_by_course={
                "C103": [_source("credits", "C103-001")],
                "C104": [_source("credits", "C104-001")],
            },
            target_additional_course_count=2,
            target_additional_credits=6,
        )
    )

    assert any(
        reason.code == GenerationFailureCode.TARGET_CREDITS_UNREACHABLE
        for reason in credit_short.failure_reasons
    )
    assert any(
        reason.code == GenerationFailureCode.TARGET_COURSE_COUNT_UNREACHABLE
        for reason in count_short.failure_reasons
    )
    assert success.success is True
    assert success.candidates[0].added_section_ids == ["C103-001", "C104-001"]


def test_validation_service_and_tools_do_not_change_state_or_score() -> None:
    repo = _repo()
    tools = TimetableGenerationTools(
        generation_service=_service(repo),
        validation_service=TimetableCandidateValidationService(catalog_repository=repo),
    )

    validation = tools.validate_timetable_candidate(
        TimetableValidationRequest(
            section_sources=[_source("major", "M001-001"), _source("general", "G101-002")],
            required_course_ids=["G102"],
            excluded_course_ids=["G101"],
        )
    )
    generated = tools.generate_timetable_candidates(
        {
            "candidate_course_ids": ["G102"],
            "candidate_section_sources_by_course": {
                "G102": [{"catalog_id": "general", "section_id": "G102-001"}],
            },
            "target_additional_course_count": 1,
        }
    )

    assert validation.valid is False
    assert {item.code for item in validation.violations} >= {
        TimetableViolationCode.TIME_CONFLICT,
        TimetableViolationCode.MISSING_REQUIRED_COURSE,
        TimetableViolationCode.EXCLUDED_COURSE_INCLUDED,
    }
    assert generated.success is True
    assert not hasattr(generated.candidates[0], "score")


def test_invalid_validation_request_is_not_reported_as_missing_course() -> None:
    repo = _repo()
    tools = TimetableGenerationTools(
        generation_service=_service(repo),
        validation_service=TimetableCandidateValidationService(catalog_repository=repo),
    )

    validation = tools.validate_timetable_candidate(
        {
            "section_sources": [],
            "earliest_start_time": "bad-time",
        }
    )

    assert validation.valid is False
    assert validation.violations[0].code == TimetableViolationCode.INVALID_VALIDATION_REQUEST
    assert all(
        violation.code != TimetableViolationCode.MISSING_REQUIRED_COURSE
        for violation in validation.violations
    )
