"""Single-agent execution loop for PlaNU session-state management."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Mapping
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from ..agent_tools import (
    BoolPreferenceInput,
    CatalogInput,
    CourseIdInput,
    CourseIdsInput,
    DepartmentInput,
    DayInput,
    DaysInput,
    SessionIdInput,
    SessionStateSummary,
    SessionToolError,
    SessionToolResult,
    TimeInput,
)

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_PATH = Path(__file__).with_name("prompts") / "session_state_agent_system.txt"
DEFAULT_MAX_TOOL_CALLS = 10


class SessionStateAgentErrorCode(str, Enum):
    """Stable error codes returned by the session-state agent."""

    INVALID_INPUT = "INVALID_INPUT"
    SESSION_NOT_AVAILABLE = "SESSION_NOT_AVAILABLE"
    TOOL_ERROR = "TOOL_ERROR"
    MODEL_CALL_FAILED = "MODEL_CALL_FAILED"
    UNKNOWN_TOOL = "UNKNOWN_TOOL"
    INVALID_TOOL_ARGUMENTS = "INVALID_TOOL_ARGUMENTS"
    TOOL_CALL_LIMIT_EXCEEDED = "TOOL_CALL_LIMIT_EXCEEDED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class SessionStateAgentError(BaseModel):
    """Structured error for failures of the agent execution itself."""

    model_config = ConfigDict(extra="forbid")

    code: SessionStateAgentErrorCode
    message: str = Field(min_length=1)
    tool_name: str | None = None
    field: str | None = None
    value: str | None = None


class SessionStateAgentInput(BaseModel):
    """Input for one PlaNU session-state agent run."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    session_id: str = Field(min_length=1)
    user_message: str = Field(min_length=1)
    request_id: str | None = Field(default=None, min_length=1)
    locale: str | None = Field(default=None, min_length=1)

    @field_validator("session_id", "user_message")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be empty")
        return value


class ExecutedSessionTool(BaseModel):
    """Safe summary of one tool execution."""

    model_config = ConfigDict(extra="forbid")

    name: str
    success: bool
    changed: bool = False
    error_code: str | None = None


class UnresolvedSessionRequest(BaseModel):
    """A user request the current session-state tools cannot safely apply."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    source_text: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    needed_information: str | None = None
    requires_user_confirmation: bool = False


class SessionStateAgentResult(BaseModel):
    """Final structured result of a session-state agent run."""

    model_config = ConfigDict(extra="forbid")

    success: bool
    session_id: str | None = None
    message: str
    changed: bool = False
    state_summary: SessionStateSummary | None = None
    executed_tools: list[ExecutedSessionTool] = Field(default_factory=list)
    unresolved_requests: list[UnresolvedSessionRequest] = Field(default_factory=list)
    error: SessionStateAgentError | None = None


class SessionStateToolCall(BaseModel):
    """Tool call requested by the injected model."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)


class SessionStateModelResponse(BaseModel):
    """Normalized response from a tool-calling model."""

    model_config = ConfigDict(extra="forbid")

    tool_calls: list[SessionStateToolCall] = Field(default_factory=list)
    message: str | None = None
    unresolved_requests: list[UnresolvedSessionRequest] = Field(default_factory=list)


class SessionStateToolSpec(BaseModel):
    """Description passed to native or fake tool-calling models."""

    model_config = ConfigDict(extra="forbid")

    name: str
    description: str
    parameters: dict[str, Any]


