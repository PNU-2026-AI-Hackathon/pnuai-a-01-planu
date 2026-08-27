"""Tests for selected timetable and revision tool registration."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backend.app.agent_tools import TimetableGenerationTools, TimetableSelectionTools
from backend.app.agents import SessionStateToolset
from backend.app.models import Category, CatalogKind, ClassTime, Course, Day
from backend.app.models.timetable_generation import (
    GeneratedTimetableCandidate,
    SectionSource,
    TimetableGenerationRequest,
    TimetableGenerationResult,
    TimetableValidationResult,
)
from backend.app.models.timetable_selection import SelectedTimetableStatus
from backend.app.models.timetable_revision import TimetableRevisionRequest
from backend.app.repositories import InMemoryCatalogRepository, InMemorySessionRepository
from backend.app.repositories.recent_timetable_candidate_repository import RecentTimetableCandidateRepository
from backend.app.services.session_service import SessionService
from backend.app.services.timetable_revision_preparation_service import (
    TimetableRevisionPreparationService,
)


def _now() -> datetime:
    return datetime(2026, 8, 9, 12, 0, tzinfo=timezone.utc)


def _service() -> SessionService:
    return SessionService(
        InMemorySessionRepository(),
        session_ttl=timedelta(minutes=30),
        now_provider=_now,
        session_id_provider=lambda: "session-1",
    )


def _course(course_id: str, *, category: Category, day: Day = Day.MON) -> Course:
    return Course(
        course_id=course_id,
        course_name=course_id,
        category=category,
        area=3 if category == Category.GENERAL_ELECTIVE else None,
        credit=3,
        division=course_id.rsplit("-", 1)[-1],
        professor="Kim",
        class_times=[
            ClassTime(
                day=day,
                start="09:00",
                end="10:15",
                classroom="101",
                building_code="B1",
            )
        ],
    )


def _candidate() -> GeneratedTimetableCandidate:
    fixed = SectionSource(catalog_id="major-catalog", section_id="MAJ101-001")
    added = SectionSource(catalog_id="elective-catalog", section_id="GEN101-001")
    sources = [fixed, added]
    return GeneratedTimetableCandidate(
        candidate_id=GeneratedTimetableCandidate.build_source_id(sources),
        section_ids=["MAJ101-001", "GEN101-001"],
        section_sources=sources,
        fixed_section_ids=["MAJ101-001"],
        fixed_section_sources=[fixed],
        added_section_ids=["GEN101-001"],
        added_section_sources=[added],
        course_ids=["MAJ101", "GEN101"],
        total_credits=6,
        validation=TimetableValidationResult(valid=True, checked_section_ids=[]),
        generation_order=1,
    )



def _revised_candidate() -> GeneratedTimetableCandidate:
    fixed = SectionSource(catalog_id="major-catalog", section_id="MAJ101-001")
    added = SectionSource(catalog_id="elective-catalog", section_id="GEN102-001")
    sources = [fixed, added]
    return GeneratedTimetableCandidate(
        candidate_id=GeneratedTimetableCandidate.build_source_id(sources),
        section_ids=["MAJ101-001", "GEN102-001"],
        section_sources=sources,
        fixed_section_ids=["MAJ101-001"],
        fixed_section_sources=[fixed],
        added_section_ids=["GEN102-001"],
        added_section_sources=[added],
        course_ids=["MAJ101", "GEN102"],
        total_credits=6,
        validation=TimetableValidationResult(valid=True, checked_section_ids=[]),
        generation_order=1,
    )


def _selection_tools(
    service: SessionService,
    catalog_repository: InMemoryCatalogRepository,
    candidate: GeneratedTimetableCandidate | None = None,
) -> TimetableSelectionTools:
    recent = RecentTimetableCandidateRepository()
    recent.save_candidates("session-1", [candidate or _candidate()])
    return TimetableSelectionTools(
        session_service=service,
        revision_preparation_service=TimetableRevisionPreparationService(
            session_service=service,
            catalog_repository=catalog_repository,
        ),
        recent_candidate_repository=recent,
    )


def test_generation_tool_stores_recent_candidates_for_candidate_id_selection() -> None:
    class GenerationService:
        def generate(self, request: TimetableGenerationRequest) -> TimetableGenerationResult:
            return TimetableGenerationResult(
                success=True,
                candidates=[_candidate()],
                total_candidates_found=1,
                search_nodes_visited=1,
                message="generated",
            )

    recent = RecentTimetableCandidateRepository()
    tools = TimetableGenerationTools(
        generation_service=GenerationService(),
        validation_service=object(),
        recent_candidate_repository=recent,
    )

    result = tools.generate_timetable_candidates({"session_id": "session-1"})
    cached = recent.get_candidate("session-1", _candidate().candidate_id)

    assert result.success is True
    assert cached.candidate_id == _candidate().candidate_id


def test_selection_tools_store_get_and_clear_selected_timetable() -> None:
    service = _service()
    state = service.create_session()
    catalog = InMemoryCatalogRepository()
    tools = _selection_tools(service, catalog)

    selected = tools.select_timetable_candidate(
        {"session_id": state.session_id, "candidate_id": _candidate().candidate_id}
    )
    fetched = tools.get_selected_timetable({"session_id": state.session_id})
    cleared = tools.clear_selected_timetable({"session_id": state.session_id})
    cleared_again = tools.clear_selected_timetable({"session_id": state.session_id})

    assert selected.success is True
    assert selected.changed is True
    assert selected.selected_timetable is not None
    assert selected.selected_timetable_status == SelectedTimetableStatus.CURRENT.value
    assert fetched.selected_timetable is not None
    assert cleared.changed is True
    assert cleared_again.changed is False


def test_select_timetable_candidate_rejects_invalid_candidate() -> None:
    service = _service()
    state = service.create_session()
    catalog = InMemoryCatalogRepository()
    tools = _selection_tools(service, catalog)
    result = tools.select_timetable_candidate(
        {"session_id": state.session_id, "candidate_id": "tt-not-generated"}
    )

    assert result.success is False
    assert result.error is not None
    assert result.error.field == "candidate_id"


def test_hard_and_soft_changes_mark_selected_timetable_stale() -> None:
    service = _service()
    state = service.create_session()
    service.select_timetable_candidate(state.session_id, _candidate())

    after_soft = service.add_preferred_course(state.session_id, "GEN202")
    after_hard = service.add_required_free_day(state.session_id, Day.FRI)

    assert after_soft.selected_timetable_status == SelectedTimetableStatus.STALE
    assert after_hard.selected_timetable_status == SelectedTimetableStatus.STALE


def test_prepare_timetable_revision_locks_untargeted_fixed_sections() -> None:
    service = _service()
    state = service.create_session()
    catalog = InMemoryCatalogRepository()
    catalog.register(
        "major-catalog",
        kind=CatalogKind.MAJOR,
        courses=[_course("MAJ101-001", category=Category.MAJOR_REQUIRED)],
    )
    catalog.register(
        "elective-catalog",
        kind=CatalogKind.ELECTIVE,
        courses=[_course("GEN101-001", category=Category.GENERAL_ELECTIVE)],
    )
    service.register_major_catalog(state.session_id, "major-catalog")
    service.register_elective_catalog(state.session_id, "elective-catalog")
    service.select_timetable_candidate(state.session_id, _candidate())
    tools = _selection_tools(service, catalog)

    result = tools.prepare_timetable_revision(
        TimetableRevisionRequest(
            session_id=state.session_id,
            replace_course_ids=["GEN101"],
        )
    )

    assert result.success is True
    assert result.locked_section_ids == ["MAJ101-001"]
    assert result.replaceable_section_ids == ["GEN101-001"]
    assert result.generation_request is not None
    assert result.generation_request.session_id == state.session_id
    assert result.generation_request.fixed_section_sources == [
        SectionSource(catalog_id="major-catalog", section_id="MAJ101-001")
    ]


def test_revision_generation_candidate_is_cached_and_selectable() -> None:
    class GenerationService:
        def generate(self, request: TimetableGenerationRequest) -> TimetableGenerationResult:
            assert request.session_id == "session-1"
            return TimetableGenerationResult(
                success=True,
                candidates=[_revised_candidate()],
                total_candidates_found=1,
                search_nodes_visited=1,
                message="generated revision",
            )

    service = _service()
    state = service.create_session()
    catalog = InMemoryCatalogRepository()
    catalog.register(
        "major-catalog",
        kind=CatalogKind.MAJOR,
        courses=[_course("MAJ101-001", category=Category.MAJOR_REQUIRED)],
    )
    catalog.register(
        "elective-catalog",
        kind=CatalogKind.ELECTIVE,
        courses=[
            _course("GEN101-001", category=Category.GENERAL_ELECTIVE),
            _course("GEN102-001", category=Category.GENERAL_ELECTIVE),
        ],
    )
    service.register_major_catalog(state.session_id, "major-catalog")
    service.register_elective_catalog(state.session_id, "elective-catalog")
    service.select_timetable_candidate(state.session_id, _candidate())
    recent = RecentTimetableCandidateRepository()
    selection_tools = TimetableSelectionTools(
        session_service=service,
        revision_preparation_service=TimetableRevisionPreparationService(
            session_service=service,
            catalog_repository=catalog,
        ),
        recent_candidate_repository=recent,
    )
    generation_tools = TimetableGenerationTools(
        generation_service=GenerationService(),
        validation_service=object(),
        recent_candidate_repository=recent,
    )

    prepared = selection_tools.prepare_timetable_revision(
        TimetableRevisionRequest(
            session_id=state.session_id,
            replace_section_ids=["GEN101-001"],
        )
    )
    assert prepared.generation_request is not None
    generated = generation_tools.generate_timetable_candidates(
        prepared.generation_request.model_dump(mode="json")
    )
    selected = selection_tools.select_timetable_candidate(
        {"session_id": state.session_id, "candidate_id": _revised_candidate().candidate_id}
    )

    assert generated.success is True
    assert selected.success is True
    assert selected.selected_timetable is not None
    assert selected.selected_timetable.candidate_id == _revised_candidate().candidate_id


def test_failed_generation_clears_previous_recent_candidates() -> None:
    class SuccessGenerationService:
        def generate(self, request: TimetableGenerationRequest) -> TimetableGenerationResult:
            return TimetableGenerationResult(
                success=True,
                candidates=[_candidate()],
                total_candidates_found=1,
                search_nodes_visited=1,
                message="generated",
            )

    class FailedGenerationService:
        def generate(self, request: TimetableGenerationRequest) -> TimetableGenerationResult:
            return TimetableGenerationResult(
                success=False,
                candidates=[],
                total_candidates_found=0,
                search_nodes_visited=1,
                message="no candidates",
            )

    service = _service()
    state = service.create_session()
    catalog = InMemoryCatalogRepository()
    recent = RecentTimetableCandidateRepository()
    selection_tools = TimetableSelectionTools(
        session_service=service,
        revision_preparation_service=TimetableRevisionPreparationService(
            session_service=service,
            catalog_repository=catalog,
        ),
        recent_candidate_repository=recent,
    )
    success_tools = TimetableGenerationTools(
        generation_service=SuccessGenerationService(),
        validation_service=object(),
        recent_candidate_repository=recent,
    )
    failed_tools = TimetableGenerationTools(
        generation_service=FailedGenerationService(),
        validation_service=object(),
        recent_candidate_repository=recent,
    )

    success_tools.generate_timetable_candidates({"session_id": state.session_id})
    first_selection = selection_tools.select_timetable_candidate(
        {"session_id": state.session_id, "candidate_id": _candidate().candidate_id}
    )
    failed_tools.generate_timetable_candidates({"session_id": state.session_id})
    stale_selection = selection_tools.select_timetable_candidate(
        {"session_id": state.session_id, "candidate_id": _candidate().candidate_id}
    )

    assert first_selection.success is True
    assert stale_selection.success is False
    assert stale_selection.error is not None
    assert stale_selection.error.field == "candidate_id"


def test_revision_rejects_fixed_major_section_replacement() -> None:
    service = _service()
    state = service.create_session()
    catalog = InMemoryCatalogRepository()
    catalog.register(
        "major-catalog",
        kind=CatalogKind.MAJOR,
        courses=[_course("MAJ101-001", category=Category.MAJOR_REQUIRED)],
    )
    catalog.register(
        "elective-catalog",
        kind=CatalogKind.ELECTIVE,
        courses=[_course("GEN101-001", category=Category.GENERAL_ELECTIVE)],
    )
    service.select_timetable_candidate(state.session_id, _candidate())
    tools = _selection_tools(service, catalog)

    result = tools.prepare_timetable_revision(
        TimetableRevisionRequest(
            session_id=state.session_id,
            replace_section_ids=["MAJ101-001"],
        )
    )

    assert result.success is False
    assert result.needs_confirmation is True
    assert result.replaceable_section_ids == []
    assert result.generation_request is None
    assert any("확정 전공" in reason for reason in result.confirmation_reasons)


def test_elective_revision_uses_elective_catalog_without_major_fallback() -> None:
    service = _service()
    state = service.create_session()
    catalog = InMemoryCatalogRepository()
    catalog.register(
        "major-catalog",
        kind=CatalogKind.MAJOR,
        courses=[_course("MAJ101-001", category=Category.MAJOR_REQUIRED)],
    )
    catalog.register(
        "elective-catalog",
        kind=CatalogKind.ELECTIVE,
        courses=[_course("GEN101-001", category=Category.GENERAL_ELECTIVE)],
    )
    service.register_major_catalog(state.session_id, "major-catalog")
    service.register_elective_catalog(state.session_id, "elective-catalog")
    service.select_timetable_candidate(state.session_id, _candidate())
    tools = _selection_tools(service, catalog)

    result = tools.prepare_timetable_revision(
        TimetableRevisionRequest(
            session_id=state.session_id,
            replace_section_ids=["GEN101-001"],
        )
    )

    assert result.success is True
    assert result.additional_discovery == [
        {
            "catalog_id": "elective-catalog",
            "replace_course_ids": ["GEN101"],
            "excluded_course_ids": [],
            "excluded_section_ids": ["GEN101-001"],
        }
    ]


def test_revision_does_not_fallback_to_major_catalog_for_elective_replacement() -> None:
    service = _service()
    state = service.create_session()
    catalog = InMemoryCatalogRepository()
    catalog.register(
        "major-catalog",
        kind=CatalogKind.MAJOR,
        courses=[_course("MAJ101-001", category=Category.MAJOR_REQUIRED)],
    )
    catalog.register(
        "elective-catalog",
        kind=CatalogKind.ELECTIVE,
        courses=[_course("GEN101-001", category=Category.GENERAL_ELECTIVE)],
    )
    service.register_major_catalog(state.session_id, "major-catalog")
    service.select_timetable_candidate(state.session_id, _candidate())
    tools = _selection_tools(service, catalog)

    result = tools.prepare_timetable_revision(
        TimetableRevisionRequest(
            session_id=state.session_id,
            replace_section_ids=["GEN101-001"],
        )
    )

    assert result.success is True
    assert result.additional_discovery == [{"reason": "elective_catalog_id_required"}]


def test_new_tools_are_registered_with_input_schemas() -> None:
    class Dummy:
        def __getattr__(self, name):
            def _tool(data):
                return data

            return _tool

    toolset = SessionStateToolset.from_agent_and_discovery_tools(
        Dummy(),
        Dummy(),
        Dummy(),
        scoring_tools=Dummy(),
        selection_tools=Dummy(),
    )
    specs = {spec.name: spec for spec in toolset.specs()}

    for name in {
        "select_timetable_candidate",
        "get_selected_timetable",
        "clear_selected_timetable",
        "prepare_timetable_revision",
    }:
        assert toolset.has_tool(name)
        assert specs[name].parameters["type"] == "object"

    selection_properties = specs["select_timetable_candidate"].parameters["properties"]
    revision_properties = specs["prepare_timetable_revision"].parameters["properties"]
    assert "candidate_id" in selection_properties
    assert "candidate" not in selection_properties
    assert "temporary_hard_constraints" not in revision_properties
    assert "temporary_soft_preferences" not in revision_properties
