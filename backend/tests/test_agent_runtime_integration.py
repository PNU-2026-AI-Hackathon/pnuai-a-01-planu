"""Integration tests for the PlaNU composition root and agent runtime API."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from typing import get_type_hints

from backend.app.agents import AgentDomain, RunnableAgent
from backend.app.agents.simple_session_model import SimpleSessionStateModel
from backend.app.container import build_container
from backend.app.deps import get_agent_runtime
from backend.app.main import app
from backend.app.runtime import AgentRuntime
from backend.app.models import Category, ClassTime, Course, Day
from backend.app.models.course_discovery import CatalogKind
from backend.app.services.general_preference_parser import GeneralPreferenceParser
from backend.app.services.session_store import SessionStore
from backend.app.core.errors import AppError


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
    assert container.legacy_session_state_agent.model is model
    assert container.major_agent.agent.system_prompt != container.preference_agent.agent.system_prompt
    assert container.preference_agent.agent.system_prompt != container.timetable_agent.agent.system_prompt


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
        agent=container.supervisor_agent,
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





def test_public_chat_uses_supervisor_agent_and_not_legacy_full_agent() -> None:
    with TestClient(app) as client:
        created = client.post("/sessions", json={"department": "컴퓨터공학과"})
        session_id = created.json()["session_id"]

        class ExplodingLegacyAgent:
            def run(self, _data):
                raise AssertionError("legacy full toolset agent must not handle public chat")

        app.state.container.legacy_session_state_agent = ExplodingLegacyAgent()
        response = client.post(
            f"/sessions/{session_id}/chat",
            json={"message": "전공 분반을 확인해줘"},
        )

        assert response.status_code == 200, response.text
        assert app.state.container.supervisor_agent.last_route is not None


def test_public_chat_accumulates_real_korean_timetable_conditions() -> None:
    container = build_container()
    runtime = AgentRuntime(
        session_service=container.session_service,
        agent=container.supervisor_agent,
        selection_tools=container.timetable_selection_tools,
        condition_summary_service=container.condition_summary_service,
    )
    app.dependency_overrides[get_agent_runtime] = lambda: runtime
    client = TestClient(app)

    try:
        state = container.session_service.create_session()
        state = container.session_service.set_department(state.session_id, "컴퓨터공학과")
        session_id = state.session_id
        messages = [
            "수요일은 공강으로 해줘",
            "10시 이전 수업은 피하고 싶어",
            "오후 5시 30분 전에는 끝내줘",
            "18학점 이상 듣고 싶어",
            "연강은 피하고 싶어",
        ]
        responses = [
            client.post(f"/sessions/{session_id}/chat", json={"message": message})
            for message in messages
        ]
    finally:
        app.dependency_overrides.clear()

    for response in responses:
        assert response.status_code == 200, response.text
        assert response.json()["changed"] is True
        assert "변경할 조건을 찾지 못했습니다" not in response.json()["message"]

    saved = container.session_service.get_session(session_id)
    assert saved.hard_constraints.required_free_days == [Day.WED]
    assert saved.soft_preferences.preferred_earliest_start_time == "10:00"
    assert saved.hard_constraints.latest_end_time == "17:30"
    assert saved.hard_constraints.min_credit == 18
    assert saved.soft_preferences.compact_schedule is False

    latest_summary = responses[-1].json()["condition_summary"]
    hard_items = {item["key"]: item for item in latest_summary["hard_constraints"]}
    soft_items = {item["key"]: item for item in latest_summary["soft_preferences"]}
    assert hard_items["required_free_days"]["status"] == "SET"
    assert hard_items["latest_end_time"]["raw_value"] == "17:30"
    assert hard_items["min_credit"]["raw_value"] == 18
    assert soft_items["preferred_earliest_start_time"]["raw_value"] == "10:00"
    assert soft_items["compact_schedule"]["raw_value"] is False


def test_public_chat_credit_conditions_are_saved_only_by_agent_tool() -> None:
    container = build_container()
    runtime = AgentRuntime(
        session_service=container.session_service,
        agent=container.supervisor_agent,
        selection_tools=container.timetable_selection_tools,
        condition_summary_service=container.condition_summary_service,
    )
    app.dependency_overrides[get_agent_runtime] = lambda: runtime
    client = TestClient(app)

    try:
        state = container.session_service.create_session()
        session_id = state.session_id
        combined = client.post(
            f"/sessions/{session_id}/chat",
            json={"message": "금요일은 꼭 공강이고 최소 12학점, 최대 15학점으로 만들어줘"},
        )
        assert combined.status_code == 200, combined.text
        saved = container.session_service.get_session(session_id)
        assert saved.hard_constraints.required_free_days == [Day.FRI]
        assert saved.hard_constraints.min_credit == 12
        assert saved.hard_constraints.max_credit == 15

        negative = client.post(
            f"/sessions/{session_id}/chat",
            json={"message": "최소 18학점은 너무 많아서 싫어"},
        )
        assert negative.status_code == 200, negative.text
        saved = container.session_service.get_session(session_id)
        assert saved.hard_constraints.min_credit == 12

        over_limit = client.post(
            f"/sessions/{session_id}/chat",
            json={"message": "22학점 초과는 못들어요"},
        )
        assert over_limit.status_code == 200, over_limit.text
        saved = container.session_service.get_session(session_id)
        assert saved.hard_constraints.max_credit == 22

        over_or_equal_limit = client.post(
            f"/sessions/{session_id}/chat",
            json={"message": "22학점 이상은 못들어요"},
        )
        assert over_or_equal_limit.status_code == 200, over_or_equal_limit.text
        saved = container.session_service.get_session(session_id)
        assert saved.hard_constraints.max_credit == 22
        assert saved.hard_constraints.max_credit_inclusive is False

        more_than_lower_bound = client.post(
            f"/sessions/{session_id}/chat",
            json={"message": "15학점 초과로 듣고 싶어요"},
        )
        assert more_than_lower_bound.status_code == 200, more_than_lower_bound.text
        saved = container.session_service.get_session(session_id)
        assert saved.hard_constraints.min_credit == 15
        assert saved.hard_constraints.min_credit_inclusive is False

        clear = client.post(
            f"/sessions/{session_id}/chat",
            json={"message": "최소 학점 조건을 취소해줘"},
        )
        assert clear.status_code == 200, clear.text
        saved = container.session_service.get_session(session_id)
        assert saved.hard_constraints.min_credit is None
        assert saved.hard_constraints.max_credit == 22
        assert saved.hard_constraints.max_credit_inclusive is False

        invalid = client.post(
            f"/sessions/{session_id}/chat",
            json={"message": "최소 18학점, 최대 15학점으로 만들어줘"},
        )
        assert invalid.status_code == 200, invalid.text
        body = invalid.json()
        assert body["changed"] is False
        assert "INVALID_VALUE" in body["message"]
    finally:
        app.dependency_overrides.clear()


def test_public_chat_accepts_supported_preferences_and_keeps_ambiguous_requests_unresolved() -> None:
    container = build_container()
    runtime = AgentRuntime(
        session_service=container.session_service,
        agent=container.supervisor_agent,
        selection_tools=container.timetable_selection_tools,
        condition_summary_service=container.condition_summary_service,
    )
    app.dependency_overrides[get_agent_runtime] = lambda: runtime
    client = TestClient(app)

    try:
        state = container.session_service.create_session()
        session_id = state.session_id
        compact = client.post(
            f"/sessions/{session_id}/chat",
            json={"message": "가능하면 수업을 몰아서 듣고 싶어"},
        )
        ambiguous = client.post(
            f"/sessions/{session_id}/chat",
            json={"message": "편하게 만들어줘"},
        )
    finally:
        app.dependency_overrides.clear()

    assert compact.status_code == 200, compact.text
    assert compact.json()["changed"] is True
    assert "요청을 어떤 작업으로 처리할지 확인이 필요합니다" not in compact.json()["message"]
    saved = container.session_service.get_session(session_id)
    assert saved.soft_preferences.compact_schedule is True
    summary = compact.json()["condition_summary"]
    soft_items = {item["key"]: item for item in summary["soft_preferences"]}
    assert soft_items["compact_schedule"]["status"] == "SET"
    assert soft_items["compact_schedule"]["display_value"] == "몰아듣기 선호"
    assert soft_items["compact_schedule"]["raw_value"] is True

    assert ambiguous.status_code == 200, ambiguous.text
    assert ambiguous.json()["changed"] is False


def test_public_chat_handles_consecutive_area_and_latest_end_variants() -> None:
    container = build_container()
    runtime = AgentRuntime(
        session_service=container.session_service,
        agent=container.supervisor_agent,
        selection_tools=container.timetable_selection_tools,
        condition_summary_service=container.condition_summary_service,
    )
    app.dependency_overrides[get_agent_runtime] = lambda: runtime
    client = TestClient(app)

    try:
        state = container.session_service.create_session()
        session_id = state.session_id
        responses = [
            client.post(f"/sessions/{session_id}/chat", json={"message": message})
            for message in [
                "연강은 싫어요",
                "외국어 강의는 싫어요.",
                "수업이 가능하면 16시 이전에 전부 끝났으면 좋겠어요.",
                "모든 수업이 18시 이전에 끝났으면 좋겠어요.",
            ]
        ]
    finally:
        app.dependency_overrides.clear()

    for response in responses:
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["changed"] is True
        assert "요청을 어떤 작업으로 처리할지 확인이 필요합니다" not in body["message"]
        assert "변경할 조건을 찾지 못했습니다" not in body["message"]

    saved = container.session_service.get_session(session_id)
    assert saved.soft_preferences.compact_schedule is False
    assert saved.hard_constraints.excluded_elective_areas == [6]
    assert saved.soft_preferences.preferred_latest_end_time == "16:00"
    assert saved.hard_constraints.latest_end_time == "18:00"

    summary = responses[-1].json()["condition_summary"]
    hard_items = {item["key"]: item for item in summary["hard_constraints"]}
    soft_items = {item["key"]: item for item in summary["soft_preferences"]}
    assert hard_items["excluded_elective_areas"]["raw_value"] == [6]
    assert hard_items["latest_end_time"]["raw_value"] == "18:00"
    assert soft_items["preferred_latest_end_time"]["raw_value"] == "16:00"
    assert soft_items["compact_schedule"]["display_value"] == "연강 회피"


def test_simple_session_model_routes_course_names_to_catalog_search() -> None:
    model = SimpleSessionStateModel()

    result = model(
        {
            "messages": [
                {
                    "role": "user",
                    "content": {
                        "message": "고전읽기와토론은 선호하고 경제학원론은 제외해줘",
                        "current_state_summary": {
                            "major_catalog_id": "major-catalog",
                            "elective_catalog_id": "elective-catalog",
                        },
                    },
                }
            ]
        }
    )

    calls = result["tool_calls"]
    assert [call["name"] for call in calls] == ["search_courses_by_name"] * 4
    assert {call["arguments"]["query"] for call in calls} == {
        "고전읽기와토론",
        "경제학원론",
    }
    assert {call["arguments"]["catalog_id"] for call in calls} == {
        "major-catalog",
        "elective-catalog",
    }


def test_general_preference_parser_accepts_injected_llm_without_env(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    def fake_llm(_payload: dict[str, object]) -> dict[str, object]:
        return {
            "hard_conditions": {},
            "soft_conditions": {"preferred_free_days": ["FRI"]},
            "unsupported_conditions": [],
            "warnings": [],
        }

    parser = GeneralPreferenceParser(llm=fake_llm)
    result = parser.parse("금요일은 가능하면 쉬고 싶어")

    assert result.soft_conditions.preferred_free_days == [Day.FRI]
    assert result.unsupported_conditions == []


def test_public_chat_routes_requests_to_expected_domain_agents() -> None:
    with TestClient(app) as client:
        created = client.post("/sessions", json={"department": "컴퓨터공학과"})
        session_id = created.json()["session_id"]
        cases = [
            ("전공 과목을 찾아줘", AgentDomain.MAJOR),
            ("금요일은 반드시 비워줘", AgentDomain.PREFERENCE),
            ("현재 조건으로 시간표 만들어줘", AgentDomain.TIMETABLE),
            ("전체적으로 마음에 안 들어. 조건부터 다시 정할래", AgentDomain.PREFERENCE),
            ("이 시간표에서 자료구조 대신 다른 과목 하나만 바꿔줘", AgentDomain.TIMETABLE),
            ("금요일은 비우고 시간표 만들어줘", AgentDomain.PREFERENCE),
        ]
        for message, expected in cases:
            response = client.post(
                f"/sessions/{session_id}/chat",
                json={"message": message},
            )
            assert response.status_code == 200, response.text
            assert app.state.container.supervisor_agent.last_route is expected



def test_agent_runtime_constructor_depends_on_runnable_agent_protocol() -> None:
    hints = get_type_hints(AgentRuntime.__init__)

    assert hints["agent"] is RunnableAgent


