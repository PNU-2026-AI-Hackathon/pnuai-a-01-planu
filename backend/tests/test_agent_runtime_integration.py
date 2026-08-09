"""Integration tests for the PlaNU composition root and agent runtime API."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from backend.app.container import build_container
from backend.app.deps import get_agent_runtime
from backend.app.main import app
from backend.app.runtime import AgentRuntime
from backend.app.models import Category, ClassTime, Course, Day
from backend.app.models.course_discovery import CatalogKind
from backend.app.services.session_store import SessionStore


class FakeModel:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, payload):
        self.calls.append(payload)
        if self.responses:
            return self.responses.pop(0)
        return {"message": "완료했습니다.", "tool_calls": []}


def _course(course_id: str, name: str, *, day: Day = Day.MON) -> Course:
    return Course(
        course_id=course_id,
        course_name=name,
        category=Category.GENERAL_ELECTIVE,
        area=3,
        credit=3,
        division=course_id.rsplit("-", 1)[-1],
        professor="김교수",
        class_times=[
            ClassTime(
                day=day,
                start="11:00",
                end="12:15",
                classroom="501-101",
                building_code="501",
            )
        ],
    )


def test_composition_root_shares_repositories_and_registers_all_agent_tools() -> None:
    model = FakeModel()
    container = build_container(model=model)

    assert container.session_service._repository is container.session_repository
    assert container.session_agent_tools._session_service is container.session_service
    assert container.course_discovery_service._repository is container.catalog_repository
    assert container.timetable_candidate_generation_service.catalog_repository is container.catalog_repository

    tool_names = [spec.name for spec in container.session_state_toolset.specs()]
    assert len(tool_names) == len(set(tool_names))
    assert {
        "get_session_summary",
        "update_session_profile",
        "update_selected_major_courses",
        "update_timetable_preferences",
        "reset_session_preferences",
        "discover_courses",
        "search_courses_by_name",
        "get_course_sections",
        "get_section_details",
        "generate_timetable_candidates",
        "validate_timetable_candidate",
        "score_timetable_candidate",
        "rank_timetable_candidates",
        "select_timetable_candidate",
        "get_selected_timetable",
        "clear_selected_timetable",
        "prepare_timetable_revision",
    }.issubset(set(tool_names))
    assert container.session_state_agent.model is model


def test_chat_api_uses_agent_tools_and_returns_public_dto() -> None:
    with TestClient(app) as client:
        created = client.post("/sessions", json={"department": "컴퓨터공학과"})
        assert created.status_code == 200, created.text
        session_id = created.json()["session_id"]

        response = client.post(
            f"/sessions/{session_id}/chat",
            json={"message": "금요일은 반드시 비워줘.", "request_id": "req-chat"},
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["session_id"] == session_id
        assert body["changed"] is True
        assert body["session_summary"]["hard_constraints"]["required_free_days"] == ["FRI"]
        assert "executed_tools" not in body

        saved = app.state.container.session_service.get_session(session_id)
        assert saved.hard_constraints.required_free_days == [Day.FRI]


def test_chat_api_returns_stable_session_unavailable_error_after_ttl() -> None:
    current = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def clock() -> datetime:
        return current

    store = SessionStore(ttl=timedelta(minutes=1), clock=clock)
    container = build_container(session_store=store, model=FakeModel())
    session = container.session_service.create_session()
    runtime = AgentRuntime(
        session_service=container.session_service,
        agent=container.session_state_agent,
        selection_tools=container.timetable_selection_tools,
    )
    app.dependency_overrides[get_agent_runtime] = lambda: runtime
    current = current + timedelta(minutes=2)

    client = TestClient(app)
    try:
        response = client.post(
            f"/sessions/{session.session_id}/chat",
            json={"message": "금요일은 반드시 비워줘."},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "SESSION_NOT_AVAILABLE"


def test_catalog_isolation_between_sessions_through_shared_discovery_tool() -> None:
    container = build_container(model=FakeModel())
    first = container.session_service.create_session()
    second = container.session_service.create_session()
    first_catalog = f"{first.session_id}:major"
    second_catalog = f"{second.session_id}:major"

    container.catalog_repository.register(
        first_catalog,
        kind=CatalogKind.MAJOR,
        courses=[_course("A100-001", "자료구조")],
        department="컴퓨터공학과",
    )
    container.session_service.register_major_catalog(first.session_id, first_catalog)
    container.catalog_repository.register(
        second_catalog,
        kind=CatalogKind.MAJOR,
        courses=[_course("B100-001", "자료구조")],
        department="컴퓨터공학과",
    )
    container.session_service.register_major_catalog(second.session_id, second_catalog)

    first_result = container.course_discovery_tools.search_courses_by_name(
        {"catalog_id": first_catalog, "query": "자료구조"}
    )
    second_result = container.course_discovery_tools.search_courses_by_name(
        {"catalog_id": second_catalog, "query": "자료구조"}
    )

    assert [candidate.course_id for candidate in first_result.candidates] == ["A100"]
    assert [candidate.course_id for candidate in second_result.candidates] == ["B100"]


