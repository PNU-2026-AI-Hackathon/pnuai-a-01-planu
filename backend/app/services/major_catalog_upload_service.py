"""Upload, validate, parse, and store user-owned major catalog workbooks."""

from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path
from typing import Protocol

from fastapi import UploadFile

from ..core.errors import AppError
from ..models.course import Course
from ..models.course_discovery import CatalogKind
from ..repositories.catalog_repository import CatalogRepository
from ..schemas.catalog_schema import MajorCatalogUploadResponse
from .exceptions import SessionNotAvailableError
from .session_service import SessionService
from .session_store import SessionStore, session_store
from .uploaded_catalog_parser import (
    MAX_UPLOAD_SIZE,
    UploadedCatalogError,
    UploadedCatalogParser,
)


UPLOAD_CHUNK_SIZE = 64 * 1024


class MajorCatalogParserProtocol(Protocol):
    def parse_major(self, path: str | Path) -> list[Course]:
        ...


class MajorCatalogUploadService:
    def __init__(
        self,
        *,
        store: SessionStore = session_store,
        parser: MajorCatalogParserProtocol | None = None,
        max_upload_size: int = MAX_UPLOAD_SIZE,
        session_service: SessionService | None = None,
        catalog_repository: CatalogRepository | None = None,
    ) -> None:
        self.store = store
        self.parser = parser or UploadedCatalogParser()
        self.max_upload_size = max_upload_size
        self.session_service = session_service
        self.catalog_repository = catalog_repository

    async def upload_and_create_session(
        self,
        *,
        upload_file: UploadFile | None,
        department: str | None = None,
    ) -> MajorCatalogUploadResponse:
        department = (department or "").strip()
        if not department:
            raise AppError(
                "DEPARTMENT_REQUIRED",
                "학과를 선택해주세요.",
                status_code=400,
            )
        self._validate_upload_name(upload_file)

        temp_path: Path | None = None
        try:
            temp_path = await self._write_limited_temp_file(upload_file)
            try:
                parsed_courses = await asyncio.to_thread(self.parser.parse_major, temp_path)
            except UploadedCatalogError as exc:
                raise _catalog_app_error(exc) from exc
            except Exception as exc:
                raise AppError(
                    "MAJOR_CATALOG_PARSE_FAILED",
                    "전공 수강편람을 파싱하지 못했습니다.",
                    status_code=422,
                ) from exc

            courses, duplicate_count = _validate_and_deduplicate(parsed_courses)
            warnings = []
            if duplicate_count:
                warnings.append(
                    f"동일한 과목과 분반으로 판단된 중복 데이터 {duplicate_count}건을 제거했습니다."
                )

            try:
                session = self._create_session_with_major_catalog(
                    department=department,
                    courses=courses,
                )
            except Exception as exc:
                raise AppError(
                    "SESSION_CREATE_FAILED",
                    "전공 수강편람 세션을 생성하지 못했습니다.",
                    status_code=500,
                ) from exc

            return MajorCatalogUploadResponse(
                session_id=session.session_id,
                session_stage=session.session_stage,
                parsed_course_count=len(session.major_candidates),
                warnings=warnings,
            )
        finally:
            if temp_path is not None:
                try:
                    temp_path.unlink(missing_ok=True)
                except OSError:
                    pass

    def _create_session_with_major_catalog(
        self,
        *,
        department: str,
        courses: list[Course],
    ):
        if self.session_service is None or self.catalog_repository is None:
            return self.store.create(
                department=department,
                major_candidates=courses,
            )

        state = self.session_service.create_session()
        state = self.session_service.set_department(state.session_id, department)
        catalog_id = f"{state.session_id}:major"
        try:
            self.catalog_repository.register(
                catalog_id,
                kind=CatalogKind.MAJOR,
                courses=courses,
                department=department,
            )
            self.session_service.register_major_catalog(state.session_id, catalog_id)
        except SessionNotAvailableError:
            raise
        except Exception:
            self.session_service.delete_session(state.session_id)
            raise
        return self.store.get(state.session_id, touch=False)

    @staticmethod
    def _validate_upload_name(upload_file: UploadFile | None) -> None:
        if upload_file is None:
            raise AppError(
                "MAJOR_CATALOG_REQUIRED",
                "전공 수강편람 파일을 업로드해주세요.",
                status_code=400,
            )
        filename = (upload_file.filename or "").strip()
        if not filename:
            raise AppError(
                "MAJOR_CATALOG_REQUIRED",
                "전공 수강편람 파일을 업로드해주세요.",
                status_code=400,
            )
        if Path(filename).suffix.lower() != ".xlsx":
            raise AppError(
                "INVALID_FILE_EXTENSION",
                "전공 수강편람은 .xlsx 파일만 업로드할 수 있습니다.",
                status_code=400,
            )

    async def _write_limited_temp_file(self, upload_file: UploadFile) -> Path:
        return await write_limited_upload_to_temp(
            upload_file,
            suffix=".xlsx",
            prefix="planu-major-catalog-",
            max_upload_size=self.max_upload_size,
        )


