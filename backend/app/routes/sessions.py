"""Session lookup routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..core.errors import AppError
from ..deps import get_session_store
from ..schemas.session_schema import MajorCandidatesResponse
from ..services.session_store import SessionNotFoundError, SessionStore


router = APIRouter(prefix="/sessions", tags=["sessions"])


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
