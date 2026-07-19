"""Major course selection routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..deps import get_major_preview_service
from ..schemas.major_schema import MajorPreviewRequest, MajorPreviewResponse
from ..services.major_preview_service import MajorPreviewService


router = APIRouter(prefix="/major", tags=["major"])


@router.post("/preview", response_model=MajorPreviewResponse)
async def preview_major_selection(
    request: MajorPreviewRequest,
    service: MajorPreviewService = Depends(get_major_preview_service),
) -> MajorPreviewResponse:
    return await service.create_preview(
        session_id=request.session_id,
        prompt=request.prompt,
    )

