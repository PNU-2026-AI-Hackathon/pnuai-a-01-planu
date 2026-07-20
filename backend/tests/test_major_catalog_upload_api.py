"""API tests for ``POST /catalog/major``."""

from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.deps import (
    get_major_catalog_upload_service,
    get_major_preview_service,
)
from backend.app.main import app
from backend.app.models import (
    Category,
    ClassTime,
    Course,
    Day,
    MajorCourseReference,
    MajorSelectionParseResult,
)
from backend.app.services.major_catalog_upload_service import MajorCatalogUploadService
from backend.app.services.major_preview_service import MajorPreviewService
from backend.app.services.session_store import SessionStore


class FakeCatalogParser:
    def parse_major(self, _: object) -> list[Course]:
        return [
            Course(
                course_id="MA100-001",
                course_name="자료구조",
                category=Category.MAJOR_REQUIRED,
                credit=3,
                division="001",
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
        ]


class FakeMajorSelectionParser:
    def parse(self, _: str) -> MajorSelectionParseResult:
        return MajorSelectionParseResult(
            selected_courses=[
                MajorCourseReference(course_name="자료구조", section="001")
            ]
        )


def test_major_catalog_upload_api_returns_session_response() -> None:
    store = SessionStore()
    service = MajorCatalogUploadService(
        store=store,
        parser=FakeCatalogParser(),
    )
    app.dependency_overrides[get_major_catalog_upload_service] = lambda: service
    client = TestClient(app)

    try:
        response = client.post(
            "/catalog/major",
            data={"department": "컴퓨터공학과"},
            files={
                "major_catalog": (
                    "major.xlsx",
                    b"placeholder",
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["session_stage"] == "catalog_parsed"
    assert body["parsed_course_count"] == 1
    assert store.get(body["session_id"]).major_candidates[0].course_name == "자료구조"


def test_uploaded_major_catalog_session_can_call_preview() -> None:
    store = SessionStore()
    upload_service = MajorCatalogUploadService(
        store=store,
        parser=FakeCatalogParser(),
    )
    preview_service = MajorPreviewService(
        store=store,
        parser=FakeMajorSelectionParser(),
    )
    app.dependency_overrides[get_major_catalog_upload_service] = lambda: upload_service
    app.dependency_overrides[get_major_preview_service] = lambda: preview_service
    client = TestClient(app)

    try:
        upload_response = client.post(
            "/catalog/major",
            data={"department": "컴퓨터공학과"},
            files={"major_catalog": ("major.xlsx", b"placeholder")},
        )
        session_id = upload_response.json()["session_id"]
        preview_response = client.post(
            "/major/preview",
            json={"session_id": session_id, "prompt": "자료구조 001분반"},
        )
    finally:
        app.dependency_overrides.clear()

    assert upload_response.status_code == 200
    assert preview_response.status_code == 200
    assert preview_response.json()["matched_courses"][0]["course"]["course_id"] == "MA100-001"


def test_major_catalog_upload_api_returns_standard_error_for_invalid_extension() -> None:
    client = TestClient(app)

    response = client.post(
        "/catalog/major",
        data={"department": "컴퓨터공학과"},
        files={"major_catalog": ("major.csv", b"placeholder")},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_FILE_EXTENSION"


def test_major_catalog_upload_api_returns_standard_error_for_missing_file() -> None:
    client = TestClient(app)

    response = client.post(
        "/catalog/major",
        data={"department": "컴퓨터공학과"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "MAJOR_CATALOG_REQUIRED"


def test_major_catalog_upload_api_requires_department() -> None:
    client = TestClient(app)

    missing = client.post(
        "/catalog/major",
        files={"major_catalog": ("major.xlsx", b"placeholder")},
    )
    blank = client.post(
        "/catalog/major",
        data={"department": "   "},
        files={"major_catalog": ("major.xlsx", b"placeholder")},
    )

    assert missing.status_code == 400
    assert missing.json()["error"]["code"] == "DEPARTMENT_REQUIRED"
    assert blank.status_code == 400
    assert blank.json()["error"]["code"] == "DEPARTMENT_REQUIRED"
