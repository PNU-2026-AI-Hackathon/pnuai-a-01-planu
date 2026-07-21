"""Catalog upload routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, UploadFile

from ..deps import get_major_catalog_upload_service
from ..schemas.catalog_schema import MajorCatalogUploadResponse
from ..services.major_catalog_upload_service import MajorCatalogUploadService


router = APIRouter(prefix="/catalog", tags=["catalog"])


@router.post("/major", response_model=MajorCatalogUploadResponse)
async def upload_major_catalog(
    major_catalog: UploadFile | None = File(default=None),
    department: str | None = Form(default=None),
    service: MajorCatalogUploadService = Depends(get_major_catalog_upload_service),
) -> MajorCatalogUploadResponse:
    return await service.upload_and_create_session(
        upload_file=major_catalog,
        department=department,
    )