class SessionStateToolset:
    """Registry of the session-state tools available to the agent."""

    def __init__(self, tools: Mapping[str, Callable[[Mapping[str, object]], SessionToolResult]]) -> None:
        self._tools = dict(tools)

    @classmethod
    def from_query_and_command_tools(cls, queries: object, commands: object) -> "SessionStateToolset":
        return cls(
            {
                "get_session_summary": queries.get_session_summary,
                "set_department": commands.set_department,
                "register_major_catalog": commands.register_major_catalog,
                "register_elective_catalog": commands.register_elective_catalog,
                "add_selected_major_course": commands.add_selected_major_course,
                "remove_selected_major_course": commands.remove_selected_major_course,
                "replace_selected_major_courses": commands.replace_selected_major_courses,
                "add_required_free_day": commands.add_required_free_day,
                "remove_required_free_day": commands.remove_required_free_day,
                "replace_required_free_days": commands.replace_required_free_days,
                "set_earliest_start_time": commands.set_earliest_start_time,
                "clear_earliest_start_time": commands.clear_earliest_start_time,
                "set_latest_end_time": commands.set_latest_end_time,
                "clear_latest_end_time": commands.clear_latest_end_time,
                "add_required_course": commands.add_required_course,
                "remove_required_course": commands.remove_required_course,
                "add_excluded_course": commands.add_excluded_course,
                "remove_excluded_course": commands.remove_excluded_course,
                "clear_hard_constraints": commands.clear_hard_constraints,
                "add_preferred_free_day": commands.add_preferred_free_day,
                "remove_preferred_free_day": commands.remove_preferred_free_day,
                "replace_preferred_free_days": commands.replace_preferred_free_days,
                "set_preferred_earliest_start_time": commands.set_preferred_earliest_start_time,
                "clear_preferred_earliest_start_time": commands.clear_preferred_earliest_start_time,
                "set_preferred_latest_end_time": commands.set_preferred_latest_end_time,
                "clear_preferred_latest_end_time": commands.clear_preferred_latest_end_time,
                "add_preferred_course": commands.add_preferred_course,
                "remove_preferred_course": commands.remove_preferred_course,
                "add_disliked_course": commands.add_disliked_course,
                "remove_disliked_course": commands.remove_disliked_course,
                "set_compact_schedule_preference": commands.set_compact_schedule_preference,
                "clear_compact_schedule_preference": commands.clear_compact_schedule_preference,
                "clear_soft_preferences": commands.clear_soft_preferences,
                "clear_all_preferences": commands.clear_all_preferences,
            }
        )

    def has_tool(self, name: str) -> bool:
        return name in self._tools

    def run(self, name: str, arguments: Mapping[str, object]) -> SessionToolResult:
        return self._tools[name](arguments)

    def specs(self) -> list[SessionStateToolSpec]:
        return [
            SessionStateToolSpec(
                name=name,
                description=_TOOL_DESCRIPTIONS[name],
                parameters=_TOOL_INPUT_MODELS[name].model_json_schema(),
            )
            for name in self._tools
        ]


_TOOL_INPUT_MODELS: dict[str, type[BaseModel]] = {
    "get_session_summary": SessionIdInput,
    "set_department": DepartmentInput,
    "register_major_catalog": CatalogInput,
    "register_elective_catalog": CatalogInput,
    "add_selected_major_course": CourseIdInput,
    "remove_selected_major_course": CourseIdInput,
    "replace_selected_major_courses": CourseIdsInput,
    "add_required_free_day": DayInput,
    "remove_required_free_day": DayInput,
    "replace_required_free_days": DaysInput,
    "set_earliest_start_time": TimeInput,
    "clear_earliest_start_time": SessionIdInput,
    "set_latest_end_time": TimeInput,
    "clear_latest_end_time": SessionIdInput,
    "add_required_course": CourseIdInput,
    "remove_required_course": CourseIdInput,
    "add_excluded_course": CourseIdInput,
    "remove_excluded_course": CourseIdInput,
    "clear_hard_constraints": SessionIdInput,
    "add_preferred_free_day": DayInput,
    "remove_preferred_free_day": DayInput,
    "replace_preferred_free_days": DaysInput,
    "set_preferred_earliest_start_time": TimeInput,
    "clear_preferred_earliest_start_time": SessionIdInput,
    "set_preferred_latest_end_time": TimeInput,
    "clear_preferred_latest_end_time": SessionIdInput,
    "add_preferred_course": CourseIdInput,
    "remove_preferred_course": CourseIdInput,
    "add_disliked_course": CourseIdInput,
    "remove_disliked_course": CourseIdInput,
    "set_compact_schedule_preference": BoolPreferenceInput,
    "clear_compact_schedule_preference": SessionIdInput,
    "clear_soft_preferences": SessionIdInput,
    "clear_all_preferences": SessionIdInput,
}

