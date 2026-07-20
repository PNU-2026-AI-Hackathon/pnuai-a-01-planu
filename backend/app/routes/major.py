"""Major course selection routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..deps import get_major_confirm_service, get_major_preview_service
from ..schemas.major_schema import (
    MajorConfirmRequest,
    MajorConfirmResponse,
    MajorPreviewRequest,
    MajorPreviewResponse,
)
from ..services.major_confirm_service import MajorConfirmService
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


@router.post("/confirm", response_model=MajorConfirmResponse)
async def confirm_major_selection(
    request: MajorConfirmRequest,
    service: MajorConfirmService = Depends(get_major_confirm_service),
) -> MajorConfirmResponse:
    return await service.confirm(
        session_id=request.session_id,
        preview_id=request.preview_id,
    )
