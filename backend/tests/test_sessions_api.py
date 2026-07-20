"""API tests for session lookup routes."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from backend.app.deps import get_session_store
from backend.app.main import app
from backend.app.models import Category, ClassTime, Course, Day
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


def test_major_candidates_lookup_returns_session_courses() -> None:
    store = SessionStore()
    session = store.create(
        "컴퓨터공학과",
        major_candidates=[_course()],
    )
    app.dependency_overrides[get_session_store] = lambda: store
    client = TestClient(app)

    try:
        response = client.get(f"/sessions/{session.session_id}/major-candidates")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == session.session_id
    assert body["session_stage"] == "catalog_parsed"
    assert body["department"] == "컴퓨터공학과"
    assert body["major_candidates"][0]["course_id"] == "MA100-001"
    assert body["major_candidates"][0]["course_name"] == "자료구조"


def test_major_candidates_lookup_uses_standard_missing_session_error() -> None:
    store = SessionStore()
    app.dependency_overrides[get_session_store] = lambda: store
    client = TestClient(app)

    try:
        response = client.get("/sessions/missing/major-candidates")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "SESSION_NOT_FOUND"


def test_major_candidates_lookup_uses_standard_expired_session_error() -> None:
    current = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def clock() -> datetime:
        return current

    store = SessionStore(ttl=timedelta(minutes=1), clock=clock)
    session = store.create("컴퓨터공학과", major_candidates=[_course()])
    current = current + timedelta(minutes=2)
    app.dependency_overrides[get_session_store] = lambda: store
    client = TestClient(app)

    try:
        response = client.get(f"/sessions/{session.session_id}/major-candidates")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "SESSION_NOT_FOUND"


def test_major_candidates_lookup_does_not_change_session_data_except_touch() -> None:
    store = SessionStore()
    session = store.create(
        "컴퓨터공학과",
        major_candidates=[_course()],
    )
    store.update(
        session.session_id,
        session_stage=SessionStage.MAJOR_CONFIRMED,
        fixed_courses=[_course()],
        confirmed_major_credits=3,
    )
    before = store.get(session.session_id, touch=False)
    app.dependency_overrides[get_session_store] = lambda: store
    client = TestClient(app)

    try:
        response = client.get(f"/sessions/{session.session_id}/major-candidates")
    finally:
        app.dependency_overrides.clear()

    after = store.get(session.session_id, touch=False)
    assert response.status_code == 200
    assert after.session_stage is before.session_stage
    assert after.department == before.department
    assert after.major_candidates == before.major_candidates
    assert after.fixed_courses == before.fixed_courses
    assert after.confirmed_major_credits == before.confirmed_major_credits
