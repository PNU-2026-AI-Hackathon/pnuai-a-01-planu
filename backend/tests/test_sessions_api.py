"""API tests for session lookup routes."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from backend.app.agent_tools import CourseDiscoveryTools, SessionAgentTools
from backend.app.agents import SessionStateAgent, SessionStateToolset
from backend.app.agents.simple_session_model import SimpleSessionStateModel
from backend.app.deps import (
    get_condition_summary_service,
    get_session_service,
    get_session_state_agent,
    get_session_store,
)
from backend.app.main import app
from backend.app.models import Category, ClassTime, Course, Day
from backend.app.repositories import SessionStoreCatalogRepository, SessionStoreRepository
from backend.app.services.condition_summary_service import ConditionSummaryService
from backend.app.services.course_discovery_service import CourseDiscoveryService
from backend.app.services.session_service import SessionService
from backend.app.services.session_update_models import (
    HardConstraintsUpdate,
    SoftPreferencesUpdate,
)
from backend.app.services.session_store import SessionStage, SessionStore
from backend.app.services.timetable_generation_service import TimetableGenerationService


def _course(course_id: str = "MA100-001") -> Course:
    return Course(
        course_id=course_id,
        course_name="자료구조",
        category=Category.MAJOR_REQUIRED,
        credit=3,
        division="001",
        professor="김교수",
        class_times=[
            ClassTime(
                day=Day.MON,
                start="09:00",
                end="10:15",
                classroom="제6공학관 6201",
                building_code="6201",
            )
        ],
    )


def _named_course(course_id: str, name: str, *, category: Category = Category.MAJOR_REQUIRED) -> Course:
    return Course(
        course_id=course_id,
        course_name=name,
        category=category,
        area=3 if category is Category.GENERAL_ELECTIVE else None,
        credit=3,
        division=course_id.rsplit("-", 1)[-1],
        professor="김교수",
        class_times=[
            ClassTime(
                day=Day.MON,
                start="11:00",
                end="12:15",
                classroom="제6공학관 6201",
                building_code="6201",
            )
        ],
    )


def test_delete_timetable_condition_removes_one_list_value_and_returns_summary() -> None:
    store = SessionStore()
    service = SessionService(SessionStoreRepository(store))
    summary_service = ConditionSummaryService()
    state = service.create_session()
    service.update_preferences(
        state.session_id,
        hard_patch=HardConstraintsUpdate(required_free_days=[Day.WED, Day.FRI]),
        soft_patch=SoftPreferencesUpdate(preferred_free_days=[Day.THU]),
    )
    app.dependency_overrides[get_session_service] = lambda: service
    app.dependency_overrides[get_condition_summary_service] = lambda: summary_service
    client = TestClient(app)

    try:
        response = client.patch(
            f"/sessions/{state.session_id}/conditions",
            json={"scope": "hard", "key": "required_free_days", "value": "FRI"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200, response.text
    saved = service.get_session(state.session_id)
    assert saved.hard_constraints.required_free_days == [Day.WED]
    hard_items = {
        item["key"]: item
        for item in response.json()["hard_constraints"]
        if item["status"] == "SET"
    }
    assert hard_items["required_free_days"]["raw_value"] == ["WED"]


class ScriptedModel:
    def __init__(self, *responses):
        self.responses = list(responses)

    def __call__(self, _payload):
        if not self.responses:
            return {"message": "완료했습니다.", "tool_calls": []}
        return self.responses.pop(0)


class ExplodingTools(SessionStateToolset):
    def __init__(self, wrapped: SessionStateToolset, *, fail_on: str) -> None:
        self.wrapped = wrapped
        self.fail_on = fail_on

    def has_tool(self, name: str) -> bool:
        return self.wrapped.has_tool(name)

    def run(self, name: str, arguments):
        if name == self.fail_on:
            raise RuntimeError("raw service failure")
        return self.wrapped.run(name, arguments)

    def specs(self):
        return self.wrapped.specs()


def _agent_for_store(store: SessionStore, model=None) -> SessionStateAgent:
    session_service = SessionService(SessionStoreRepository(store))
    discovery_service = CourseDiscoveryService(SessionStoreCatalogRepository(store))
    return SessionStateAgent(
        model=model or SimpleSessionStateModel(),
        tools=SessionStateToolset.from_agent_and_discovery_tools(
            SessionAgentTools(session_service),
            CourseDiscoveryTools(discovery_service),
        ),
    )


def _exploding_agent_for_store(
    store: SessionStore,
    model,
    *,
    fail_on: str,
) -> SessionStateAgent:
    session_service = SessionService(SessionStoreRepository(store))
    discovery_service = CourseDiscoveryService(SessionStoreCatalogRepository(store))
    tools = SessionStateToolset.from_agent_and_discovery_tools(
        SessionAgentTools(session_service),
        CourseDiscoveryTools(discovery_service),
    )
    return SessionStateAgent(
        model=model,
        tools=ExplodingTools(tools, fail_on=fail_on),
    )


def test_major_candidates_lookup_returns_session_courses() -> None:
    store = SessionStore()
    session = store.create(
        "컴퓨터공학과",
        major_candidates=[_course()],
    )
    app.dependency_overrides[get_session_store] = lambda: store
    client = TestClient(app)

    try:
        response = client.get(f"/sessions/{session.session_id}/major-candidates")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == session.session_id
    assert body["session_stage"] == "catalog_parsed"
    assert body["department"] == "컴퓨터공학과"
    assert body["major_candidates"][0]["course_id"] == "MA100-001"
    assert body["major_candidates"][0]["course_name"] == "자료구조"


def test_major_candidates_lookup_uses_standard_missing_session_error() -> None:
    store = SessionStore()
    app.dependency_overrides[get_session_store] = lambda: store
    client = TestClient(app)

    try:
        response = client.get("/sessions/missing/major-candidates")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "SESSION_NOT_FOUND"


def test_major_candidates_lookup_uses_standard_expired_session_error() -> None:
    current = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def clock() -> datetime:
        return current

    store = SessionStore(ttl=timedelta(minutes=1), clock=clock)
    session = store.create("컴퓨터공학과", major_candidates=[_course()])
    current = current + timedelta(minutes=2)
    app.dependency_overrides[get_session_store] = lambda: store
    client = TestClient(app)

    try:
        response = client.get(f"/sessions/{session.session_id}/major-candidates")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "SESSION_NOT_FOUND"


def test_major_candidates_lookup_does_not_change_session_data_except_touch() -> None:
    store = SessionStore()
    session = store.create(
        "컴퓨터공학과",
        major_candidates=[_course()],
    )
    store.update(
        session.session_id,
        session_stage=SessionStage.MAJOR_CONFIRMED,
        fixed_courses=[_course()],
        confirmed_major_credits=3,
    )
    before = store.get(session.session_id, touch=False)
    app.dependency_overrides[get_session_store] = lambda: store
    client = TestClient(app)

    try:
        response = client.get(f"/sessions/{session.session_id}/major-candidates")
    finally:
        app.dependency_overrides.clear()

    after = store.get(session.session_id, touch=False)
    assert response.status_code == 200
    assert after.session_stage is before.session_stage
    assert after.department == before.department
    assert after.major_candidates == before.major_candidates
    assert after.fixed_courses == before.fixed_courses
    assert after.confirmed_major_credits == before.confirmed_major_credits


def test_agent_message_updates_same_session_store_used_by_existing_api() -> None:
    store = SessionStore()
    session = store.create("컴퓨터공학과", major_candidates=[_course()])
    app.dependency_overrides[get_session_state_agent] = lambda: _agent_for_store(store)
    client = TestClient(app)

    try:
        response = client.post(
            f"/sessions/{session.session_id}/agent/messages",
            json={
                "message": "금요일은 반드시 비워줘. 10시 이전 수업은 가능하면 피하고 싶어.",
                "request_id": "req-1",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["success"] is True
    assert body["request_id"] == "req-1"
    saved = store.get(session.session_id, touch=False)
    assert saved.hard_constraints.required_free_days == [Day.FRI]
    assert saved.soft_preferences.preferred_earliest_start_time == "10:00"


def test_agent_resolves_course_name_through_session_catalog_before_mutation() -> None:
    store = SessionStore()
    session = store.create("컴퓨터공학과", major_candidates=[_course("MA100-001")])
    model = ScriptedModel(
        {"tool_calls": [{"name": "search_courses_by_name", "arguments": {"catalog_id": session.major_catalog_id, "query": "자료구조"}}]},
        {"tool_calls": [{"name": "update_timetable_preferences", "arguments": {"hard": {"required_course_ids": ["MA100"]}}}]},
        {"message": "자료구조를 필수 과목으로 반영했습니다.", "tool_calls": []},
    )
    app.dependency_overrides[get_session_state_agent] = lambda: _agent_for_store(store, model)
    client = TestClient(app)

    try:
        response = client.post(
            f"/sessions/{session.session_id}/agent/messages",
            json={"message": "자료구조는 꼭 듣고 싶어"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200, response.text
    body = response.json()
    assert [tool["name"] for tool in body["executed_tools"]] == [
        "get_session_summary",
        "search_courses_by_name",
        "update_timetable_preferences",
        "get_session_summary",
    ]
    saved = store.get(session.session_id, touch=False)
    assert saved.hard_constraints.required_course_ids == ["MA100"]


def test_simple_agent_applies_complex_day_and_course_request_once() -> None:
    store = SessionStore()
    session = store.create("컴퓨터공학과", major_candidates=[_named_course("DS100-001", "자료구조")])
    app.dependency_overrides[get_session_state_agent] = lambda: _agent_for_store(store)
    client = TestClient(app)

    try:
        response = client.post(
            f"/sessions/{session.session_id}/agent/messages",
            json={"message": "금요일은 꼭 비우고 자료구조도 반드시 넣어줘."},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["success"] is True
    assert body["partially_applied"] is False
    assert [tool["name"] for tool in body["executed_tools"]].count("update_timetable_preferences") == 1
    saved = store.get(session.session_id, touch=False)
    assert saved.hard_constraints.required_free_days == [Day.FRI]
    assert saved.hard_constraints.required_course_ids == ["DS100"]


def test_simple_agent_handles_multiple_courses_with_different_intents() -> None:
    store = SessionStore()
    session = store.create("영어영문학과", major_candidates=[])
    store.update(
        session.session_id,
        elective_catalog_id=f"{session.session_id}:elective",
        elective_candidates=[
            _named_course("ENG101-001", "고급영어", category=Category.GENERAL_ELECTIVE),
            _named_course("ENG102-001", "대학영어", category=Category.GENERAL_ELECTIVE),
        ],
    )
    app.dependency_overrides[get_session_state_agent] = lambda: _agent_for_store(store)
    client = TestClient(app)

    try:
        response = client.post(
            f"/sessions/{session.session_id}/agent/messages",
            json={"message": "고급영어는 선호하지만 대학영어는 빼줘."},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["success"] is True
    saved = store.get(session.session_id, touch=False)
    assert saved.soft_preferences.preferred_course_ids == ["ENG101"]
    assert saved.hard_constraints.excluded_course_ids == ["ENG102"]


def test_simple_agent_searches_both_catalogs_and_does_not_choose_ambiguous_course() -> None:
    store = SessionStore()
    session = store.create(
        "컴퓨터공학과",
        major_candidates=[_named_course("MA100-001", "자료구조")],
    )
    store.update(
        session.session_id,
        elective_catalog_id=f"{session.session_id}:elective",
        elective_candidates=[_named_course("GE100-001", "자료구조", category=Category.GENERAL_ELECTIVE)],
    )
    app.dependency_overrides[get_session_state_agent] = lambda: _agent_for_store(store)
    client = TestClient(app)

    try:
        response = client.post(
            f"/sessions/{session.session_id}/agent/messages",
            json={"message": "자료구조는 꼭 넣어줘."},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["changed"] is False
    assert body["unresolved_requests"]
    assert len(body["unresolved_requests"][0]["candidates"]) == 2
    saved = store.get(session.session_id, touch=False)
    assert saved.hard_constraints.required_course_ids == []


def test_simple_agent_partially_applies_resolved_conditions_when_course_missing() -> None:
    store = SessionStore()
    session = store.create("컴퓨터공학과", major_candidates=[_named_course("DS100-001", "자료구조")])
    app.dependency_overrides[get_session_state_agent] = lambda: _agent_for_store(store)
    client = TestClient(app)

    try:
        response = client.post(
            f"/sessions/{session.session_id}/agent/messages",
            json={"message": "금요일은 꼭 비우고 존재하지 않는 과목은 넣어줘."},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["changed"] is True
    assert body["partially_applied"] is True
    assert body["unresolved_requests"]
    saved = store.get(session.session_id, touch=False)
    assert saved.hard_constraints.required_free_days == [Day.FRI]


def test_agent_message_tool_exception_returns_structured_agent_error() -> None:
    store = SessionStore()
    session = store.create("컴퓨터공학과")
    model = ScriptedModel(
        {
            "tool_calls": [
                {
                    "name": "update_timetable_preferences",
                    "arguments": {"hard": {"required_free_days": ["FRI"]}},
                },
                {
                    "name": "reset_session_preferences",
                    "arguments": {"target": "all"},
                },
            ]
        }
    )
    app.dependency_overrides[get_session_state_agent] = lambda: _exploding_agent_for_store(
        store,
        model,
        fail_on="reset_session_preferences",
    )
    client = TestClient(app)

    try:
        response = client.post(
            f"/sessions/{session.session_id}/agent/messages",
            json={"message": "금요일은 비우고 전체 조건은 초기화해줘."},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["success"] is False
    assert body["changed"] is True
    assert body["partially_applied"] is True
    assert body["error"]["code"] == "INTERNAL_ERROR"
    assert body["error"]["tool_name"] == "reset_session_preferences"
    assert "raw service failure" not in response.text
    saved = store.get(session.session_id, touch=False)
    assert saved.hard_constraints.required_free_days == [Day.FRI]


def test_simple_agent_time_correction_overwrites_single_time_fields() -> None:
    store = SessionStore()
    session = store.create("컴퓨터공학과")
    app.dependency_overrides[get_session_state_agent] = lambda: _agent_for_store(store)
    client = TestClient(app)

    try:
        first = client.post(
            f"/sessions/{session.session_id}/agent/messages",
            json={"message": "10시 이전 수업은 절대 안 돼."},
        )
        second = client.post(
            f"/sessions/{session.session_id}/agent/messages",
            json={"message": "9시부터는 괜찮아."},
        )
        third = client.post(
            f"/sessions/{session.session_id}/agent/messages",
            json={"message": "5시 이후 수업은 안 돼."},
        )
        fourth = client.post(
            f"/sessions/{session.session_id}/agent/messages",
            json={"message": "6시까지는 괜찮아."},
        )
    finally:
        app.dependency_overrides.clear()

    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 200
    assert fourth.status_code == 200
    saved = store.get(session.session_id, touch=False)
    assert saved.hard_constraints.earliest_start_time == "09:00"
    assert saved.hard_constraints.latest_end_time == "18:00"


def test_simple_agent_course_correction_removes_previous_required_course() -> None:
    store = SessionStore()
    session = store.create(
        "컴퓨터공학과",
        major_candidates=[
            _named_course("DS100-001", "자료구조"),
            _named_course("ALG100-001", "알고리즘"),
        ],
    )
    app.dependency_overrides[get_session_state_agent] = lambda: _agent_for_store(store)
    client = TestClient(app)

    try:
        first = client.post(
            f"/sessions/{session.session_id}/agent/messages",
            json={"message": "자료구조는 꼭 넣어줘."},
        )
        second = client.post(
            f"/sessions/{session.session_id}/agent/messages",
            json={"message": "자료구조는 빼고 알고리즘을 넣어줘."},
        )
    finally:
        app.dependency_overrides.clear()

    assert first.status_code == 200
    assert second.status_code == 200
    saved = store.get(session.session_id, touch=False)
    assert saved.hard_constraints.required_course_ids == ["ALG100"]
    assert saved.hard_constraints.excluded_course_ids == ["DS100"]


def test_generation_service_uses_agent_saved_constraints_from_same_session() -> None:
    store = SessionStore()
    session = store.create("컴퓨터공학과", major_candidates=[_course()])
    store.update(
        session.session_id,
        fixed_courses=[_course()],
        confirmed_major_credits=3,
        general_required_candidates=[],
        general_elective_candidates=[
            Course(
                course_id="GE100-001",
                course_name="고전읽기",
                category=Category.GENERAL_ELECTIVE,
                area=3,
                credit=3,
                division="001",
                professor="이교수",
                class_times=[
                    ClassTime(
                        day=Day.MON,
                        start="11:00",
                        end="12:15",
                        classroom="501-101",
                        building_code="501",
                    )
                ],
            )
        ],
        session_stage=SessionStage.GENERAL_READY,
    )
    service = SessionService(SessionStoreRepository(store))
    service.add_required_free_day(session.session_id, Day.FRI)

    result = TimetableGenerationService(store=store).generate_for_session(
        session_id=session.session_id,
        max_candidates=3,
    )

    assert result.hard_conditions.required_free_days == [Day.FRI]
    saved = store.get(session.session_id, touch=False)
    assert saved.generation_hard_conditions is not None
    assert saved.generation_hard_conditions.required_free_days == [Day.FRI]
