from __future__ import annotations

from backend.app.agent_tools.timetable_generation_tools import TimetableGenerationTools
from backend.app.models.course import Category, ClassTime, Course, Day
from backend.app.models.course_discovery import CatalogKind
from backend.app.models.timetable_generation import (
    GenerationFailureCode,
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


def _source(catalog_id: str, section_id: str) -> SectionSource:
    return SectionSource(catalog_id=catalog_id, section_id=section_id)


def _service(repo: InMemoryCatalogRepository) -> TimetableCandidateGenerationService:
    return TimetableCandidateGenerationService(catalog_repository=repo)


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
    assert any(reason.code == GenerationFailureCode.TIME_CONFLICT for reason in result.failure_reasons)


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
    assert [candidate.candidate_id for candidate in first.candidates] == [
        candidate.candidate_id for candidate in second.candidates
    ]
    assert first.candidates[0].added_section_ids == second.candidates[0].added_section_ids


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
