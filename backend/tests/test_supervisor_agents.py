"""Tests for Supervisor + domain-agent routing."""

from __future__ import annotations

from backend.app.agents import AgentDomain, PlanuSupervisorAgent, RunnableAgent, SessionStateAgentResult
from backend.app.agents.supervisor_agent import not_my_responsibility_result
from backend.app.container import build_container


class FakeModel:
    def __init__(self, *responses):
        self.responses = list(responses)

    def __call__(self, _payload):
        if self.responses:
            return self.responses.pop(0)
        return {"message": "처리했습니다.", "tool_calls": []}


class StubAgent:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def run(self, data):
        self.calls.append(data)
        return self.result


def _run_supervisor_message(container, message: str):
    session = container.session_service.create_session()
    return container.supervisor_agent.run(
        {"session_id": session.session_id, "user_message": message}
    )


def test_supervisor_routes_major_request_to_major_agent() -> None:
    container = build_container(model=FakeModel())

    result = _run_supervisor_message(container, "전공 분반을 확인해줘")

    assert result.success is True
    assert container.supervisor_agent.last_route is AgentDomain.MAJOR


def test_supervisor_routes_preference_crud_to_preference_agent() -> None:
    container = build_container(model=FakeModel())

    _run_supervisor_message(container, "금요일은 반드시 비워줘")

    assert container.supervisor_agent.last_route is AgentDomain.PREFERENCE


def test_supervisor_routes_timetable_generation_to_timetable_agent() -> None:
    container = build_container(model=FakeModel())

    _run_supervisor_message(container, "현재 조건으로 시간표 만들어줘")

    assert container.supervisor_agent.last_route is AgentDomain.TIMETABLE


def test_supervisor_routes_global_dislike_to_preference_agent() -> None:
    container = build_container(model=FakeModel())

    _run_supervisor_message(container, "전체적으로 마음에 안 들어. 조건부터 다시 정할래")

    assert container.supervisor_agent.last_route is AgentDomain.PREFERENCE


def test_supervisor_routes_small_revision_to_timetable_agent() -> None:
    container = build_container(model=FakeModel())

    _run_supervisor_message(container, "이 시간표에서 자료구조 대신 다른 과목 하나만 바꿔줘")

    assert container.supervisor_agent.last_route is AgentDomain.TIMETABLE


def test_supervisor_handles_not_my_responsibility_with_confirmation() -> None:
    not_mine = not_my_responsibility_result(
        session_id="s1",
        request_id=None,
        domain=AgentDomain.PREFERENCE,
    )
    success = SessionStateAgentResult(success=True, session_id="s1", message="재라우팅 완료")
    supervisor = PlanuSupervisorAgent(
        major_agent=StubAgent(success),
        preference_agent=StubAgent(not_mine),
        timetable_agent=StubAgent(success),
    )

    result = supervisor.run({"session_id": "s1", "user_message": "금요일은 비워줘"})

    assert result.success is False
    assert result.needs_confirmation is True
    assert supervisor.last_attempted_routes == [AgentDomain.PREFERENCE]

def test_domain_agents_expose_only_needed_cross_domain_tools() -> None:
    container = build_container(model=FakeModel())
    major_tools = set(container.major_agent.tool_names)
    preference_tools = set(container.preference_agent.tool_names)
    timetable_tools = set(container.timetable_agent.tool_names)

    assert "update_timetable_preferences" not in major_tools
    assert "rank_timetable_candidates" not in major_tools
    assert "search_courses_by_name" in preference_tools
    assert "generate_timetable_candidates" not in preference_tools
    assert "update_timetable_preferences" not in timetable_tools
    assert "rank_timetable_candidates" in timetable_tools
    assert "score_timetable_candidate" in timetable_tools


def test_timetable_agent_uses_ranking_tool_for_soft_scoring() -> None:
    model = FakeModel(
        {
            "tool_calls": [
                {
                    "name": "rank_timetable_candidates",
                    "arguments": {"candidates": [], "sections": [], "soft_preferences": {}},
                }
            ]
        }
    )
    container = build_container(model=model)
    session = container.session_service.create_session()

    result = container.timetable_agent.run(
        {"session_id": session.session_id, "user_message": "현재 조건으로 시간표 만들어줘"}
    )

    assert any(tool.name == "rank_timetable_candidates" for tool in result.executed_tools)
    assert "rank_timetable_candidates" in container.timetable_agent.tool_names


