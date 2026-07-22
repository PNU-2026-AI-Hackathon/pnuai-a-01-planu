"""Major course selection routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..deps import get_major_confirm_service, get_major_preview_service
from ..schemas.major_schema import (
    MajorCourseListResponse,
    MajorConfirmRequest,
    MajorConfirmResponse,
    MajorManualPreviewRequest,
    MajorPreviewRequest,
    MajorPreviewResponse,
)
from ..services.major_confirm_service import MajorConfirmService
from ..services.major_preview_service import MajorPreviewService


router = APIRouter(prefix="/major", tags=["major"])


@router.get("/courses", response_model=MajorCourseListResponse)
async def list_major_courses(
    session_id: str = Query(min_length=1),
    service: MajorPreviewService = Depends(get_major_preview_service),
) -> MajorCourseListResponse:
    return await service.list_uploaded_courses(session_id=session_id)


@router.post("/preview", response_model=MajorPreviewResponse)
async def preview_major_selection(
    request: MajorPreviewRequest,
    service: MajorPreviewService = Depends(get_major_preview_service),
) -> MajorPreviewResponse:
    return await service.create_preview(
        session_id=request.session_id,
        prompt=request.prompt,
    )


@router.post("/manual-preview", response_model=MajorPreviewResponse)
async def manual_preview_major_selection(
    request: MajorManualPreviewRequest,
    service: MajorPreviewService = Depends(get_major_preview_service),
) -> MajorPreviewResponse:
    return await service.create_manual_preview(
        session_id=request.session_id,
        course_ids=request.course_ids,
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


@router.post("/reconfirm", response_model=MajorConfirmResponse)
async def reconfirm_major_selection(
    request: MajorConfirmRequest,
    service: MajorConfirmService = Depends(get_major_confirm_service),
) -> MajorConfirmResponse:
    return await service.reconfirm(
        session_id=request.session_id,
        preview_id=request.preview_id,
    )
