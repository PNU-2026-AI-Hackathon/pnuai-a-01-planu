"""Session lookup routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from ..core.errors import AppError
from ..deps import get_session_state_agent, get_session_store
from ..agents import SessionStateAgent, SessionStateAgentResult
from ..schemas.session_schema import MajorCandidatesResponse
from ..services.session_store import SessionNotFoundError, SessionStore


router = APIRouter(prefix="/sessions", tags=["sessions"])


class AgentMessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    message: str = Field(min_length=1)
    request_id: str | None = Field(default=None, min_length=1)


class AgentMessageResponse(SessionStateAgentResult):
    pass


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
    if (
        result.error is not None
        and result.error.code.value == "SESSION_NOT_AVAILABLE"
    ):
        raise AppError(
            "SESSION_NOT_FOUND",
            "세션을 찾을 수 없거나 만료되었습니다.",
            status_code=404,
        )
    return AgentMessageResponse.model_validate(result.model_dump(mode="json"))