_TOOL_DESCRIPTIONS: dict[str, str] = {
    "get_session_summary": "Fetch the compact current session state. Required before and after mutations.",
    "set_department": "Set the user's department when the department text is explicit.",
    "register_major_catalog": "Store an already parsed major catalog id.",
    "register_elective_catalog": "Store an already parsed elective catalog id.",
    "add_selected_major_course": "Add one resolved selected major course id.",
    "remove_selected_major_course": "Remove one resolved selected major course id.",
    "replace_selected_major_courses": "Replace selected major course ids with resolved ids.",
    "add_required_free_day": "Add a Hard required free weekday.",
    "remove_required_free_day": "Remove a Hard required free weekday.",
    "replace_required_free_days": "Replace all Hard required free weekdays.",
    "set_earliest_start_time": "Set the Hard earliest allowed class start time.",
    "clear_earliest_start_time": "Clear the Hard earliest-start constraint.",
    "set_latest_end_time": "Set the Hard latest allowed class end time.",
    "clear_latest_end_time": "Clear the Hard latest-end constraint.",
    "add_required_course": "Add one resolved course id as a Hard required course.",
    "remove_required_course": "Remove one Hard required course id.",
    "add_excluded_course": "Add one resolved course id as a Hard excluded course.",
    "remove_excluded_course": "Remove one Hard excluded course id.",
    "clear_hard_constraints": "Clear all Hard constraints only.",
    "add_preferred_free_day": "Add a Soft preferred free weekday.",
    "remove_preferred_free_day": "Remove a Soft preferred free weekday.",
    "replace_preferred_free_days": "Replace all Soft preferred free weekdays.",
    "set_preferred_earliest_start_time": "Set the Soft preferred earliest class start time.",
    "clear_preferred_earliest_start_time": "Clear the Soft preferred earliest-start time.",
    "set_preferred_latest_end_time": "Set the Soft preferred latest class end time.",
    "clear_preferred_latest_end_time": "Clear the Soft preferred latest-end time.",
    "add_preferred_course": "Add one resolved course id as a Soft preferred course.",
    "remove_preferred_course": "Remove one Soft preferred course id.",
    "add_disliked_course": "Add one resolved course id as a Soft disliked course.",
    "remove_disliked_course": "Remove one Soft disliked course id.",
    "set_compact_schedule_preference": "Set whether compact schedules are softly preferred.",
    "clear_compact_schedule_preference": "Clear compact-schedule Soft preference.",
    "clear_soft_preferences": "Clear all Soft preferences only.",
    "clear_all_preferences": "Clear both Hard constraints and Soft preferences.",
}


