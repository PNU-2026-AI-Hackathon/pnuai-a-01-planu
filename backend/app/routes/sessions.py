"""Session lookup and PlaNU agent routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from ..agents import SessionStateAgent, SessionStateAgentResult
from ..core.errors import AppError
from ..deps import (
    get_agent_runtime,
    get_condition_summary_service,
    get_session_service,
    get_session_state_agent,
    get_session_store,
)
from ..runtime import AgentRuntime, CandidateSelectionRequest
from ..schemas.agent_schema import (
    PlanuChatRequest,
    PlanuChatResponse,
    SelectedTimetableResponse,
    SessionCreateRequest,
    SessionCreateResponse,
)
from ..schemas.session_schema import MajorCandidatesResponse
from ..services.exceptions import SessionNotAvailableError
from ..services.session_service import SessionService
from ..services.condition_summary_service import ConditionSummaryService
from ..schemas.condition_summary_schema import ConditionSummaryDto
from ..services.session_store import SessionNotFoundError, SessionStore


router = APIRouter(prefix="/sessions", tags=["sessions"])


class AgentMessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    message: str = Field(min_length=1)
    request_id: str | None = Field(default=None, min_length=1)


class AgentMessageResponse(SessionStateAgentResult):
    pass


@router.post("", response_model=SessionCreateResponse)
def create_session(
    request: SessionCreateRequest | None = None,
    service: SessionService = Depends(get_session_service),
) -> SessionCreateResponse:
    try:
        state = service.create_session()
        if request is not None and request.department:
            state = service.set_department(state.session_id, request.department)
    except Exception as exc:
        raise AppError(
            "SESSION_CREATE_FAILED",
            "세션을 생성하지 못했습니다.",
            status_code=500,
        ) from exc
    return SessionCreateResponse(
        session_id=state.session_id,
        created_at=state.created_at.isoformat(),
        expires_at=state.expires_at.isoformat(),
    )


@router.get("/{session_id}/major-candidates", response_model=MajorCandidatesResponse)
async def get_major_candidates(
    session_id: str,
    store: SessionStore = Depends(get_session_store),
) -> MajorCandidatesResponse:
    try:
        session = store.get(session_id)
    except SessionNotFoundError as exc:
        raise AppError(
            "SESSION_NOT_FOUND",
            "세션을 찾을 수 없거나 만료되었습니다.",
            status_code=404,
        ) from exc

    return MajorCandidatesResponse(
        session_id=session.session_id,
        session_stage=session.session_stage,
        department=session.department,
        major_candidates=session.major_candidates,
    )


@router.post("/{session_id}/chat", response_model=PlanuChatResponse)
def post_chat_message(
    session_id: str,
    request: PlanuChatRequest,
    runtime: AgentRuntime = Depends(get_agent_runtime),
) -> PlanuChatResponse:
    return runtime.handle_message(
        session_id=session_id,
        message=request.message,
        request_id=request.request_id,
    )


@router.post("/{session_id}/conditions/confirm", response_model=ConditionSummaryDto)
def confirm_timetable_conditions(
    session_id: str,
    service: SessionService = Depends(get_session_service),
    summary_service: ConditionSummaryService = Depends(get_condition_summary_service),
) -> ConditionSummaryDto:
    try:
        state = service.confirm_generation_preferences(session_id)
    except SessionNotAvailableError as exc:
        raise AppError(
            "SESSION_NOT_AVAILABLE",
            "세션을 찾을 수 없거나 만료되었습니다.",
            status_code=404,
        ) from exc
    return summary_service.summarize(state)


@router.post("/{session_id}/agent/messages", response_model=AgentMessageResponse)
def post_agent_message(
    session_id: str,
    request: AgentMessageRequest,
    agent: SessionStateAgent = Depends(get_session_state_agent),
) -> AgentMessageResponse:
    result = agent.run(
        {
            "session_id": session_id,
            "user_message": request.message,
            "request_id": request.request_id,
        }
    )
    if result.error is not None and result.error.code.value == "SESSION_NOT_AVAILABLE":
        raise AppError(
            "SESSION_NOT_AVAILABLE",
            "세션을 찾을 수 없거나 만료되었습니다.",
            status_code=404,
        )
    return AgentMessageResponse.model_validate(result.model_dump(mode="json"))


@router.get("/{session_id}/timetable", response_model=SelectedTimetableResponse)
def get_selected_timetable(
    session_id: str,
    runtime: AgentRuntime = Depends(get_agent_runtime),
) -> SelectedTimetableResponse:
    return runtime.get_selected_timetable(session_id=session_id)


@router.post("/{session_id}/timetables/{candidate_id}/select", response_model=SelectedTimetableResponse)
def select_timetable_candidate(
    session_id: str,
    candidate_id: str,
    runtime: AgentRuntime = Depends(get_agent_runtime),
) -> SelectedTimetableResponse:
    request = CandidateSelectionRequest(session_id=session_id, candidate_id=candidate_id)
    return runtime.select_candidate(
        session_id=request.session_id,
        candidate_id=request.candidate_id,
    )
