"""Tests for structured course catalog discovery."""

from __future__ import annotations

import inspect

import pytest
from pydantic import ValidationError

from backend.app.agent_tools import CourseDiscoveryTools
from backend.app.models import (
    CatalogKind,
    Category,
    ClassTime,
    Course,
    CourseDiscoveryRequest,
    CourseMatchType,
    Day,
    DiscoveryResolution,
    DiscoveryToolErrorCode,
)
from backend.app.repositories import (
    CatalogAlreadyExistsError,
    CatalogNotFoundError,
    CourseNotFoundError,
    InMemoryCatalogRepository,
    SectionNotFoundError,
)
from backend.app.services.course_discovery_service import CourseDiscoveryService


def _time(day: Day, start: str, end: str) -> ClassTime:
    return ClassTime(
        day=day,
        start=start,
        end=end,
        classroom="609-313",
        building_code="609",
    )


def _course(
    code: str,
    division: str,
    name: str,
    *,
    category: Category = Category.GENERAL_ELECTIVE,
    area: int | None = 3,
    professor: str = "김교수",
    class_times: list[ClassTime] | None = None,
) -> Course:
    return Course(
        course_id=f"{code}-{division}",
        course_name=name,
        category=category,
        area=area,
        credit=3,
        division=division,
        professor=professor,
        class_times=class_times or [_time(Day.MON, "10:00", "11:15")],
    )


def _catalog() -> list[Course]:
    return [
        _course("C001", "001", "컴퓨터프로그래밍", class_times=[_time(Day.MON, "10:00", "11:15")]),
        _course("C001", "002", "컴퓨터프로그래밍", class_times=[_time(Day.FRI, "10:00", "11:15")]),
        _course("C001", "003", "컴퓨터프로그래밍", class_times=[_time(Day.TUE, "13:00", "14:15")]),
        _course("C002", "001", "컴퓨터와사회", area=3, class_times=[_time(Day.WED, "11:00", "12:15")]),
        _course("C003", "001", "대학수학", area=2, class_times=[_time(Day.THU, "09:00", "10:15")]),
        _course("C004", "001", "프로그래밍입문", area=3, class_times=[_time(Day.MON, "08:30", "09:45")]),
        _course("C005", "001", "컴퓨터프로그래밍", area=4, class_times=[_time(Day.WED, "15:00", "16:15")]),
        _course(
            "M001",
            "001",
            "자료구조",
            category=Category.MAJOR_REQUIRED,
            area=None,
            class_times=[_time(Day.TUE, "10:00", "11:15")],
        ),
        _course("C006", "001", "금요일세미나", area=3, class_times=[_time(Day.FRI, "14:00", "15:15")]),
    ]


@pytest.fixture
def repository() -> InMemoryCatalogRepository:
    repo = InMemoryCatalogRepository()
    repo.register("catalog-1", kind=CatalogKind.ELECTIVE, courses=_catalog(), department="컴퓨터공학부")
    return repo


@pytest.fixture
def service(repository: InMemoryCatalogRepository) -> CourseDiscoveryService:
    return CourseDiscoveryService(repository)


def test_repository_register_get_delete_and_exists() -> None:
    repo = InMemoryCatalogRepository()
    record = repo.register("catalog-1", kind=CatalogKind.ELECTIVE, courses=_catalog())

    assert record.catalog_id == "catalog-1"
    assert repo.exists("catalog-1") is True
    assert len(repo.list_sections("catalog-1")) == len(_catalog())

    repo.delete("catalog-1")
    repo.delete("catalog-1")
    assert repo.exists("catalog-1") is False


def test_repository_duplicate_and_missing_catalog_errors(repository: InMemoryCatalogRepository) -> None:
    with pytest.raises(CatalogAlreadyExistsError):
        repository.register("catalog-1", kind=CatalogKind.ELECTIVE, courses=_catalog())

    with pytest.raises(CatalogNotFoundError):
        repository.list_sections("missing")


def test_repository_deep_copy_and_instance_isolation(repository: InMemoryCatalogRepository) -> None:
    sections = repository.list_sections("catalog-1")
    sections[0].course_name = "변경"

    assert repository.list_sections("catalog-1")[0].course_name == "컴퓨터프로그래밍"

    other = InMemoryCatalogRepository()
    assert other.exists("catalog-1") is False


