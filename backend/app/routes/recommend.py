"""Timetable generation and recommendation routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..deps import get_timetable_generation_service
from ..schemas.recommend_schema import (
    TimetableGenerationRequest,
    TimetableGenerationResponse,
)
from ..services.timetable_generation_service import TimetableGenerationService


router = APIRouter(prefix="/recommend", tags=["recommend"])


@router.post("/generate", response_model=TimetableGenerationResponse)
async def generate_timetable_candidates(
    request: TimetableGenerationRequest,
    service: TimetableGenerationService = Depends(get_timetable_generation_service),
) -> TimetableGenerationResponse:
    result = service.generate_for_session(
        session_id=request.session_id,
        course_load_target=request.course_load_target(),
        hard_conditions=request.hard_conditions,
        preference_prompt=request.preference_prompt,
        max_candidates=request.max_candidates,
    )
    return TimetableGenerationResponse.model_validate(result.model_dump())