def test_complex_preference_plus_generation_request_prefers_preference_agent() -> None:
    container = build_container(model=FakeModel())

    _run_supervisor_message(container, "금요일은 비우고 이 조건으로 시간표 만들어줘")

    assert container.supervisor_agent.last_attempted_routes == [AgentDomain.PREFERENCE]
    assert container.supervisor_agent.last_route is AgentDomain.PREFERENCE


def test_domain_agents_use_distinct_system_prompts() -> None:
    container = build_container(model=FakeModel())

    assert "PlaNU Major Agent" in container.major_agent.agent.system_prompt
    assert "PlaNU Preference Agent" in container.preference_agent.agent.system_prompt
    assert "PlaNU Timetable Agent" in container.timetable_agent.agent.system_prompt
    assert len({
        container.major_agent.agent.system_prompt,
        container.preference_agent.agent.system_prompt,
        container.timetable_agent.agent.system_prompt,
    }) == 3


def test_runnable_agent_is_exported_from_agents_package() -> None:
    assert RunnableAgent is not None


def test_no_automatic_fallback_after_major_not_my_responsibility() -> None:
    not_mine = not_my_responsibility_result(session_id="s1", request_id=None, domain=AgentDomain.MAJOR)
    success = SessionStateAgentResult(success=True, session_id="s1", message="should not run")
    major = StubAgent(not_mine)
    preference = StubAgent(success)
    timetable = StubAgent(success)
    supervisor = PlanuSupervisorAgent(major_agent=major, preference_agent=preference, timetable_agent=timetable)

    result = supervisor.run({"session_id": "s1", "user_message": "전공 과목을 찾아줘"})

    assert result.needs_confirmation is True
    assert supervisor.last_attempted_routes == [AgentDomain.MAJOR]
    assert preference.calls == []
    assert timetable.calls == []


def test_no_automatic_fallback_after_preference_not_my_responsibility() -> None:
    not_mine = not_my_responsibility_result(session_id="s1", request_id=None, domain=AgentDomain.PREFERENCE)
    success = SessionStateAgentResult(success=True, session_id="s1", message="should not run")
    major = StubAgent(success)
    preference = StubAgent(not_mine)
    timetable = StubAgent(success)
    supervisor = PlanuSupervisorAgent(major_agent=major, preference_agent=preference, timetable_agent=timetable)

    result = supervisor.run({"session_id": "s1", "user_message": "금요일은 비워줘"})

    assert result.needs_confirmation is True
    assert supervisor.last_attempted_routes == [AgentDomain.PREFERENCE]
    assert major.calls == []
    assert timetable.calls == []


def test_no_automatic_fallback_after_timetable_not_my_responsibility() -> None:
    not_mine = not_my_responsibility_result(session_id="s1", request_id=None, domain=AgentDomain.TIMETABLE)
    success = SessionStateAgentResult(success=True, session_id="s1", message="should not run")
    major = StubAgent(success)
    preference = StubAgent(success)
    timetable = StubAgent(not_mine)
    supervisor = PlanuSupervisorAgent(major_agent=major, preference_agent=preference, timetable_agent=timetable)

    result = supervisor.run({"session_id": "s1", "user_message": "현재 조건으로 시간표 만들어줘"})

    assert result.needs_confirmation is True
    assert supervisor.last_attempted_routes == [AgentDomain.TIMETABLE]
    assert major.calls == []
    assert preference.calls == []


def test_confirmation_message_asks_user_to_clarify_request_type() -> None:
    not_mine = not_my_responsibility_result(session_id="s1", request_id=None, domain=AgentDomain.MAJOR)
    supervisor = PlanuSupervisorAgent(
        major_agent=StubAgent(not_mine),
        preference_agent=StubAgent(not_mine),
        timetable_agent=StubAgent(not_mine),
    )

    result = supervisor.run({"session_id": "s1", "user_message": "전공 관련해서 봐줘"})

    assert result.needs_confirmation is True
    assert result.confirmation_request is not None
    assert "전공 과목, 조건 변경, 시간표 생성/수정" in result.confirmation_request.question



