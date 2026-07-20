"""Tests for major catalog upload session creation."""

from __future__ import annotations

import asyncio
from io import BytesIO
from pathlib import Path

from fastapi import UploadFile
import pytest

from backend.app.core.errors import AppError
from backend.app.models.course import Category, ClassTime, Course, Day
from backend.app.services.major_catalog_upload_service import MajorCatalogUploadService
from backend.app.services.session_store import SessionStage, SessionStore


class FakeParser:
    def __init__(self, courses: list[Course]) -> None:
        self.courses = courses
        self.called = False
        self.seen_path: Path | None = None

    def parse_major(self, path: str | Path) -> list[Course]:
        self.called = True
        self.seen_path = Path(path)
        assert self.seen_path.name.startswith("planu-major-catalog-")
        return self.courses


def _course(course_id: str = "MA100-001", division: str = "001") -> Course:
    return Course(
        course_id=course_id,
        course_name="자료구조",
        category=Category.MAJOR_REQUIRED,
        credit=3,
        division=division,
        professor="김교수",
        class_times=[
            ClassTime(
                day=Day.MON,
                start="09:00",
                end="10:15",
                classroom="제6공학관 6201",
                building_code="6201",
            )
        ],
    )


def _upload(filename: str, content: bytes) -> UploadFile:
    return UploadFile(filename=filename, file=BytesIO(content))


def test_upload_major_catalog_creates_session_after_parsing() -> None:
    store = SessionStore()
    parser = FakeParser([_course()])
    service = MajorCatalogUploadService(store=store, parser=parser)

    response = asyncio.run(
        service.upload_and_create_session(
            upload_file=_upload("major.xlsx", b"placeholder"),
            department="컴퓨터공학과",
        )
    )

    session = store.get(response.session_id)
    assert response.session_stage is SessionStage.CATALOG_PARSED
    assert response.parsed_course_count == 1
    assert session.department == "컴퓨터공학과"
    assert [course.course_id for course in session.major_candidates] == ["MA100-001"]
    assert parser.called is True
    assert parser.seen_path is not None
    assert not parser.seen_path.exists()


def test_upload_major_catalog_rejects_oversized_file_before_parser() -> None:
    store = SessionStore()
    parser = FakeParser([_course()])
    service = MajorCatalogUploadService(
        store=store,
        parser=parser,
        max_upload_size=4,
    )

    with pytest.raises(AppError) as error:
        asyncio.run(
            service.upload_and_create_session(
                upload_file=_upload("major.xlsx", b"12345"),
                department="컴퓨터공학과",
            )
        )

    assert error.value.code == "FILE_TOO_LARGE"
    assert parser.called is False
    assert len(store) == 0


def test_upload_major_catalog_deduplicates_courses_with_warning() -> None:
    store = SessionStore()
    parser = FakeParser([_course(), _course()])
    service = MajorCatalogUploadService(store=store, parser=parser)

    response = asyncio.run(
        service.upload_and_create_session(
            upload_file=_upload("major.xlsx", b"placeholder"),
            department="컴퓨터공학과",
        )
    )

    session = store.get(response.session_id)
    assert response.parsed_course_count == 1
    assert len(session.major_candidates) == 1
    assert response.warnings == [
        "동일한 과목과 분반으로 판단된 중복 데이터 1건을 제거했습니다."
    ]


def test_upload_major_catalog_rejects_non_xlsx_name() -> None:
    service = MajorCatalogUploadService(
        store=SessionStore(),
        parser=FakeParser([_course()]),
    )

    with pytest.raises(AppError) as error:
        asyncio.run(
            service.upload_and_create_session(
                upload_file=_upload("major.csv", b"placeholder"),
                department="컴퓨터공학과",
            )
        )

    assert error.value.code == "INVALID_FILE_EXTENSION"
