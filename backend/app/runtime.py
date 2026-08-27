"""Application-level wrapper around the PlaNU agent."""

from __future__ import annotations

import logging

from .agent_tools.timetable_selection_tools import SelectTimetableCandidateInput
from .agent_tools import TimetableSelectionTools
from .agents import RunnableAgent, SessionStateAgentResult
from .agents.session_state_agent import AgentRankedTimetableCandidate, AgentTimetableCandidate
from .core.errors import AppError
from .services.condition_summary_service import ConditionSummaryService
from .services.exceptions import SessionNotAvailableError
from .services.general_course_pool_service import GeneralCoursePreparationService
from .services.session_service import SessionService
from .schemas.agent_schema import (
    ConfirmationDto,
    ConfirmationOption,
    LegacyAgentMessageResponse,
    PlanuChatResponse,
    SelectedTimetableResponse,
    TimetableCandidateDto,
    TimetableCourseDto,
    selected_timetable_from_domain,
)


logger = logging.getLogger(__name__)


class AgentRuntime:
    """Keeps HTTP routers independent from the agent/tool execution details."""

    def __init__(
        self,
        *,
        session_service: SessionService,
        agent: RunnableAgent,
        selection_tools: TimetableSelectionTools,
        condition_summary_service: ConditionSummaryService | None = None,
        general_course_preparation_service: GeneralCoursePreparationService | None = None,
    ) -> None:
        self._session_service = session_service
        self._agent = agent
        self._selection_tools = selection_tools
        self._condition_summary_service = condition_summary_service or ConditionSummaryService()
        self._general_course_preparation_service = general_course_preparation_service

    def handle_message(
        self,
        *,
        session_id: str,
        message: str,
        request_id: str | None = None,
    ) -> PlanuChatResponse:
        self._ensure_session(session_id)
        self._ensure_default_general_catalog(session_id)
        result = self._run_agent(session_id=session_id, message=message, request_id=request_id)
        if result.error is not None and result.error.code.value == "SESSION_NOT_AVAILABLE":
            raise _session_unavailable_error()
        state = self._session_service.get_session(session_id)
        response = chat_response_from_agent_result(
            result,
            condition_summary=self._condition_summary_service.summarize(state),
        )
        logger.warning(
            "planu_chat_response session_id=%s request_id=%s success=%s changed=%s "
            "unresolved_count=%s candidate_count=%s error_code=%s executed_tools=%s failed_tools=%s message=%s",
            session_id,
            request_id,
            response.success,
            response.changed,
            len(response.unresolved_requests),
            len(response.candidate_courses),
            response.error.code if response.error is not None else None,
            [tool.name for tool in result.executed_tools],
            [tool.name for tool in result.failed_tools],
            response.message,
        )
        return response

    def handle_legacy_message(
        self,
        *,
        session_id: str,
        message: str,
        request_id: str | None = None,
    ) -> LegacyAgentMessageResponse:
        self._ensure_session(session_id)
        self._ensure_default_general_catalog(session_id)
        result = self._run_agent(session_id=session_id, message=message, request_id=request_id)
        if result.error is not None and result.error.code.value == "SESSION_NOT_AVAILABLE":
            raise _session_unavailable_error()
        state = self._session_service.get_session(session_id)
        public = chat_response_from_agent_result(
            result,
            condition_summary=self._condition_summary_service.summarize(state),
        )
        logger.warning(
            "planu_legacy_chat_response session_id=%s request_id=%s success=%s changed=%s "
            "unresolved_count=%s candidate_count=%s error_code=%s executed_tools=%s failed_tools=%s message=%s",
            session_id,
            request_id,
            public.success,
            public.changed,
            len(public.unresolved_requests),
            len(public.candidate_courses),
            public.error.code if public.error is not None else None,
            [tool.name for tool in result.executed_tools],
            [tool.name for tool in result.failed_tools],
            public.message,
        )
        return LegacyAgentMessageResponse(
            success=result.success,
            session_id=result.session_id,
            request_id=result.request_id,
            message=public.message,
            changed=public.changed,
            partially_applied=result.partially_applied,
            needs_confirmation=public.needs_confirmation,
            confirmation=public.confirmation,
            session_summary=public.session_summary,
            condition_summary=public.condition_summary,
            candidate_courses=public.candidate_courses,
            timetable_candidates=public.timetable_candidates,
            selected_timetable=public.selected_timetable,
            unresolved_requests=public.unresolved_requests,
            executed_tools=[item.model_dump(mode="json") for item in result.executed_tools],
            failed_tools=[item.model_dump(mode="json") for item in result.failed_tools],
            error=None if result.error is None else result.error.model_dump(mode="json"),
        )

    def get_selected_timetable(self, *, session_id: str) -> SelectedTimetableResponse:
        state = self._ensure_session(session_id)
        status = None if state.selected_timetable_status is None else state.selected_timetable_status.value
        return SelectedTimetableResponse(
            session_id=session_id,
            selected_timetable=selected_timetable_from_domain(
                state.selected_timetable,
                status=status,
            ),
        )

    def select_candidate(self, *, session_id: str, candidate_id: str) -> SelectedTimetableResponse:
        self._ensure_session(session_id)
        result = self._selection_tools.select_timetable_candidate(
            SelectTimetableCandidateInput(session_id=session_id, candidate_id=candidate_id)
        )
        if not result.success:
            raise AppError(
                result.error.code.value if result.error is not None else "TIMETABLE_SELECTION_FAILED",
                result.message,
                status_code=404 if result.error is not None and result.error.code.value == "SESSION_NOT_AVAILABLE" else 409,
            )
        state = self._session_service.get_session(session_id)
        if state.selected_timetable is None:
            raise AppError(
                "TIMETABLE_SELECTION_EMPTY",
                "선택된 시간표 정보를 저장하지 못했습니다.",
                status_code=409,
            )
        status = None if state.selected_timetable_status is None else state.selected_timetable_status.value
        return SelectedTimetableResponse(
            session_id=session_id,
            selected_timetable=selected_timetable_from_domain(
                state.selected_timetable,
                status=status,
            ),
        )

    def _run_agent(
        self,
        *,
        session_id: str,
        message: str,
        request_id: str | None,
    ) -> SessionStateAgentResult:
        try:
            return self._agent.run(
                {
                    "session_id": session_id,
                    "user_message": message,
                    "request_id": request_id,
                }
            )
        except Exception as exc:
            raise AppError(
                "AGENT_RUN_FAILED",
                "PlaNU Agent 실행 중 오류가 발생했습니다.",
                status_code=502,
            ) from exc

    def _ensure_default_general_catalog(self, session_id: str) -> None:
        if self._general_course_preparation_service is None:
            return
        try:
            prepared = self._general_course_preparation_service.prepare_default_for_session(session_id)
        except Exception:
            logger.exception("agent_runtime_default_general_prepare_failed session_id=%s", session_id)
            return
        if prepared:
            logger.warning("agent_runtime_default_general_prepared session_id=%s", session_id)

    def _ensure_session(self, session_id: str):
        try:
            return self._session_service.get_session(session_id)
        except SessionNotAvailableError as exc:
            raise _session_unavailable_error() from exc

