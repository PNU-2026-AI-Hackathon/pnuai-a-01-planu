"""General-course preparation routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, UploadFile

from ..deps import get_general_course_preparation_service
from ..schemas.general_schema import GeneralPreparationResponse
from ..services.general_course_pool_service import GeneralCoursePreparationService


router = APIRouter(prefix="/general", tags=["general"])


@router.post("/prepare", response_model=GeneralPreparationResponse)
async def prepare_general_courses(
    session_id: str = Form(...),
    elective_catalog: UploadFile | None = File(default=None),
    elective_area: int | None = Form(default=None),
    service: GeneralCoursePreparationService = Depends(get_general_course_preparation_service),
) -> GeneralPreparationResponse:
    return await service.prepare_for_session(
        session_id=session_id,
        elective_catalog=elective_catalog,
        elective_area=elective_area,
    )