def test_name_search_exact_course_id_and_code(service: CourseDiscoveryService) -> None:
    by_course_id = service.search_by_name(catalog_id="catalog-1", query="C001")
    by_section_id = service.search_by_name(catalog_id="catalog-1", query="C001-001")

    assert by_course_id.resolution is DiscoveryResolution.EXACT
    assert by_course_id.candidates[0].match_type is CourseMatchType.COURSE_ID_EXACT
    assert by_course_id.candidates[0].matching_section_ids == ["C001-001", "C001-002", "C001-003"]
    assert by_section_id.candidates[0].course_id == "C001"


def test_name_search_exact_partial_ambiguous_and_not_found(service: CourseDiscoveryService) -> None:
    exact = service.search_by_name(catalog_id="catalog-1", query="대학수학")
    partial = service.search_by_name(catalog_id="catalog-1", query="사회")
    ambiguous = service.search_by_name(catalog_id="catalog-1", query="컴퓨터")
    missing = service.search_by_name(catalog_id="catalog-1", query="없는과목")

    assert exact.resolution is DiscoveryResolution.EXACT
    assert exact.candidates[0].match_reasons[0] == "과목명 정확 일치"
    assert partial.candidates[0].course_name == "컴퓨터와사회"
    assert ambiguous.resolution is DiscoveryResolution.AMBIGUOUS
    assert {item.course_id for item in ambiguous.candidates} >= {"C001", "C002", "C005"}
    assert missing.success is False
    assert missing.resolution is DiscoveryResolution.NOT_FOUND


def test_name_search_groups_multiple_sections_as_one_candidate(service: CourseDiscoveryService) -> None:
    result = service.search_by_name(catalog_id="catalog-1", query="컴퓨터프로그래밍")

    assert result.resolution is DiscoveryResolution.AMBIGUOUS
    c001 = next(candidate for candidate in result.candidates if candidate.course_id == "C001")
    assert c001.total_section_count == 3
    assert c001.matching_section_count == 3


def test_condition_discovery_without_query_and_core_filters(service: CourseDiscoveryService) -> None:
    result = service.discover(CourseDiscoveryRequest(catalog_id="catalog-1", area=3, limit=10))

    assert result.resolution is DiscoveryResolution.CANDIDATES
    assert result.total_matched_courses >= 4
    assert all(candidate.area == 3 for candidate in result.candidates)
    assert any("교양 3영역" in reason for reason in result.candidates[0].match_reasons)


def test_condition_filters_days_and_times(service: CourseDiscoveryService) -> None:
    allowed = service.discover(CourseDiscoveryRequest(catalog_id="catalog-1", allowed_days=[Day.TUE]))
    no_friday = service.discover(CourseDiscoveryRequest(catalog_id="catalog-1", excluded_days=[Day.FRI], query="컴퓨터프로그래밍"))
    later = service.discover(CourseDiscoveryRequest(catalog_id="catalog-1", earliest_start_time="10:00", area=3))
    early_end = service.discover(CourseDiscoveryRequest(catalog_id="catalog-1", latest_end_time="10:00", area=3))

    assert [candidate.course_id for candidate in allowed.candidates] == ["C001", "M001"]
    c001 = next(candidate for candidate in no_friday.candidates if candidate.course_id == "C001")
    assert c001.matching_section_ids == ["C001-001", "C001-003"]
    assert "FRI 수업이 없는 분반 2개" in c001.match_reasons
    assert all("C004-001" not in candidate.matching_section_ids for candidate in later.candidates)
    assert [candidate.course_id for candidate in early_end.candidates] == ["C004"]


def test_condition_excluded_ids_multi_conditions_and_partial_sections(service: CourseDiscoveryService) -> None:
    result = service.discover(
        CourseDiscoveryRequest(
            catalog_id="catalog-1",
            category=Category.GENERAL_ELECTIVE,
            area=3,
            earliest_start_time="10:00",
            excluded_days=[Day.FRI],
            excluded_course_ids=["C002"],
            limit=10,
        )
    )

    assert [candidate.course_id for candidate in result.candidates] == ["C001"]
    candidate = result.candidates[0]
    assert candidate.matching_section_ids == ["C001-001", "C001-003"]
    assert "C001-002" not in candidate.matching_section_ids
    assert candidate.matching_section_count == 2


