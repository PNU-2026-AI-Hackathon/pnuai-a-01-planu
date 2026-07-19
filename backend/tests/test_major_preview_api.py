"""API tests for ``POST /major/preview``."""

from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.deps import get_major_preview_service
from backend.app.main import app
from backend.app.models import (
    Category,
    ClassTime,
    Course,
    Day,
    MajorCourseReference,
    MajorSelectionParseResult,
)
from backend.app.services.major_preview_service import MajorPreviewService
from backend.app.services.session_store import SessionStore


class FakeParser:
    def __init__(self, result: MajorSelectionParseResult) -> None:
        self.result = result

    def parse(self, _: str) -> MajorSelectionParseResult:
        return self.result


def _course(course_id: str, name: str, division: str) -> Course:
    return Course(
        course_id=course_id,
        course_name=name,
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


def test_major_preview_api_returns_success_response() -> None:
    store = SessionStore()
    session = store.create(
        "컴퓨터공학과",
        major_candidates=[_course("MA100-001", "자료구조", "001")],
    )
    service = MajorPreviewService(
        store=store,
        parser=FakeParser(
            MajorSelectionParseResult(
                selected_courses=[MajorCourseReference(course_name="자료구조", section="001")]
            )
        ),
    )
    app.dependency_overrides[get_major_preview_service] = lambda: service
    client = TestClient(app)

    try:
        response = client.post(
            "/major/preview",
            json={
                "session_id": session.session_id,
                "prompt": "자료구조 001분반",
                "course": {"professor": "변조교수"},
            },
        )

        assert response.status_code == 422

        response = client.post(
            "/major/preview",
            json={
                "session_id": session.session_id,
                "prompt": "자료구조 001분반",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["matched_courses"][0]["course"]["course_id"] == "MA100-001"
    assert body["matched_courses"][0]["course"]["professor"] == "김교수"
    assert body["can_confirm"] is True


def test_major_preview_api_returns_standard_session_error() -> None:
    store = SessionStore()
    service = MajorPreviewService(
        store=store,
        parser=FakeParser(
            MajorSelectionParseResult(
                selected_courses=[MajorCourseReference(course_name="자료구조", section="001")]
            )
        ),
    )
    app.dependency_overrides[get_major_preview_service] = lambda: service
    client = TestClient(app)

    try:
        response = client.post(
            "/major/preview",
            json={"session_id": "missing", "prompt": "자료구조 001분반"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "SESSION_NOT_FOUND"


def test_major_preview_api_rejects_blank_prompt_before_service() -> None:
    client = TestClient(app)

    response = client.post(
        "/major/preview",
        json={"session_id": "session-1", "prompt": "   "},
    )

    assert response.status_code == 422
