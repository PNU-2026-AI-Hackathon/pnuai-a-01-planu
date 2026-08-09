"""Tests for PlaNU's single session-state management agent."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from backend.app.agent_tools import (
    CourseDiscoveryTools,
    SessionAgentTools,
    SessionCommandTools,
    SessionQueryTools,
    TimetableGenerationTools,
    TimetableScoringTools,
)
from backend.app.agents import (
    SessionStateAgent,
    SessionStateAgentErrorCode,
    SessionStateToolset,
)
from backend.app.models import CatalogKind, Category, ClassTime, Course, Day
from backend.app.repositories import InMemoryCatalogRepository, InMemorySessionRepository
from backend.app.services.course_discovery_service import CourseDiscoveryService
from backend.app.services.session_service import SessionService
from backend.app.services.timetable_candidate_generation_service import (
    TimetableCandidateGenerationService,
)
from backend.app.services.timetable_candidate_validation_service import (
    TimetableCandidateValidationService,
)
from backend.app.services.timetable_preparation_service import (
    TimetablePreparationIssueCode,
    TimetablePreparationOptions,
    TimetablePreparationService,
)


class MutableClock:
    def __init__(self, current: datetime) -> None:
        self.current = current

    def __call__(self) -> datetime:
        return self.current

    def advance(self, delta: timedelta) -> datetime:
        self.current = self.current + delta
        return self.current


class ScriptedModel:
    def __init__(self, *responses: dict[str, Any] | Exception) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def __call__(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(payload)
        if not self.responses:
            return {"message": "완료했습니다.", "tool_calls": []}
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class RecordingTools(SessionStateToolset):
    def __init__(self, wrapped: SessionStateToolset) -> None:
        self.wrapped = wrapped
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.results: list[Any] = []

    def has_tool(self, name: str) -> bool:
        return self.wrapped.has_tool(name)

    def run(self, name: str, arguments):
        self.calls.append((name, dict(arguments)))
        result = self.wrapped.run(name, arguments)
        self.results.append(result)
        return result

    def specs(self):
        return self.wrapped.specs()


class ExplodingTools(RecordingTools):
    def __init__(self, wrapped: SessionStateToolset, *, fail_on: str) -> None:
        super().__init__(wrapped)
        self.fail_on = fail_on

    def run(self, name: str, arguments):
        self.calls.append((name, dict(arguments)))
        if name == self.fail_on:
            raise RuntimeError("raw repository failure")
        result = self.wrapped.run(name, arguments)
        self.results.append(result)
        return result


def _now() -> datetime:
    return datetime(2026, 7, 26, 12, 0, tzinfo=timezone.utc)


def _service(clock: MutableClock | None = None) -> SessionService:
    return SessionService(
        InMemorySessionRepository(),
        session_ttl=timedelta(minutes=30),
        now_provider=clock or MutableClock(_now()),
        session_id_provider=lambda: "session-1",
    )


def _agent(
    model: ScriptedModel,
    *,
    service: SessionService | None = None,
    max_mutation_tool_calls: int = 10,
) -> tuple[SessionStateAgent, SessionService, RecordingTools]:
    service = service or _service()
    tools = RecordingTools(
        SessionStateToolset.from_query_and_command_tools(
            SessionQueryTools(service),
            SessionCommandTools(service),
        )
    )
    return (
        SessionStateAgent(
            model=model,
            tools=tools,
            max_mutation_tool_calls=max_mutation_tool_calls,
        ),
        service,
        tools,
    )


def _agent_with_discovery(
    model: ScriptedModel,
    *,
    service: SessionService | None = None,
    max_mutation_tool_calls: int = 10,
    max_tool_calls: int | None = None,
) -> tuple[SessionStateAgent, SessionService, RecordingTools, InMemoryCatalogRepository]:
    service = service or _service()
    catalog_repository = InMemoryCatalogRepository()
    _register_test_catalogs(catalog_repository)
    tools = RecordingTools(
        SessionStateToolset.from_agent_and_discovery_tools(
            SessionAgentTools(service),
            CourseDiscoveryTools(CourseDiscoveryService(catalog_repository)),
            TimetableGenerationTools(
                generation_service=TimetableCandidateGenerationService(
                    catalog_repository=catalog_repository,
                ),
                validation_service=TimetableCandidateValidationService(
                    catalog_repository=catalog_repository,
                ),
            ),
            TimetableScoringTools(),
        )
    )
    return (
        SessionStateAgent(
            model=model,
            tools=tools,
            max_mutation_tool_calls=max_mutation_tool_calls,
            max_tool_calls=max_tool_calls,
        ),
        service,
        tools,
        catalog_repository,
    )


def _create_session(service: SessionService) -> str:
    return service.create_session().session_id


def _run(
    agent: SessionStateAgent,
    session_id: str,
    message: str = "금요일은 반드시 비워줘",
    *,
    request_id: str | None = None,
):
    data: dict[str, object] = {"session_id": session_id, "user_message": message}
    if request_id is not None:
        data["request_id"] = request_id
    return agent.run(data)


def _tool(name: str, **arguments: object) -> dict[str, Any]:
    return {"name": name, "arguments": arguments}


def _class_time(day: Day, start: str, end: str) -> ClassTime:
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
    category: Category,
    area: int | None = None,
    department: str | None = None,
    class_times: list[ClassTime] | None = None,
) -> Course:
    return Course(
        course_id=f"{code}-{division}",
        course_name=name,
        category=category,
        area=area,
        credit=3,
        division=division,
        professor="김교수",
        class_times=class_times or [_class_time(Day.MON, "10:00", "11:15")],
    )


def _class_time_json(day: str, start: str, end: str) -> dict[str, str]:
    return {
        "day": day,
        "start": start,
        "end": end,
        "classroom": "609-313",
        "building_code": "609",
    }


def _section_json(
    catalog_id: str,
    section_id: str,
    course_id: str,
    course_name: str,
    *,
    day: str,
    start: str = "10:00",
    end: str = "11:15",
) -> dict[str, object]:
    return {
        "catalog_id": catalog_id,
        "section": {
            "section_id": section_id,
            "course_id": course_id,
            "course_code": course_id,
            "course_name": course_name,
            "category": "GENERAL_ELECTIVE" if course_id.startswith("GEN") else "MAJOR_REQUIRED",
            "area": 3 if course_id.startswith("GEN") else None,
            "department": "교양교육원" if course_id.startswith("GEN") else "정보컴퓨터공학부",
            "credit": 3,
            "division": section_id.rsplit("-", 1)[-1],
            "professor": "김교수",
            "class_times": [_class_time_json(day, start, end)],
        },
    }


def _candidate_json(
    candidate_id: str,
    added_section_id: str,
    added_course_id: str,
) -> dict[str, object]:
    section_sources = [
        {"catalog_id": "major-1", "section_id": "MAJ101-001"},
        {"catalog_id": "elective-1", "section_id": added_section_id},
    ]
    return {
        "candidate_id": candidate_id,
        "section_ids": ["MAJ101-001", added_section_id],
        "section_sources": section_sources,
        "fixed_section_ids": ["MAJ101-001"],
        "fixed_section_sources": [section_sources[0]],
        "added_section_ids": [added_section_id],
        "added_section_sources": [section_sources[1]],
        "course_ids": ["MAJ101", added_course_id],
        "total_credits": 6,
        "validation": {
            "valid": True,
            "violations": [],
            "checked_section_ids": ["MAJ101-001", added_section_id],
            "checked_section_sources": section_sources,
        },
        "generation_order": 1 if added_course_id == "GEN101" else 2,
    }


def _register_test_catalogs(repository: InMemoryCatalogRepository) -> None:
    repository.register(
        "major-1",
        kind=CatalogKind.MAJOR,
        department="정보컴퓨터공학부",
        courses=[
            _course(
                "MAJ101",
                "001",
                "컴퓨터프로그래밍",
                category=Category.MAJOR_REQUIRED,
                department="정보컴퓨터공학부",
            ),
            _course(
                "MAJ101",
                "002",
                "컴퓨터프로그래밍",
                category=Category.MAJOR_REQUIRED,
                department="정보컴퓨터공학부",
                class_times=[_class_time(Day.FRI, "13:00", "14:15")],
            ),
            _course(
                "MAJ201",
                "001",
                "자료구조",
                category=Category.MAJOR_REQUIRED,
                department="정보컴퓨터공학부",
            ),
        ],
    )
    repository.register(
        "elective-1",
        kind=CatalogKind.ELECTIVE,
        courses=[
            _course(
                "GEN101",
                "001",
                "컴퓨터와사회",
                category=Category.GENERAL_ELECTIVE,
                area=3,
                department="교양교육원",
                class_times=[_class_time(Day.WED, "10:00", "11:15")],
            ),
            _course(
                "GEN102",
                "001",
                "데이터와사회",
                category=Category.GENERAL_ELECTIVE,
                area=3,
                department="교양교육원",
                class_times=[_class_time(Day.MON, "10:00", "11:15")],
            ),
            _course(
                "GEN103",
                "001",
                "금요일세미나",
                category=Category.GENERAL_ELECTIVE,
                area=3,
                department="교양교육원",
                class_times=[_class_time(Day.FRI, "10:00", "11:15")],
            ),
            _course(
                "GEN201",
                "001",
                "대학수학(I)",
                category=Category.GENERAL_ELECTIVE,
                area=2,
                department="수학과",
            ),
            _course(
                "GEN202",
                "001",
                "대학수학(II)",
                category=Category.GENERAL_ELECTIVE,
                area=2,
                department="수학과",
            ),
        ],
    )


def test_blank_user_message_is_rejected_without_model_or_tool_call() -> None:
    model = ScriptedModel({"tool_calls": []})
    agent, _service, tools = _agent(model)

    result = agent.run({"session_id": "session-1", "user_message": "   "})

    assert result.success is False
    assert result.error is not None
    assert result.error.code == SessionStateAgentErrorCode.INVALID_INPUT
    assert model.calls == []
    assert tools.calls == []


def test_missing_session_stops_before_state_mutations() -> None:
    agent, _service, tools = _agent(
        ScriptedModel({"tool_calls": [_tool("add_required_free_day", day="FRI")]})
    )

    result = _run(agent, "missing")

    assert result.success is False
    assert result.error is not None
    assert result.error.code == SessionStateAgentErrorCode.SESSION_NOT_AVAILABLE
    assert [name for name, _args in tools.calls] == ["get_session_summary"]


def test_initial_and_final_session_summary_are_called_even_without_changes() -> None:
    model = ScriptedModel({"message": "변경 없음", "tool_calls": []})
    agent, service, tools = _agent(model)
    session_id = _create_session(service)

    result = _run(agent, session_id)

    assert result.success is True
    assert result.changed is False
    assert result.state_summary is not None
    assert [name for name, _args in tools.calls] == [
        "get_session_summary",
        "get_session_summary",
    ]


@pytest.mark.parametrize(
    ("message", "tool_call", "expected_field"),
    [
        (
            "금요일은 반드시 비워줘",
            _tool("add_required_free_day", day="FRI"),
            ("hard_days", [Day.FRI]),
        ),
        (
            "가능하면 금요일을 비워줘",
            _tool("add_preferred_free_day", day="FRI"),
            ("soft_days", [Day.FRI]),
        ),
        (
            "오전 10시 전 수업은 절대 넣지 마",
            _tool("set_earliest_start_time", time="10:00"),
            ("hard_start", "10:00"),
        ),
        (
            "가능하면 10시 이후에 시작하고 싶어",
            _tool("set_preferred_earliest_start_time", time="10:00"),
            ("soft_start", "10:00"),
        ),
        (
            "공강이 적은 시간표가 좋아",
            _tool("set_compact_schedule_preference", value=True),
            ("compact", True),
        ),
    ],
)
def test_single_condition_tool_selection_results_in_expected_state(
    message: str,
    tool_call: dict[str, Any],
    expected_field: tuple[str, object],
) -> None:
    agent, service, tools = _agent(
        ScriptedModel({"tool_calls": [tool_call]}, {"message": "반영했습니다."})
    )
    session_id = _create_session(service)

    result = _run(agent, session_id, message)

    assert result.success is True
    assert result.changed is True
    assert [name for name, _args in tools.calls][1] == tool_call["name"]
    summary = result.state_summary
    assert summary is not None
    field_name, expected = expected_field
    if field_name == "hard_days":
        assert summary.hard_constraints.required_free_days == expected
    elif field_name == "soft_days":
        assert summary.soft_preferences.preferred_free_days == expected
    elif field_name == "hard_start":
        assert summary.hard_constraints.earliest_start_time == expected
    elif field_name == "soft_start":
        assert summary.soft_preferences.preferred_earliest_start_time == expected
    else:
        assert summary.soft_preferences.compact_schedule == expected


@pytest.mark.parametrize(
    ("setup_tool", "tool_call", "expected_names"),
    [
        (
            ("add_required_free_day", {"day": "FRI"}),
            _tool("remove_required_free_day", day="FRI"),
            ["get_session_summary", "remove_required_free_day", "get_session_summary"],
        ),
        (
            ("set_earliest_start_time", {"time": "10:00"}),
            _tool("clear_earliest_start_time"),
            ["get_session_summary", "clear_earliest_start_time", "get_session_summary"],
        ),
        (
            ("add_preferred_free_day", {"day": "FRI"}),
            _tool("clear_soft_preferences"),
            ["get_session_summary", "clear_soft_preferences", "get_session_summary"],
        ),
    ],
)
def test_removal_requests_call_targeted_clear_or_remove_tools(
    setup_tool: tuple[str, dict[str, object]],
    tool_call: dict[str, Any],
    expected_names: list[str],
) -> None:
    agent, service, tools = _agent(
        ScriptedModel({"tool_calls": [tool_call]}, {"message": "삭제했습니다."})
    )
    session_id = _create_session(service)
    getattr(SessionCommandTools(service), setup_tool[0])(
        {"session_id": session_id, **setup_tool[1]}
    )

    result = _run(agent, session_id, "조건 취소")

    assert result.success is True
    assert [name for name, _args in tools.calls] == expected_names


def test_multiple_conditions_execute_in_order_and_continue_after_idempotent_tool() -> None:
    agent, service, tools = _agent(
        ScriptedModel(
            {
                "tool_calls": [
                    _tool("add_required_free_day", day="FRI"),
                    _tool("add_required_free_day", day="FRI"),
                    _tool("set_earliest_start_time", time="10:00"),
                    _tool("add_required_course", course_id="C001"),
                    _tool("add_excluded_course", course_id="C002"),
                ]
            },
            {"message": "여러 조건을 반영했습니다."},
        )
    )
    session_id = _create_session(service)

    result = _run(agent, session_id, "금요일은 비우고 오전 10시 전 수업은 빼줘.")

    assert result.success is True
    assert result.changed is True
    assert [item.name for item in result.executed_tools] == [
        "get_session_summary",
        "add_required_free_day",
        "add_required_free_day",
        "set_earliest_start_time",
        "add_required_course",
        "add_excluded_course",
        "get_session_summary",
    ]
    assert result.executed_tools[2].changed is False
    assert [name for name, _args in tools.calls][1:-1] == [
        "add_required_free_day",
        "add_required_free_day",
        "set_earliest_start_time",
        "add_required_course",
        "add_excluded_course",
    ]


def test_tool_error_makes_final_result_partial_even_when_following_tool_runs() -> None:
    agent, service, _tools = _agent(
        ScriptedModel(
            {
                "tool_calls": [
                    _tool("add_excluded_course", course_id="C001"),
                    _tool("add_preferred_course", course_id="C001"),
                    _tool("add_required_free_day", day="TUE"),
                ]
            },
            {"message": "가능한 조건은 반영했습니다."},
        )
    )
    session_id = _create_session(service)

    result = _run(agent, session_id)

    assert result.success is False
    assert result.changed is True
    assert result.partially_applied is True
    assert result.executed_tools[2].success is False
    assert result.executed_tools[2].error_code == "CONFLICTING_CONSTRAINT"
    assert [tool.name for tool in result.failed_tools] == ["add_preferred_course"]
    assert result.failed_tools[0].error_code == "CONFLICTING_CONSTRAINT"
    assert result.error is not None
    assert result.error.code == SessionStateAgentErrorCode.TOOL_ERROR
    assert result.state_summary is not None
    assert result.state_summary.hard_constraints.required_free_days == [Day.TUE]
    assert any("add_preferred_course" in item.source_text for item in result.unresolved_requests)


def test_partial_success_does_not_trust_unsafe_model_message() -> None:
    agent, service, _tools = _agent(
        ScriptedModel(
            {
                "tool_calls": [
                    _tool("add_required_free_day", day="FRI"),
                    _tool("add_required_course", course_id="C001"),
                    _tool("add_disliked_course", course_id="C001"),
                ]
            },
            {"message": "모든 조건을 반영했습니다."},
        )
    )
    session_id = _create_session(service)

    result = _run(agent, session_id)

    assert result.success is False
    assert result.changed is True
    assert result.partially_applied is True
    assert result.state_summary is not None
    assert result.state_summary.hard_constraints.required_free_days == [Day.FRI]
    assert result.failed_tools[0].name == "add_disliked_course"
    assert result.failed_tools[0].error_code == "CONFLICTING_CONSTRAINT"
    assert "모든 조건" not in result.message
    assert "일부 조건" in result.message


def test_first_mutation_failure_returns_structured_failure_without_state_change() -> None:
    agent, service, _tools = _agent(
        ScriptedModel(
            {"tool_calls": [_tool("add_preferred_course", course_id="C001")]},
            {"message": "모두 반영했습니다."},
        )
    )
    session_id = _create_session(service)
    SessionCommandTools(service).add_excluded_course(
        {"session_id": session_id, "course_id": "C001"}
    )

    result = _run(agent, session_id)

    assert result.success is False
    assert result.changed is False
    assert result.partially_applied is False
    assert result.failed_tools[0].name == "add_preferred_course"
    assert result.failed_tools[0].error_code == "CONFLICTING_CONSTRAINT"
    assert result.error is not None
    assert result.error.code == SessionStateAgentErrorCode.TOOL_ERROR
    assert result.state_summary is not None
    assert result.state_summary.soft_preferences.preferred_course_ids == []
    assert result.state_summary.hard_constraints.excluded_course_ids == ["C001"]


def test_current_state_modification_uses_remove_then_add_without_replacing_state() -> None:
    agent, service, tools = _agent(
        ScriptedModel(
            {
                "tool_calls": [
                    _tool("remove_required_free_day", day="FRI"),
                    _tool("add_required_free_day", day="TUE"),
                ]
            },
            {"message": "금요일 공강을 취소하고 화요일 공강을 추가했습니다."},
        )
    )
    session_id = _create_session(service)
    SessionCommandTools(service).add_required_free_day(
        {"session_id": session_id, "day": "FRI"}
    )

    result = _run(agent, session_id, "금요일 공강은 취소하고 화요일을 비워줘.")

    assert result.success is True
    assert [name for name, _args in tools.calls][1:-1] == [
        "remove_required_free_day",
        "add_required_free_day",
    ]
    assert "replace_required_free_days" not in [name for name, _args in tools.calls]
    assert result.state_summary is not None
    assert result.state_summary.hard_constraints.required_free_days == [Day.TUE]


def test_repeated_same_condition_returns_changed_false() -> None:
    agent, service, _tools = _agent(
        ScriptedModel(
            {"tool_calls": [_tool("add_required_free_day", day="FRI")]},
            {"message": "이미 반영된 조건입니다."},
        )
    )
    session_id = _create_session(service)
    SessionCommandTools(service).add_required_free_day(
        {"session_id": session_id, "day": "FRI"}
    )

    result = _run(agent, session_id)

    assert result.success is True
    assert result.changed is False
    assert result.partially_applied is False
    assert result.failed_tools == []


def test_idempotent_remove_missing_value_is_not_failed_tool() -> None:
    agent, service, _tools = _agent(
        ScriptedModel(
            {"tool_calls": [_tool("remove_required_free_day", day="FRI")]},
            {"message": "변경 없음"},
        )
    )
    session_id = _create_session(service)

    result = _run(agent, session_id)

    assert result.success is True
    assert result.changed is False
    assert result.partially_applied is False
    assert result.failed_tools == []
    assert result.executed_tools[1].success is True
    assert result.executed_tools[1].changed is False


@pytest.mark.parametrize(
    ("message", "source_text", "reason"),
    [
        (
            "컴퓨터프로그래밍을 반드시 넣어줘.",
            "컴퓨터프로그래밍",
            "과목명에 대응하는 course ID 조회 도구가 아직 없습니다.",
        ),
        (
            "발표가 적은 수업을 듣고 싶어.",
            "발표가 적은 수업",
            "현재 수강편람 데이터에서는 발표 여부를 확인할 수 없습니다.",
        ),
        (
            "가능하면 늦게 시작하고 싶어.",
            "늦게 시작",
            "구체적인 시작 시간이 필요합니다.",
        ),
    ],
)
def test_unresolved_requests_are_structured_and_not_applied(
    message: str,
    source_text: str,
    reason: str,
) -> None:
    agent, service, tools = _agent(
        ScriptedModel(
            {
                "message": "확인이 필요한 요청이 있습니다.",
                "unresolved_requests": [
                    {
                        "source_text": source_text,
                        "reason": reason,
                        "needed_information": "course_id 또는 구체적 기준",
                        "requires_user_confirmation": True,
                    }
                ],
            }
        )
    )
    session_id = _create_session(service)

    result = _run(agent, session_id, message)

    assert result.success is True
    assert result.changed is False
    assert result.unresolved_requests[0].source_text == source_text
    assert result.unresolved_requests[0].reason == reason
    assert [name for name, _args in tools.calls] == [
        "get_session_summary",
        "get_session_summary",
    ]
    assert "반영했습니다" not in result.message


def test_unknown_tool_name_returns_structured_model_error() -> None:
    agent, service, _tools = _agent(
        ScriptedModel({"tool_calls": [_tool("search_course_by_name", query="자료구조")]})
    )
    session_id = _create_session(service)

    result = _run(agent, session_id)

    assert result.success is False
    assert result.error is not None
    assert result.error.code == SessionStateAgentErrorCode.UNKNOWN_TOOL
    assert result.error.tool_name == "search_course_by_name"


def test_invalid_tool_arguments_return_structured_model_error() -> None:
    agent, service, _tools = _agent(
        ScriptedModel({"tool_calls": [_tool("add_required_course", course_id="   ")]})
    )
    session_id = _create_session(service)

    result = _run(agent, session_id)

    assert result.success is False
    assert result.error is not None
    assert result.error.code == SessionStateAgentErrorCode.INVALID_TOOL_ARGUMENTS
    assert result.error.tool_name == "add_required_course"
    assert result.error.field == "course_id"


def test_tool_call_limit_stops_without_infinite_recall() -> None:
    model = ScriptedModel(
        {"tool_calls": [_tool("add_required_free_day", day="FRI")]},
        {"message": "완료했습니다."},
    )
    agent, service, _tools = _agent(model, max_mutation_tool_calls=0)
    session_id = _create_session(service)

    result = _run(agent, session_id)

    assert result.success is False
    assert result.error is not None
    assert result.error.code == SessionStateAgentErrorCode.TOOL_CALL_LIMIT_EXCEEDED
    assert result.changed is False
    assert result.partially_applied is False
    assert len(model.calls) == 1


def test_max_mutation_tool_calls_excludes_initial_and_final_summary_queries() -> None:
    agent, service, tools = _agent(
        ScriptedModel(
            {
                "tool_calls": [
                    _tool("add_required_free_day", day="FRI"),
                    _tool("set_earliest_start_time", time="10:00"),
                ]
            },
            {"message": "반영했습니다."},
        ),
        max_mutation_tool_calls=2,
    )
    session_id = _create_session(service)

    result = _run(agent, session_id)

    assert result.success is True
    assert result.changed is True
    assert [name for name, _args in tools.calls] == [
        "get_session_summary",
        "add_required_free_day",
        "set_earliest_start_time",
        "get_session_summary",
    ]
    assert result.state_summary is not None
    assert result.state_summary.hard_constraints.required_free_days == [Day.FRI]
    assert result.state_summary.hard_constraints.earliest_start_time == "10:00"


def test_mutation_limit_excess_tool_is_not_executed_and_current_state_is_returned() -> None:
    agent, service, tools = _agent(
        ScriptedModel(
            {
                "tool_calls": [
                    _tool("add_required_free_day", day="FRI"),
                    _tool("set_earliest_start_time", time="10:00"),
                    _tool("set_latest_end_time", time="17:00"),
                ]
            }
        ),
        max_mutation_tool_calls=2,
    )
    session_id = _create_session(service)

    result = _run(agent, session_id)

    assert result.success is False
    assert result.changed is True
    assert result.partially_applied is True
    assert result.error is not None
    assert result.error.code == SessionStateAgentErrorCode.TOOL_CALL_LIMIT_EXCEEDED
    assert [name for name, _args in tools.calls] == [
        "get_session_summary",
        "add_required_free_day",
        "set_earliest_start_time",
    ]
    assert "set_latest_end_time" not in [name for name, _args in tools.calls]
    assert result.state_summary is not None
    assert result.state_summary.hard_constraints.required_free_days == [Day.FRI]
    assert result.state_summary.hard_constraints.earliest_start_time == "10:00"
    assert result.state_summary.hard_constraints.latest_end_time is None


def test_request_id_is_passed_to_model_and_result() -> None:
    model = ScriptedModel({"message": "변경 없음", "tool_calls": []})
    agent, service, _tools = _agent(model)
    session_id = _create_session(service)

    result = _run(agent, session_id, request_id="req-123")

    assert result.request_id == "req-123"
    assert model.calls[0]["messages"][1]["content"]["request_id"] == "req-123"


def test_model_failure_is_sanitized_and_external_llm_is_not_required() -> None:
    model = ScriptedModel(RuntimeError("raw provider failure"))
    agent, service, _tools = _agent(model)
    session_id = _create_session(service)

    result = _run(agent, session_id)

    assert result.success is False
    assert result.error is not None
    assert result.error.code == SessionStateAgentErrorCode.MODEL_CALL_FAILED
    assert "raw provider failure" not in result.message


def test_model_supplied_session_id_is_overridden_by_request_session_id() -> None:
    ids = iter(["url-session", "other-session"])
    service = SessionService(
        InMemorySessionRepository(),
        session_ttl=timedelta(minutes=30),
        now_provider=MutableClock(_now()),
        session_id_provider=lambda: next(ids),
    )
    url_session_id = _create_session(service)
    other_session_id = _create_session(service)
    tools = RecordingTools(
        SessionStateToolset.from_agent_and_discovery_tools(
            SessionAgentTools(service),
            CourseDiscoveryTools(CourseDiscoveryService(InMemoryCatalogRepository())),
        )
    )
    agent = SessionStateAgent(
        model=ScriptedModel(
            {
                "tool_calls": [
                    _tool(
                        "update_timetable_preferences",
                        session_id=other_session_id,
                        hard={"required_free_days": ["FRI"]},
                    )
                ]
            },
            {"message": "반영했습니다.", "tool_calls": []},
        ),
        tools=tools,
    )

    result = _run(agent, url_session_id)

    assert result.success is True
    assert tools.calls[1][0] == "update_timetable_preferences"
    assert tools.calls[1][1]["session_id"] == url_session_id
    assert tools.results[1].session_id == url_session_id
    assert result.state_summary is not None
    assert result.state_summary.session_id == url_session_id
    assert service.get_session(url_session_id).hard_constraints.required_free_days == [Day.FRI]
    assert service.get_session(other_session_id).hard_constraints.required_free_days == []


def test_unexpected_tool_exception_returns_structured_internal_error() -> None:
    service = _service()
    wrapped = SessionStateToolset.from_agent_and_discovery_tools(
        SessionAgentTools(service),
        CourseDiscoveryTools(CourseDiscoveryService(InMemoryCatalogRepository())),
    )
    tools = ExplodingTools(wrapped, fail_on="reset_session_preferences")
    agent = SessionStateAgent(
        model=ScriptedModel(
            {
                "tool_calls": [
                    _tool(
                        "update_timetable_preferences",
                        hard={"required_free_days": ["FRI"]},
                    ),
                    _tool("reset_session_preferences", target="all"),
                ]
            }
        ),
        tools=tools,
    )
    session_id = _create_session(service)

    result = _run(agent, session_id, request_id="req-internal")

    assert result.success is False
    assert result.changed is True
    assert result.partially_applied is True
    assert result.request_id == "req-internal"
    assert result.error is not None
    assert result.error.code == SessionStateAgentErrorCode.INTERNAL_ERROR
    assert result.error.tool_name == "reset_session_preferences"
    assert "raw repository failure" not in result.message
    assert "raw repository failure" not in result.error.message
    assert [tool.name for tool in result.executed_tools] == [
        "get_session_summary",
        "update_timetable_preferences",
    ]
    assert result.failed_tools == []
    assert service.get_session(session_id).hard_constraints.required_free_days == [Day.FRI]


@pytest.mark.parametrize(
    ("max_tool_calls", "max_mutation_tool_calls", "message"),
    [
        (0, 0, "max_tool_calls must be at least 1"),
        (-1, 0, "max_tool_calls must be at least 1"),
        (1, -1, "max_mutation_tool_calls must not be negative"),
        (1, 2, "max_mutation_tool_calls must not exceed max_tool_calls"),
    ],
)
def test_tool_call_limit_configuration_rejects_invalid_values(
    max_tool_calls: int,
    max_mutation_tool_calls: int,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        SessionStateAgent(
            model=ScriptedModel({"tool_calls": []}),
            tools=SessionStateToolset({}),
            max_tool_calls=max_tool_calls,
            max_mutation_tool_calls=max_mutation_tool_calls,
        )


def test_tool_call_limit_configuration_accepts_boundary_values() -> None:
    agent = SessionStateAgent(
        model=ScriptedModel({"tool_calls": []}),
        tools=SessionStateToolset({}),
        max_tool_calls=1,
        max_mutation_tool_calls=0,
    )

    assert agent.max_total_tool_calls == 1
    assert agent.max_mutation_tool_calls == 0


def test_result_tool_records_are_ordered_and_final_summary_matches_storage() -> None:
    agent, service, _tools = _agent(
        ScriptedModel(
            {
                "tool_calls": [
                    _tool("set_department", department="정보컴퓨터공학부"),
                    _tool("add_preferred_course", course_id="C003"),
                    _tool("add_disliked_course", course_id="C004"),
                ]
            },
            {"message": "학과와 과목 선호를 반영했습니다."},
        )
    )
    session_id = _create_session(service)

    result = _run(agent, session_id, "정보컴퓨터공학부야. 가능하면 C003, C004는 피해줘.")
    stored = service.get_session(session_id)

    assert result.success is True
    assert result.changed is True
    assert [item.name for item in result.executed_tools] == [
        "get_session_summary",
        "set_department",
        "add_preferred_course",
        "add_disliked_course",
        "get_session_summary",
    ]
    assert result.state_summary is not None
    assert result.state_summary.department == stored.department
    assert result.state_summary.soft_preferences == stored.soft_preferences


def test_discovery_tools_are_registered_with_single_agent_toolset() -> None:
    agent, service, tools, _catalogs = _agent_with_discovery(
        ScriptedModel({"message": "확인했습니다.", "tool_calls": []})
    )
    session_id = _create_session(service)

    specs = {spec.name for spec in tools.specs()}
    result = _run(agent, session_id, "현재 상태만 보여줘")

    assert result.success is True
    assert {
        "get_session_summary",
        "update_timetable_preferences",
        "search_courses_by_name",
        "discover_courses",
        "get_course_sections",
        "get_section_details",
    } <= specs
    assert len(specs) == len(tools.specs())
    assert [name for name, _args in tools.calls] == [
        "get_session_summary",
        "get_session_summary",
    ]


def test_timetable_generation_tools_are_registered_with_single_agent_toolset() -> None:
    agent, service, tools, _catalogs = _agent_with_discovery(
        ScriptedModel({"message": "확인했습니다.", "tool_calls": []})
    )
    session_id = _create_session(service)

    specs = {spec.name for spec in tools.specs()}
    result = _run(agent, session_id, "현재 조건을 보여줘")

    assert result.success is True
    assert {
        "generate_timetable_candidates",
        "validate_timetable_candidate",
        "score_timetable_candidate",
        "rank_timetable_candidates",
    } <= specs
    assert len(specs) == len(tools.specs())


def test_generation_tool_result_is_returned_without_saving_to_session() -> None:
    agent, service, tools, _catalogs = _agent_with_discovery(
        ScriptedModel(
            {
                "tool_calls": [
                    _tool(
                        "generate_timetable_candidates",
                        fixed_section_sources=[
                            {"catalog_id": "major-1", "section_id": "MAJ101-001"}
                        ],
                        candidate_course_ids=["GEN101"],
                        candidate_section_sources_by_course={
                            "GEN101": [
                                {"catalog_id": "elective-1", "section_id": "GEN101-001"}
                            ]
                        },
                        required_free_days=["FRI"],
                        department="정보컴퓨터공학부",
                        target_additional_course_count=1,
                        max_results=3,
                        max_search_nodes=100,
                    )
                ]
            },
            {"message": "현재 조건에서 시간표 후보 1개를 찾았습니다.", "tool_calls": []},
        )
    )
    session_id = _create_session(service)
    SessionAgentTools(service).update_session_profile(
        {
            "session_id": session_id,
            "department": "정보컴퓨터공학부",
            "major_catalog_id": "major-1",
            "elective_catalog_id": "elective-1",
        }
    )

    service.replace_selected_major_courses(session_id, ["MAJ101-001"])

    result = _run(agent, session_id, "금요일 비우고 교양 한 과목 추가한 시간표를 만들어줘")

    assert result.success is True
    assert result.changed is False
    assert result.generation_summary is not None
    assert result.generation_summary.generated_candidate_count == 1
    assert result.generation_summary.applied_hard_constraints["required_free_days"] == ["FRI"]
    assert result.timetable_candidates[0].fixed_section_ids == ["MAJ101-001"]
    assert result.timetable_candidates[0].added_section_ids == ["GEN101-001"]
    assert result.timetable_candidates[0].valid is True
    assert service.get_session(session_id).selected_major_course_ids == ["MAJ101-001"]
    assert [name for name, _args in tools.calls] == [
        "get_session_summary",
        "generate_timetable_candidates",
        "get_session_summary",
    ]


def test_generation_then_ranking_result_is_returned_without_auto_selecting_top_candidate() -> None:
    candidates = [
        _candidate_json("candidate-free-fri", "GEN101-001", "GEN101"),
        _candidate_json("candidate-friday-class", "GEN103-001", "GEN103"),
    ]
    sections = [
        _section_json(
            "major-1",
            "MAJ101-001",
            "MAJ101",
            "컴퓨터프로그래밍",
            day="MON",
        ),
        _section_json(
            "elective-1",
            "GEN101-001",
            "GEN101",
            "컴퓨터와사회",
            day="WED",
        ),
        _section_json(
            "elective-1",
            "GEN103-001",
            "GEN103",
            "금요일세미나",
            day="FRI",
        ),
    ]
    agent, service, tools, _catalogs = _agent_with_discovery(
        ScriptedModel(
            {
                "tool_calls": [
                    _tool(
                        "generate_timetable_candidates",
                        fixed_section_sources=[
                            {"catalog_id": "major-1", "section_id": "MAJ101-001"}
                        ],
                        candidate_course_ids=["GEN101", "GEN103"],
                        candidate_section_sources_by_course={
                            "GEN101": [
                                {"catalog_id": "elective-1", "section_id": "GEN101-001"}
                            ],
                            "GEN103": [
                                {"catalog_id": "elective-1", "section_id": "GEN103-001"}
                            ],
                        },
                        department="정보컴퓨터공학부",
                        target_additional_course_count=1,
                        max_results=3,
                        max_search_nodes=100,
                    )
                ]
            },
            {
                "tool_calls": [
                    _tool(
                        "rank_timetable_candidates",
                        candidates=candidates,
                        sections=sections,
                        max_ranked_results=1,
                    )
                ]
            },
            {"message": "유효한 후보 2개 중 선호 기준 상위 1개를 보여드립니다.", "tool_calls": []},
        )
    )
    session_id = _create_session(service)
    SessionAgentTools(service).update_session_profile(
        {
            "session_id": session_id,
            "department": "정보컴퓨터공학부",
            "major_catalog_id": "major-1",
            "elective_catalog_id": "elective-1",
        }
    )
    SessionAgentTools(service).update_timetable_preferences(
        {
            "session_id": session_id,
            "soft": {"preferred_free_days": ["FRI"]},
        }
    )
    service.replace_selected_major_courses(session_id, ["MAJ101-001"])

    result = _run(agent, session_id, "금요일 공강 선호 기준으로 시간표 하나만 추천해줘")

    assert result.success is True
    assert result.ranking_applied is True
    assert result.ranking_summary is not None
    assert result.ranking_summary.evaluated_candidate_count == 2
    assert result.ranking_summary.returned_candidate_count == 1
    assert result.ranking_summary.soft_preferences_present is True
    assert result.effective_soft_preferences == {
        "preferred_free_days": ["FRI"],
        "preferred_earliest_start_time": None,
        "preferred_latest_end_time": None,
        "preferred_course_ids": [],
        "disliked_course_ids": [],
        "compact_schedule": None,
    }
    assert [candidate.candidate_id for candidate in result.ranked_timetable_candidates] == [
        "candidate-free-fri"
    ]
    top = result.ranked_timetable_candidates[0]
    assert top.rank == 1
    assert top.comparison_score > 0
    assert top.sections[1].course_name == "컴퓨터와사회"
    assert top.satisfied_preferences[0].code == "FREE_DAY_PREFERENCE_SATISFIED"
    assert service.get_session(session_id).selected_major_course_ids == ["MAJ101-001"]
    assert tools.calls[2][1]["soft_preferences"]["preferred_free_days"] == ["FRI"]
    assert [name for name, _args in tools.calls] == [
        "get_session_summary",
        "generate_timetable_candidates",
        "rank_timetable_candidates",
        "get_session_summary",
    ]


def test_ranking_failure_keeps_generated_candidates_and_reports_ranking_error() -> None:
    candidates = [_candidate_json("candidate-missing-section", "GEN101-001", "GEN101")]
    agent, service, tools, _catalogs = _agent_with_discovery(
        ScriptedModel(
            {
                "tool_calls": [
                    _tool(
                        "generate_timetable_candidates",
                        fixed_section_sources=[
                            {"catalog_id": "major-1", "section_id": "MAJ101-001"}
                        ],
                        candidate_course_ids=["GEN101"],
                        candidate_section_sources_by_course={
                            "GEN101": [
                                {"catalog_id": "elective-1", "section_id": "GEN101-001"}
                            ]
                        },
                        department="정보컴퓨터공학부",
                        target_additional_course_count=1,
                        max_results=3,
                        max_search_nodes=100,
                    )
                ]
            },
            {
                "tool_calls": [
                    _tool(
                        "rank_timetable_candidates",
                        candidates=candidates,
                        sections=[],
                        soft_preferences={"preferred_free_days": ["FRI"]},
                        max_ranked_results=3,
                    )
                ]
            },
            {"message": "ranking 실패를 확인했습니다.", "tool_calls": []},
        )
    )
    session_id = _create_session(service)

    result = _run(agent, session_id, "시간표 추천해줘")

    assert result.success is False
    assert result.timetable_candidates
    assert result.ranking_applied is False
    assert result.ranking_error is not None
    assert result.ranking_error.code == "SECTION_DETAILS_MISSING"
    assert result.ranked_timetable_candidates == []
    assert [name for name, _args in tools.calls] == [
        "get_session_summary",
        "generate_timetable_candidates",
        "rank_timetable_candidates",
        "get_session_summary",
    ]

def test_generation_failure_reasons_are_capped_and_user_facing() -> None:
    agent, service, tools, _catalogs = _agent_with_discovery(
        ScriptedModel(
            {
                "tool_calls": [
                    _tool(
                        "generate_timetable_candidates",
                        fixed_section_sources=[
                            {"catalog_id": "major-1", "section_id": "MAJ101-001"}
                        ],
                        candidate_course_ids=["GEN101"],
                        candidate_section_sources_by_course={
                            "GEN101": [
                                {"catalog_id": "elective-1", "section_id": "GEN101-001"}
                            ]
                        },
                        required_free_days=["WED"],
                        department="정보컴퓨터공학부",
                        target_additional_course_count=1,
                        max_results=3,
                        max_search_nodes=100,
                    )
                ]
            },
            {"message": "조건을 만족하는 시간표 후보를 만들지 못했습니다.", "tool_calls": []},
        )
    )
    session_id = _create_session(service)

    result = _run(agent, session_id, "수요일 공강으로 시간표 후보를 만들어줘")

    assert result.success is True
    assert result.timetable_candidates == []
    assert result.generation_failure_reasons
    assert {
        reason.code for reason in result.generation_failure_reasons
    } <= {"REQUIRED_FREE_DAY_VIOLATION", "TARGET_COURSE_COUNT_UNREACHABLE"}
    assert "자동 완화" not in result.message
    assert "generate_timetable_candidates" in [name for name, _args in tools.calls]


def test_validation_tool_result_is_returned_for_explicit_section_check() -> None:
    agent, service, tools, _catalogs = _agent_with_discovery(
        ScriptedModel(
            {
                "tool_calls": [
                    _tool(
                        "validate_timetable_candidate",
                        section_sources=[
                            {"catalog_id": "major-1", "section_id": "MAJ101-001"},
                            {"catalog_id": "elective-1", "section_id": "GEN102-001"},
                        ],
                    )
                ]
            },
            {"message": "section 조합을 검증했습니다.", "tool_calls": []},
        )
    )
    session_id = _create_session(service)

    result = _run(agent, session_id, "이 section 조합을 검증해줘")

    assert result.success is True
    assert result.validation_results[0].valid is False
    assert "TIME_CONFLICT" in result.validation_results[0].violation_codes
    assert "generate_timetable_candidates" not in [name for name, _args in tools.calls]


def test_preparation_service_builds_generation_request_from_discovery_candidates() -> None:
    agent, service, tools, _catalogs = _agent_with_discovery(
        ScriptedModel(
            {
                "tool_calls": [
                    _tool(
                        "discover_courses",
                        catalog_id="elective-1",
                        category="GENERAL_ELECTIVE",
                        excluded_days=["FRI"],
                        limit=3,
                    )
                ]
            },
            {"message": "후보를 찾았습니다.", "tool_calls": []},
        )
    )
    session_id = _create_session(service)
    SessionAgentTools(service).update_session_profile(
        {
            "session_id": session_id,
            "department": "정보컴퓨터공학부",
            "major_catalog_id": "major-1",
            "elective_catalog_id": "elective-1",
        }
    )
    service.replace_selected_major_courses(session_id, ["MAJ101-001"])

    result = _run(agent, session_id, "금요일 없는 교양 후보를 찾아줘")
    assert result.state_summary is not None
    discovery = tools.results[1]
    prepared = TimetablePreparationService().prepare(
        result.state_summary,
        TimetablePreparationOptions(
            candidate_catalog_id="elective-1",
            discovered_candidates=discovery.candidates,
            target_additional_course_count=1,
        ),
    )

    assert prepared.ready is True
    assert prepared.request is not None
    assert prepared.request.fixed_section_sources[0].section_id == "MAJ101-001"
    assert "GEN103" not in prepared.request.candidate_section_sources_by_course
    assert len(prepared.request.candidate_section_sources_by_course) == 3
    assert all(
        source.catalog_id == "elective-1"
        for sources in prepared.request.candidate_section_sources_by_course.values()
        for source in sources
    )


def test_preparation_service_requires_major_section_when_only_course_id_is_selected() -> None:
    agent, service, _tools, _catalogs = _agent_with_discovery(
        ScriptedModel({"message": "확인했습니다.", "tool_calls": []})
    )
    session_id = _create_session(service)
    SessionAgentTools(service).update_session_profile(
        {
            "session_id": session_id,
            "department": "정보컴퓨터공학부",
            "major_catalog_id": "major-1",
            "elective_catalog_id": "elective-1",
        }
    )
    service.replace_selected_major_courses(session_id, ["MAJ101"])

    result = _run(agent, session_id, "현재 조건을 보여줘")
    assert result.state_summary is not None
    prepared = TimetablePreparationService().prepare(
        result.state_summary,
        TimetablePreparationOptions(
            candidate_catalog_id="elective-1",
            discovered_candidates=[],
            target_additional_course_count=1,
        ),
    )

    assert prepared.ready is False
    assert TimetablePreparationIssueCode.MAJOR_SECTION_UNCONFIRMED in {
        issue.code for issue in prepared.issues
    }


def test_explicit_major_course_search_returns_candidate_without_state_change() -> None:
    agent, service, tools, _catalogs = _agent_with_discovery(
        ScriptedModel(
            {
                "tool_calls": [
                    _tool(
                        "search_courses_by_name",
                        catalog_id="major-1",
                        query="컴퓨터프로그래밍",
                    )
                ]
            },
            {"message": "컴퓨터프로그래밍 후보를 찾았습니다.", "tool_calls": []},
        )
    )
    session_id = _create_session(service)
    SessionAgentTools(service).update_session_profile(
        {
            "session_id": session_id,
            "major_catalog_id": "major-1",
            "elective_catalog_id": "elective-1",
        }
    )

    result = _run(agent, session_id, "컴퓨터프로그래밍을 찾아줘")

    assert result.success is True
    assert result.changed is False
    assert result.discovery_results[0].tool_name == "search_courses_by_name"
    assert result.discovery_results[0].catalog_id == "major-1"
    assert result.discovery_results[0].resolution == "EXACT"
    assert result.candidate_courses[0].course_id == "MAJ101"
    assert result.candidate_courses[0].matching_section_count == 2
    assert [name for name, _args in tools.calls] == [
        "get_session_summary",
        "search_courses_by_name",
        "get_session_summary",
    ]


def test_exact_search_can_feed_required_course_update_after_resolution() -> None:
    agent, service, tools, _catalogs = _agent_with_discovery(
        ScriptedModel(
            {
                "tool_calls": [
                    _tool(
                        "search_courses_by_name",
                        catalog_id="major-1",
                        query="자료구조",
                    )
                ]
            },
            {
                "tool_calls": [
                    _tool(
                        "update_timetable_preferences",
                        hard={"required_course_ids": ["MAJ201"]},
                    )
                ]
            },
            {"message": "자료구조를 반드시 포함하도록 반영했습니다.", "tool_calls": []},
        )
    )
    session_id = _create_session(service)
    SessionAgentTools(service).update_session_profile(
        {"session_id": session_id, "major_catalog_id": "major-1"}
    )

    result = _run(agent, session_id, "자료구조를 반드시 넣어줘")

    assert result.success is True
    assert result.changed is True
    assert result.state_summary is not None
    assert result.state_summary.hard_constraints.required_course_ids == ["MAJ201"]
    assert [name for name, _args in tools.calls] == [
        "get_session_summary",
        "search_courses_by_name",
        "update_timetable_preferences",
        "get_session_summary",
    ]


def test_ambiguous_search_sets_confirmation_without_selecting_first_candidate() -> None:
    agent, service, tools, _catalogs = _agent_with_discovery(
        ScriptedModel(
            {
                "tool_calls": [
                    _tool(
                        "search_courses_by_name",
                        catalog_id="elective-1",
                        query="대학수학",
                    )
                ]
            },
            {"message": "대학수학과 일치하는 후보가 여러 개입니다.", "tool_calls": []},
        )
    )
    session_id = _create_session(service)
    SessionAgentTools(service).update_session_profile(
        {"session_id": session_id, "elective_catalog_id": "elective-1"}
    )

    result = _run(agent, session_id, "대학수학을 반드시 넣어줘")

    assert result.success is True
    assert result.changed is False
    assert result.needs_confirmation is True
    assert result.confirmation_request is not None
    assert {item.course_code for item in result.confirmation_request.candidates} == {
        "GEN201",
        "GEN202",
    }
    assert "update_timetable_preferences" not in [name for name, _args in tools.calls]


def test_condition_discovery_uses_structured_filters_and_candidate_summary() -> None:
    agent, service, tools, _catalogs = _agent_with_discovery(
        ScriptedModel(
            {
                "tool_calls": [
                    _tool(
                        "discover_courses",
                        catalog_id="elective-1",
                        category="GENERAL_ELECTIVE",
                        area=3,
                        excluded_days=["FRI"],
                        earliest_start_time="10:00",
                        limit=3,
                    )
                ]
            },
            {
                "message": "교양 3영역이며 금요일 수업이 없고 10시 이후 시작하는 후보를 찾았습니다.",
                "tool_calls": [],
            },
        )
    )
    session_id = _create_session(service)
    SessionAgentTools(service).update_session_profile(
        {"session_id": session_id, "elective_catalog_id": "elective-1"}
    )

    result = _run(agent, session_id, "금요일 없는 3영역 교양 후보를 보여줘")

    assert result.success is True
    assert result.changed is False
    assert result.discovery_results[0].resolution == "CANDIDATES"
    assert {candidate.course_id for candidate in result.candidate_courses} == {
        "GEN101",
        "GEN102",
    }
    assert all("GEN103" not in candidate.matching_section_ids for candidate in result.candidate_courses)
    assert all(candidate.matching_section_count >= 1 for candidate in result.candidate_courses)
    discover_args = tools.calls[1][1]
    assert "query" not in discover_args
    assert discover_args["excluded_days"] == ["FRI"]
    assert discover_args["earliest_start_time"] == "10:00"
    assert "get_course_sections" not in [name for name, _args in tools.calls]


def test_state_change_then_discovery_uses_updated_hard_constraints_in_order() -> None:
    agent, service, tools, _catalogs = _agent_with_discovery(
        ScriptedModel(
            {
                "tool_calls": [
                    _tool(
                        "update_timetable_preferences",
                        hard={"required_free_days": ["FRI"]},
                    )
                ]
            },
            {"tool_calls": [_tool("get_session_summary")]},
            {
                "tool_calls": [
                    _tool(
                        "discover_courses",
                        catalog_id="elective-1",
                        category="GENERAL_ELECTIVE",
                        excluded_days=["FRI"],
                        limit=3,
                    )
                ]
            },
            {"message": "금요일을 비우는 조건을 반영하고 후보를 찾았습니다.", "tool_calls": []},
        )
    )
    session_id = _create_session(service)
    SessionAgentTools(service).update_session_profile(
        {"session_id": session_id, "elective_catalog_id": "elective-1"}
    )

    result = _run(agent, session_id, "금요일은 반드시 비우고 들을 수 있는 교양 후보를 찾아줘")

    assert result.success is True
    assert result.changed is True
    assert result.state_summary is not None
    assert result.state_summary.hard_constraints.required_free_days == [Day.FRI]
    assert [name for name, _args in tools.calls] == [
        "get_session_summary",
        "update_timetable_preferences",
        "get_session_summary",
        "discover_courses",
        "get_session_summary",
    ]
    assert tools.calls[3][1]["excluded_days"] == ["FRI"]


def test_soft_preferences_are_not_sent_as_hard_discovery_filters() -> None:
    agent, service, tools, _catalogs = _agent_with_discovery(
        ScriptedModel(
            {
                "tool_calls": [
                    _tool(
                        "update_timetable_preferences",
                        soft={"preferred_free_days": ["FRI"]},
                    )
                ]
            },
            {"tool_calls": [_tool("get_session_summary")]},
            {
                "tool_calls": [
                    _tool(
                        "discover_courses",
                        catalog_id="elective-1",
                        category="GENERAL_ELECTIVE",
                        limit=3,
                    )
                ]
            },
            {"message": "선호를 반영하고 후보를 찾았습니다.", "tool_calls": []},
        )
    )
    session_id = _create_session(service)
    SessionAgentTools(service).update_session_profile(
        {"session_id": session_id, "elective_catalog_id": "elective-1"}
    )

    result = _run(agent, session_id, "가능하면 금요일 공강이 좋고 교양 후보를 보여줘")

    assert result.success is True
    assert result.state_summary is not None
    assert result.state_summary.soft_preferences.preferred_free_days == [Day.FRI]
    assert "excluded_days" not in tools.calls[3][1]


def test_catalog_missing_request_stays_unresolved_without_discovery_call() -> None:
    agent, service, tools, _catalogs = _agent_with_discovery(
        ScriptedModel(
            {
                "message": "전공 수강편람 등록이 필요합니다.",
                "unresolved_requests": [
                    {
                        "source_text": "전공 과목 검색",
                        "reason": "major_catalog_id가 세션에 없습니다.",
                        "needed_information": "전공 수강편람 catalog_id",
                        "requires_user_confirmation": True,
                    }
                ],
            }
        )
    )
    session_id = _create_session(service)

    result = _run(agent, session_id, "전공 과목 후보를 찾아줘")

    assert result.success is True
    assert result.needs_confirmation is True
    assert result.discovery_results == []
    assert [name for name, _args in tools.calls] == [
        "get_session_summary",
        "get_session_summary",
    ]


def test_sections_and_section_details_are_called_only_when_requested() -> None:
    agent, service, tools, _catalogs = _agent_with_discovery(
        ScriptedModel(
            {
                "tool_calls": [
                    _tool(
                        "get_course_sections",
                        catalog_id="major-1",
                        course_id="MAJ101",
                    ),
                    _tool(
                        "get_section_details",
                        catalog_id="major-1",
                        section_id="MAJ101-001",
                    ),
                ]
            },
            {"message": "분반 상세를 확인했습니다.", "tool_calls": []},
        )
    )
    session_id = _create_session(service)
    SessionAgentTools(service).update_session_profile(
        {"session_id": session_id, "major_catalog_id": "major-1"}
    )

    result = _run(agent, session_id, "MAJ101 분반과 MAJ101-001 상세를 보여줘")

    assert result.success is True
    assert [name for name, _args in tools.calls] == [
        "get_session_summary",
        "get_course_sections",
        "get_section_details",
        "get_session_summary",
    ]