async def write_limited_upload_to_temp(
    upload_file: UploadFile,
    *,
    suffix: str,
    prefix: str,
    max_upload_size: int = MAX_UPLOAD_SIZE,
) -> Path:
    handle = tempfile.NamedTemporaryFile(
        mode="wb",
        suffix=suffix,
        prefix=prefix,
        delete=False,
    )
    temp_path = Path(handle.name)
    total_size = 0
    try:
        with handle:
            while True:
                chunk = await upload_file.read(UPLOAD_CHUNK_SIZE)
                if not chunk:
                    break
                total_size += len(chunk)
                if total_size > max_upload_size:
                    raise AppError(
                        "FILE_TOO_LARGE",
                        "업로드 파일은 5MB 이하여야 합니다.",
                        status_code=413,
                        details={"max_size_bytes": max_upload_size},
                    )
                handle.write(chunk)
    except Exception:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise

    if total_size == 0:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise AppError(
            "INVALID_EXCEL_FILE",
            "유효한 .xlsx 파일이 아닙니다.",
            status_code=400,
        )
    return temp_path


def _catalog_app_error(exc: UploadedCatalogError) -> AppError:
    message = str(exc) or "전공 수강편람을 처리하지 못했습니다."
    if "파일 크기" in message:
        return AppError(
            "FILE_TOO_LARGE",
            "업로드 파일은 5MB 이하여야 합니다.",
            status_code=413,
            details={"max_size_bytes": MAX_UPLOAD_SIZE},
        )
    if "유효한 .xlsx" in message or "엑셀 파일을 열 수 없습니다" in message:
        return AppError(
            "INVALID_EXCEL_FILE",
            "유효한 .xlsx 파일이 아닙니다.",
            status_code=400,
        )
    if ".xlsx" in message:
        return AppError(
            "INVALID_FILE_EXTENSION",
            "전공 수강편람은 .xlsx 파일만 업로드할 수 있습니다.",
            status_code=400,
        )
    if "비어 있습니다" in message or "찾지 못했습니다" in message:
        return AppError("EMPTY_CATALOG", message, status_code=422)
    if "필수 열" in message:
        return AppError("INVALID_CATALOG_FORMAT", message, status_code=422)
    return AppError("MAJOR_CATALOG_PARSE_FAILED", message, status_code=422)


def _validate_and_deduplicate(courses: list[Course]) -> tuple[list[Course], int]:
    if not courses:
        raise AppError(
            "EMPTY_CATALOG",
            "시간 정보가 있는 전공 과목을 찾지 못했습니다.",
            status_code=422,
        )

    deduped: list[Course] = []
    seen: set[tuple[str, str]] = set()
    duplicate_count = 0
    for course in courses:
        try:
            normalized = Course.model_validate(course)
        except Exception as exc:
            raise AppError(
                "MAJOR_CATALOG_VALIDATION_FAILED",
                "파싱된 전공 과목 데이터가 유효하지 않습니다.",
                status_code=422,
            ) from exc

        key = (
            normalized.course_id.strip().casefold()
            or normalized.course_name.strip().casefold(),
            normalized.division.strip().casefold(),
        )
        if key in seen:
            duplicate_count += 1
            continue
        seen.add(key)
        deduped.append(normalized)

    if not deduped:
        raise AppError(
            "EMPTY_CATALOG",
            "시간 정보가 있는 전공 과목을 찾지 못했습니다.",
            status_code=422,
        )
    return deduped, duplicate_count