def test_condition_excludes_courses_with_no_matching_sections(service: CourseDiscoveryService) -> None:
    result = service.discover(CourseDiscoveryRequest(catalog_id="catalog-1", allowed_days=[Day.SUN]))

    assert result.success is False
    assert result.candidates == []


def test_limit_defaults_maximum_and_sorting(service: CourseDiscoveryService) -> None:
    defaulted = CourseDiscoveryRequest(catalog_id="catalog-1")
    assert defaulted.limit == 20

    with pytest.raises(ValidationError):
        CourseDiscoveryRequest(catalog_id="catalog-1", limit=51)

    result = service.discover(CourseDiscoveryRequest(catalog_id="catalog-1", area=3, limit=2))
    assert len(result.candidates) == 2
    assert result.total_matched_courses > len(result.candidates)
    assert result.candidates[0].matching_section_count >= result.candidates[1].matching_section_count


def test_section_lookup_all_matching_and_errors(service: CourseDiscoveryService) -> None:
    all_sections = service.get_course_sections(catalog_id="catalog-1", course_id="C001")
    matching = service.get_course_sections(
        catalog_id="catalog-1",
        course_id="C001",
        section_ids=["C001-003"],
    )
    detail = service.get_section_details(catalog_id="catalog-1", section_id="C001-002")

    assert [section.section_id for section in all_sections] == ["C001-001", "C001-002", "C001-003"]
    assert [section.section_id for section in matching] == ["C001-003"]
    assert detail.division == "002"

    with pytest.raises(CourseNotFoundError):
        service.get_course_sections(catalog_id="catalog-1", course_id="missing")
    with pytest.raises(SectionNotFoundError):
        service.get_section_details(catalog_id="catalog-1", section_id="missing")


def test_discovery_tools_wrap_service_and_do_not_use_session(repository: InMemoryCatalogRepository) -> None:
    tools = CourseDiscoveryTools(CourseDiscoveryService(repository))

    condition = tools.discover_courses({"catalog_id": "catalog-1", "excluded_days": ["FRI"], "category": "GENERAL_ELECTIVE"})
    search = tools.search_courses_by_name({"catalog_id": "catalog-1", "query": "대학수학"})
    sections = tools.get_course_sections({"catalog_id": "catalog-1", "course_id": "C001"})
    detail = tools.get_section_details({"catalog_id": "catalog-1", "section_id": "C001-001"})

    assert condition.success is True
    assert condition.candidates
    assert search.resolution is DiscoveryResolution.EXACT
    assert len(sections.sections) == 3
    assert detail.section is not None
    assert detail.section.section_id == "C001-001"

    source = inspect.getsource(CourseDiscoveryTools)
    assert "SessionService" not in source
    assert "get_session" not in source
    assert ".save(" not in source
    assert "conflicts_with" not in source


def test_discovery_tools_return_structured_errors(repository: InMemoryCatalogRepository) -> None:
    tools = CourseDiscoveryTools(CourseDiscoveryService(repository))

    missing_catalog = tools.discover_courses({"catalog_id": "missing", "limit": 5})
    missing_course = tools.get_course_sections({"catalog_id": "catalog-1", "course_id": "missing"})
    missing_section = tools.get_section_details({"catalog_id": "catalog-1", "section_id": "missing"})
    invalid = tools.discover_courses({"catalog_id": "catalog-1", "limit": 100})

    assert missing_catalog.error is not None
    assert missing_catalog.error.code is DiscoveryToolErrorCode.CATALOG_NOT_FOUND
    assert missing_course.error is not None
    assert missing_course.error.code is DiscoveryToolErrorCode.COURSE_NOT_FOUND
    assert missing_section.error is not None
    assert missing_section.error.code is DiscoveryToolErrorCode.SECTION_NOT_FOUND
    assert invalid.error is not None
    assert invalid.error.code is DiscoveryToolErrorCode.INVALID_DISCOVERY_REQUEST
