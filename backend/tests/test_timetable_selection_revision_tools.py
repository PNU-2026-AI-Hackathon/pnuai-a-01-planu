"""Tests for selected timetable and revision tool registration."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backend.app.agent_tools import TimetableSelectionTools
from backend.app.agents import SessionStateToolset
from backend.app.models import Category, CatalogKind, ClassTime, Course, Day
from backend.app.models.timetable_generation import (
    GeneratedTimetableCandidate,
    SectionSource,
    TimetableValidationResult,
)
from backend.app.models.timetable_selection import SelectedTimetableStatus
from backend.app.models.timetable_revision import TimetableRevisionRequest
from backend.app.repositories import InMemoryCatalogRepository, InMemorySessionRepository
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
    fixed = SectionSource(catalog_id="catalog-1", section_id="MAJ101-001")
    added = SectionSource(catalog_id="catalog-1", section_id="GEN101-001")
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


def _selection_tools(
    service: SessionService,
    catalog_repository: InMemoryCatalogRepository,
) -> TimetableSelectionTools:
    return TimetableSelectionTools(
        session_service=service,
        revision_preparation_service=TimetableRevisionPreparationService(
            session_service=service,
            catalog_repository=catalog_repository,
        ),
    )


def test_selection_tools_store_get_and_clear_selected_timetable() -> None:
    service = _service()
    state = service.create_session()
    catalog = InMemoryCatalogRepository()
    tools = _selection_tools(service, catalog)

    selected = tools.select_timetable_candidate(
        {"session_id": state.session_id, "candidate": _candidate().model_dump(mode="json")}
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
    candidate = _candidate().model_copy(
        update={"candidate_id": "tt-not-the-real-section-combination"}
    )

    result = tools.select_timetable_candidate(
        {"session_id": state.session_id, "candidate": candidate.model_dump(mode="json")}
    )

    assert result.success is False
    assert result.error is not None
    assert result.error.field == "candidate_id"


def test_hard_change_marks_selected_timetable_stale_but_soft_change_does_not() -> None:
    service = _service()
    state = service.create_session()
    service.select_timetable_candidate(state.session_id, _candidate())

    after_soft = service.add_preferred_course(state.session_id, "GEN202")
    after_hard = service.add_required_free_day(state.session_id, Day.FRI)

    assert after_soft.selected_timetable_status == SelectedTimetableStatus.CURRENT
    assert after_hard.selected_timetable_status == SelectedTimetableStatus.STALE


def test_prepare_timetable_revision_locks_untargeted_fixed_sections() -> None:
    service = _service()
    state = service.create_session()
    catalog = InMemoryCatalogRepository()
    catalog.register(
        "catalog-1",
        kind=CatalogKind.MAJOR,
        courses=[
            _course("MAJ101-001", category=Category.MAJOR_REQUIRED),
            _course("GEN101-001", category=Category.GENERAL_ELECTIVE),
        ],
    )
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
    assert result.generation_request.fixed_section_sources == [
        SectionSource(catalog_id="catalog-1", section_id="MAJ101-001")
    ]


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
