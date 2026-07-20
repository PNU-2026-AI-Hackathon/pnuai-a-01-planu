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
from ..schemas.catalog_schema import MajorCatalogUploadResponse
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
    ) -> None:
        self.store = store
        self.parser = parser or UploadedCatalogParser()
        self.max_upload_size = max_upload_size

    async def upload_and_create_session(
        self,
        *,
        upload_file: UploadFile | None,
        department: str | None = None,
    ) -> MajorCatalogUploadResponse:
        department = (department or "미정").strip() or "미정"
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
                session = self.store.create(
                    department=department,
                    major_candidates=courses,
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
        handle = tempfile.NamedTemporaryFile(
            mode="wb",
            suffix=".xlsx",
            prefix="planu-major-catalog-",
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
                    if total_size > self.max_upload_size:
                        raise AppError(
                            "FILE_TOO_LARGE",
                            "업로드 파일은 5MB 이하여야 합니다.",
                            status_code=413,
                            details={"max_size_bytes": self.max_upload_size},
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