class CandidateSelectionRequest(SelectTimetableCandidateInput):
    pass




def chat_response_from_agent_result(
    result: SessionStateAgentResult,
    *,
    condition_summary=None,
) -> PlanuChatResponse:
    confirmation = _confirmation(result)
    selected_status = None
    if result.state_summary is not None:
        selected_status = result.state_summary.selected_timetable_status
    return PlanuChatResponse(
        session_id=result.session_id or "",
        message=result.message,
        success=result.success,
        error=result.error,
        changed=result.changed,
        needs_confirmation=result.needs_confirmation,
        confirmation=confirmation,
        unresolved_requests=result.unresolved_requests,
        candidate_courses=result.candidate_courses,
        timetable_candidates=_timetable_candidates(result),
        selected_timetable=selected_timetable_from_domain(
            None if result.state_summary is None else result.state_summary.selected_timetable,
            status=selected_status,
        ),
        session_summary=result.state_summary,
        condition_summary=condition_summary,
    )


def _confirmation(result: SessionStateAgentResult) -> ConfirmationDto | None:
    request = result.confirmation_request
    if request is None:
        return None
    return ConfirmationDto(
        reason=request.reason,
        question=request.question,
        options=[
            ConfirmationOption(
                id=candidate.course_id,
                label=candidate.course_name,
                description=candidate.course_code,
                course_id=candidate.course_id,
            )
            for candidate in request.candidates
        ],
    )


def _timetable_candidates(result: SessionStateAgentResult) -> list[TimetableCandidateDto]:
    if result.ranked_timetable_candidates:
        return [_ranked_candidate(candidate) for candidate in result.ranked_timetable_candidates]
    return [_generated_candidate(candidate) for candidate in result.timetable_candidates]


def _ranked_candidate(candidate: AgentRankedTimetableCandidate) -> TimetableCandidateDto:
    return TimetableCandidateDto(
        rank=candidate.rank,
        candidate_id=candidate.candidate_id,
        comparison_score=candidate.comparison_score,
        total_credits=candidate.total_credits,
        courses=[_section_course(section) for section in candidate.sections],
        advantages=[component.label for component in candidate.score_components if component.satisfied],
        trade_offs=[trade_off.code for trade_off in candidate.trade_offs],
    )


def _generated_candidate(candidate: AgentTimetableCandidate) -> TimetableCandidateDto:
    return TimetableCandidateDto(
        rank=candidate.generation_order,
        candidate_id=candidate.candidate_id,
        comparison_score=None,
        total_credits=candidate.total_credits,
        courses=[
            TimetableCourseDto(course_id=course_id, section_id=section_id)
            for course_id, section_id in zip(candidate.course_ids, candidate.section_ids, strict=False)
        ],
    )


def _section_course(section) -> TimetableCourseDto:
    meeting = section.class_times[0] if section.class_times else {}
    return TimetableCourseDto(
        course_id=section.course_id,
        section_id=section.section_id,
        course_code=section.course_code,
        course_name=section.course_name,
        section=section.division,
        professor=section.professor,
        day=meeting.get("day") if isinstance(meeting, dict) else None,
        start_time=meeting.get("start") if isinstance(meeting, dict) else None,
        end_time=meeting.get("end") if isinstance(meeting, dict) else None,
        building=meeting.get("building_code") if isinstance(meeting, dict) else None,
        classroom=meeting.get("classroom") if isinstance(meeting, dict) else None,
        credits=section.credit,
    )


def _session_unavailable_error() -> AppError:
    return AppError(
        "SESSION_NOT_AVAILABLE",
        "세션을 찾을 수 없거나 만료되었습니다.",
        status_code=404,
    )