class SessionStateAgent:
    """Run one tool-calling session-state agent turn."""

    def __init__(
        self,
        *,
        model: Any,
        tools: SessionStateToolset,
        max_tool_calls: int = DEFAULT_MAX_TOOL_CALLS,
        system_prompt: str | None = None,
    ) -> None:
        if max_tool_calls <= 0:
            raise ValueError("max_tool_calls must be positive")
        self.model = model
        self.tools = tools
        self.max_tool_calls = max_tool_calls
        self.system_prompt = system_prompt or load_session_state_agent_prompt()

    def run(self, data: SessionStateAgentInput | Mapping[str, object]) -> SessionStateAgentResult:
        try:
            request = SessionStateAgentInput.model_validate(data)
        except ValidationError as exc:
            return self._input_error(exc)

        executed: list[ExecutedSessionTool] = []
        transcript: list[dict[str, Any]] = []
        unresolved_requests: list[UnresolvedSessionRequest] = []
        changed = False
        last_summary: SessionStateSummary | None = None

        initial = self._execute_tool(
            "get_session_summary",
            {"session_id": request.session_id},
            executed,
        )
        if initial.result is None:
            return self._limit_error(request, executed, last_summary)
        if not initial.result.success:
            return self._session_error(request, initial.result, executed)
        last_summary = initial.result.state_summary
        transcript.append(self._tool_transcript("get_session_summary", initial.result))

        while True:
            try:
                model_response = self._call_model(request, transcript, last_summary)
            except Exception:
                logger.exception(
                    "session_state_agent_model_failed",
                    extra={"session_id": request.session_id, "tool_call_count": len(executed)},
                )
                return self._failure(
                    request,
                    "요청을 해석하는 중 오류가 발생했습니다.",
                    SessionStateAgentErrorCode.MODEL_CALL_FAILED,
                    executed,
                    last_summary,
                    changed,
                )

            unresolved_requests.extend(model_response.unresolved_requests)
            if not model_response.tool_calls:
                final = self._execute_tool(
                    "get_session_summary",
                    {"session_id": request.session_id},
                    executed,
                )
                if final.result is None:
                    return self._limit_error(request, executed, last_summary)
                if not final.result.success:
                    return self._tool_failure(request, final.result, executed, last_summary, changed)
                message = model_response.message or self._default_message(
                    changed,
                    unresolved_requests,
                )
                return SessionStateAgentResult(
                    success=True,
                    session_id=request.session_id,
                    message=message,
                    changed=changed,
                    state_summary=final.result.state_summary,
                    executed_tools=executed,
                    unresolved_requests=unresolved_requests,
                    error=None,
                )

            for tool_call in model_response.tool_calls:
                if not self.tools.has_tool(tool_call.name):
                    logger.warning(
                        "session_state_agent_unknown_tool",
                        extra={"session_id": request.session_id, "tool_name": tool_call.name},
                    )
                    return self._failure(
                        request,
                        f"모델이 등록되지 않은 도구를 요청했습니다: {tool_call.name}",
                        SessionStateAgentErrorCode.UNKNOWN_TOOL,
                        executed,
                        last_summary,
                        changed,
                        tool_name=tool_call.name,
                    )

                arguments = {**tool_call.arguments}
                arguments.setdefault("session_id", request.session_id)
                validation_error = self._validate_tool_arguments(tool_call.name, arguments)
                if validation_error is not None:
                    return self._invalid_tool_arguments(
                        request,
                        tool_call.name,
                        validation_error,
                        executed,
                        last_summary,
                        changed,
                    )

                result = self._execute_tool(tool_call.name, arguments, executed)
                if result.result is None:
                    return self._limit_error(request, executed, last_summary)
                changed = changed or result.result.changed
                if result.result.state_summary is not None:
                    last_summary = result.result.state_summary
                transcript.append(self._tool_transcript(tool_call.name, result.result))

    def _call_model(
        self,
        request: SessionStateAgentInput,
        transcript: list[dict[str, Any]],
        current_summary: SessionStateSummary | None,
    ) -> SessionStateModelResponse:
        payload = {
            "messages": [
                {"role": "system", "content": self.system_prompt},
                {
                    "role": "user",
                    "content": {
                        "session_id": request.session_id,
                        "locale": request.locale,
                        "user_message": request.user_message,
                        "current_state_summary": (
                            None
                            if current_summary is None
                            else current_summary.model_dump(mode="json")
                        ),
                    },
                },
                *transcript,
            ],
            "tools": [spec.model_dump(mode="json") for spec in self.tools.specs()],
        }
        if hasattr(self.model, "invoke"):
            try:
                raw = self.model.invoke(payload["messages"], tools=payload["tools"])
            except TypeError:
                raw = self.model.invoke(payload)
        elif callable(self.model):
            raw = self.model(payload)
        else:
            raise TypeError("configured model is not invokable")
        return self._normalize_model_response(raw)

    def _execute_tool(
        self,
        name: str,
        arguments: Mapping[str, object],
        executed: list[ExecutedSessionTool],
    ) -> "_ToolExecution":
        if len(executed) >= self.max_tool_calls:
            return _ToolExecution(result=None)
        result = self.tools.run(name, arguments)
        error_code = None if result.error is None else result.error.code.value
        executed.append(
            ExecutedSessionTool(
                name=name,
                success=result.success,
                changed=result.changed,
                error_code=error_code,
            )
        )
        logger.info(
            "session_state_agent_tool_executed",
            extra={
                "session_id": result.session_id,
                "tool_name": name,
                "success": result.success,
                "changed": result.changed,
                "error_code": error_code,
                "tool_call_count": len(executed),
            },
        )
        return _ToolExecution(result=result)

    @staticmethod
    def _normalize_model_response(raw: Any) -> SessionStateModelResponse:
        if isinstance(raw, SessionStateModelResponse):
            return raw
        if isinstance(raw, str):
            return SessionStateModelResponse.model_validate_json(raw)
        if isinstance(raw, Mapping):
            return SessionStateModelResponse.model_validate(raw)
        if hasattr(raw, "model_dump"):
            return SessionStateModelResponse.model_validate(raw.model_dump())
        tool_calls = getattr(raw, "tool_calls", None)
        content = getattr(raw, "content", None)
        if tool_calls is not None:
            normalized_calls = [
                {
                    "name": call.get("name") if isinstance(call, Mapping) else getattr(call, "name", ""),
                    "arguments": (
                        call.get("args", call.get("arguments", {}))
                        if isinstance(call, Mapping)
                        else getattr(call, "args", getattr(call, "arguments", {}))
                    ),
                }
                for call in tool_calls
            ]
            return SessionStateModelResponse(tool_calls=normalized_calls, message=content)
        raise TypeError(f"unsupported model response type: {type(raw).__name__}")

    @staticmethod
    def _validate_tool_arguments(name: str, arguments: Mapping[str, object]) -> ValidationError | None:
        try:
            _TOOL_INPUT_MODELS[name].model_validate(arguments)
        except ValidationError as exc:
            return exc
        return None

    @staticmethod
    def _tool_transcript(name: str, result: SessionToolResult) -> dict[str, Any]:
        return {
            "role": "tool",
            "name": name,
            "content": result.model_dump(mode="json", exclude_none=True),
        }

    @staticmethod
    def _default_message(changed: bool, unresolved: list[UnresolvedSessionRequest]) -> str:
        if changed:
            if unresolved:
                return "적용 가능한 조건을 세션에 반영했고, 일부 요청은 확인이 필요합니다."
            return "요청한 조건을 세션에 반영했습니다."
        if unresolved:
            return "현재 도구로 바로 적용할 수 없는 요청이 있어 확인이 필요합니다."
        return "세션 상태를 확인했습니다. 새로 변경된 조건은 없습니다."

    @staticmethod
    def _input_error(exc: ValidationError) -> SessionStateAgentResult:
        first = exc.errors()[0]
        field = ".".join(str(part) for part in first["loc"])
        return SessionStateAgentResult(
            success=False,
            session_id=None,
            message="입력값이 올바르지 않습니다.",
            error=SessionStateAgentError(
                code=SessionStateAgentErrorCode.INVALID_INPUT,
                message=str(first["msg"]),
                field=field,
            ),
        )

    @staticmethod
    def _session_error(
        request: SessionStateAgentInput,
        result: SessionToolResult,
        executed: list[ExecutedSessionTool],
    ) -> SessionStateAgentResult:
        error = _agent_error_from_tool_result(
            result,
            fallback_code=SessionStateAgentErrorCode.SESSION_NOT_AVAILABLE,
        )
        return SessionStateAgentResult(
            success=False,
            session_id=request.session_id,
            message="세션을 찾을 수 없거나 만료되었습니다.",
            executed_tools=executed,
            error=error,
        )

    @staticmethod
    def _tool_failure(
        request: SessionStateAgentInput,
        result: SessionToolResult,
        executed: list[ExecutedSessionTool],
        state_summary: SessionStateSummary | None,
        changed: bool,
    ) -> SessionStateAgentResult:
        return SessionStateAgentResult(
            success=False,
            session_id=request.session_id,
            message="최종 세션 상태를 확인하지 못했습니다.",
            changed=changed,
            state_summary=state_summary,
            executed_tools=executed,
            error=_agent_error_from_tool_result(
                result,
                fallback_code=SessionStateAgentErrorCode.TOOL_ERROR,
            ),
        )

    @staticmethod
    def _failure(
        request: SessionStateAgentInput,
        message: str,
        code: SessionStateAgentErrorCode,
        executed: list[ExecutedSessionTool],
        state_summary: SessionStateSummary | None,
        changed: bool,
        *,
        tool_name: str | None = None,
    ) -> SessionStateAgentResult:
        return SessionStateAgentResult(
            success=False,
            session_id=request.session_id,
            message=message,
            changed=changed,
            state_summary=state_summary,
            executed_tools=executed,
            error=SessionStateAgentError(
                code=code,
                message=message,
                tool_name=tool_name,
            ),
        )

    @staticmethod
    def _invalid_tool_arguments(
        request: SessionStateAgentInput,
        tool_name: str,
        exc: ValidationError,
        executed: list[ExecutedSessionTool],
        state_summary: SessionStateSummary | None,
        changed: bool,
    ) -> SessionStateAgentResult:
        first = exc.errors()[0]
        field = ".".join(str(part) for part in first["loc"])
        message = f"모델이 {tool_name} 도구에 올바르지 않은 인자를 생성했습니다."
        return SessionStateAgentResult(
            success=False,
            session_id=request.session_id,
            message=message,
            changed=changed,
            state_summary=state_summary,
            executed_tools=executed,
            error=SessionStateAgentError(
                code=SessionStateAgentErrorCode.INVALID_TOOL_ARGUMENTS,
                message=str(first["msg"]),
                tool_name=tool_name,
                field=field,
            ),
        )

    @staticmethod
    def _limit_error(
        request: SessionStateAgentInput,
        executed: list[ExecutedSessionTool],
        state_summary: SessionStateSummary | None,
    ) -> SessionStateAgentResult:
        changed = any(item.changed for item in executed)
        return SessionStateAgentResult(
            success=False,
            session_id=request.session_id,
            message="도구 호출 한도를 초과해 실행을 중단했습니다.",
            changed=changed,
            state_summary=state_summary,
            executed_tools=executed,
            error=SessionStateAgentError(
                code=SessionStateAgentErrorCode.TOOL_CALL_LIMIT_EXCEEDED,
                message="tool call limit exceeded",
            ),
        )


class _ToolExecution(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    result: SessionToolResult | None


def _agent_error_from_tool_result(
    result: SessionToolResult,
    *,
    fallback_code: SessionStateAgentErrorCode,
) -> SessionStateAgentError:
    if result.error is None:
        return SessionStateAgentError(
            code=fallback_code,
            message=result.message,
        )
    code = (
        SessionStateAgentErrorCode.SESSION_NOT_AVAILABLE
        if result.error.code.value == "SESSION_NOT_AVAILABLE"
        else fallback_code
    )
    return SessionStateAgentError(
        code=code,
        message=result.error.message,
        field=result.error.field,
        value=result.error.value,
    )


def load_session_state_agent_prompt() -> str:
    return SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")


def result_to_pretty_json(result: SessionStateAgentResult) -> str:
    return json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2)
