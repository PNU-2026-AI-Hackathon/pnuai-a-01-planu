"""API tests for ``POST /major/confirm``."""

from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.deps import get_major_confirm_service
from backend.app.main import app
from backend.app.models import Category, ClassTime, Course, Day
from backend.app.services.major_confirm_service import MajorConfirmService
from backend.app.services.session_store import SessionStage, SessionStore


def _course(course_id: str = "MA100-001") -> Course:
    return Course(
        course_id=course_id,
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


def _service_with_preview() -> tuple[SessionStore, str, MajorConfirmService]:
    store = SessionStore()
    session = store.create("컴퓨터공학과", major_candidates=[_course()])
    store.update(
        session.session_id,
        session_stage=SessionStage.MAJOR_PREVIEW_CREATED,
        latest_major_preview={
            "session_id": session.session_id,
            "preview_id": "preview-1",
            "matched_course_ids": ["MA100-001"],
            "ambiguous_courses": [],
            "unmatched_courses": [],
            "ambiguous_texts": [],
            "has_time_conflict": False,
            "conflicts": [],
        },
    )
    return store, session.session_id, MajorConfirmService(store=store)


def test_major_confirm_api_returns_confirmed_courses_from_session() -> None:
    store, session_id, service = _service_with_preview()
    app.dependency_overrides[get_major_confirm_service] = lambda: service
    client = TestClient(app)

    try:
        response = client.post(
            "/major/confirm",
            json={
                "session_id": session_id,
                "preview_id": "preview-1",
                "fixed_courses": [{"course_id": "client-injected"}],
                "course_ids": ["client-injected"],
            },
        )
        assert response.status_code == 422

        response = client.post(
            "/major/confirm",
            json={"session_id": session_id, "preview_id": "preview-1"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == session_id
    assert body["preview_id"] == "preview-1"
    assert body["confirmed_course_count"] == 1
    assert body["confirmed_major_credits"] == 3
    assert body["session_stage"] == "major_confirmed"
    assert body["confirmed_courses"][0]["course_id"] == "MA100-001"
    assert body["confirmed_courses"][0]["professor"] == "김교수"
    assert store.get(session_id).fixed_courses[0].course_id == "MA100-001"


def test_major_confirm_api_standard_errors() -> None:
    _, _, service = _service_with_preview()
    app.dependency_overrides[get_major_confirm_service] = lambda: service
    client = TestClient(app)

    try:
        missing = client.post(
            "/major/confirm",
            json={"session_id": "missing", "preview_id": "preview-1"},
        )
        blank_session = client.post(
            "/major/confirm",
            json={"session_id": "   ", "preview_id": "preview-1"},
        )
        blank_preview = client.post(
            "/major/confirm",
            json={"session_id": "session-1", "preview_id": "   "},
        )
    finally:
        app.dependency_overrides.clear()

    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "SESSION_NOT_FOUND"
    assert blank_session.status_code == 422
    assert blank_preview.status_code == 422


def test_major_confirm_api_rejects_missing_or_unconfirmable_preview() -> None:
    store = SessionStore()
    session = store.create("컴퓨터공학과", major_candidates=[_course()])
    store.update(session.session_id, session_stage=SessionStage.MAJOR_PREVIEW_CREATED)
    service = MajorConfirmService(store=store)
    app.dependency_overrides[get_major_confirm_service] = lambda: service
    client = TestClient(app)

    try:
        missing_preview = client.post(
            "/major/confirm",
            json={"session_id": session.session_id, "preview_id": "preview-1"},
        )

        store.update(
            session.session_id,
            latest_major_preview={
                "session_id": session.session_id,
                "preview_id": "preview-1",
                "matched_course_ids": ["MA100-001"],
                "ambiguous_courses": [{"reason": "missing section"}],
                "unmatched_courses": [],
                "ambiguous_texts": [],
                "has_time_conflict": False,
                "conflicts": [],
            },
        )
        unconfirmable = client.post(
            "/major/confirm",
            json={"session_id": session.session_id, "preview_id": "preview-1"},
        )
    finally:
        app.dependency_overrides.clear()

    assert missing_preview.status_code == 404
    assert missing_preview.json()["error"]["code"] == "MAJOR_PREVIEW_NOT_FOUND"
    assert unconfirmable.status_code == 409
    assert unconfirmable.json()["error"]["code"] == "MAJOR_PREVIEW_NOT_CONFIRMABLE"


def test_major_confirm_api_rejects_invalid_session_stage() -> None:
    store = SessionStore()
    session = store.create("컴퓨터공학과", major_candidates=[_course()])
    service = MajorConfirmService(store=store)
    app.dependency_overrides[get_major_confirm_service] = lambda: service
    client = TestClient(app)

    try:
        response = client.post(
            "/major/confirm",
            json={"session_id": session.session_id, "preview_id": "preview-1"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_SESSION_STAGE"
