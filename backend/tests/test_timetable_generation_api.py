"""API tests for ``POST /recommend/generate``."""

from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.deps import get_timetable_generation_service
from backend.app.main import app
from backend.app.models import (
    Category,
    ClassTime,
    Course,
    Day,
    GeneralCoursePoolResult,
    GeneralCoursePools,
)
from backend.app.services.session_store import SessionStage, SessionStore
from backend.app.services.timetable_generation_service import TimetableGenerationService


def _course(
    course_id: str,
    name: str,
    category: Category,
    *,
    day: Day = Day.MON,
    start: str = "09:00",
    end: str = "10:00",
    credit: float = 3,
    area: int | None = None,
) -> Course:
    return Course(
        course_id=course_id,
        course_name=name,
        category=category,
        area=area,
        credit=credit,
        division="001",
        professor="김교수",
        class_times=[
            ClassTime(
                day=day,
                start=start,
                end=end,
                classroom="강의실",
                building_code="A",
            )
        ],
    )


def _major() -> Course:
    return _course("MAJ-001", "자료구조", Category.MAJOR_REQUIRED, credit=9)


def _required() -> Course:
    return _course(
        "REQ-001",
        "고전읽기와토론",
        Category.GENERAL_REQUIRED,
        day=Day.TUE,
        start="10:00",
        end="11:00",
        credit=2,
    )


def _elective() -> Course:
    return _course(
        "ELE-001",
        "과학기술과사회",
        Category.GENERAL_ELECTIVE,
        day=Day.WED,
        start="13:00",
        end="14:00",
        credit=3,
        area=1,
    )


def test_timetable_generation_api_returns_candidates_and_saves_session() -> None:
    store = SessionStore()
    session = store.create("컴퓨터공학과")
    store.update(
        session.session_id,
        fixed_courses=[_major()],
        confirmed_major_credits=9,
        session_stage=SessionStage.MAJOR_CONFIRMED,
    )
    store.update_general_course_pool(
        session.session_id,
        GeneralCoursePoolResult(
            pools=GeneralCoursePools(
                required_courses=[_required()],
                elective_courses=[_elective()],
            )
        ),
    )
    service = TimetableGenerationService(store=store)
    app.dependency_overrides[get_timetable_generation_service] = lambda: service
    client = TestClient(app)

    try:
        response = client.post(
            "/recommend/generate",
            json={
                "session_id": session.session_id,
                "target_total_credits": 14,
                "additional_elective_count": 1,
                "hard_conditions": {"excluded_days": ["FRI"]},
                "max_candidates": 10,
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["truncated"] is False
    assert body["candidates"]
    candidate = body["candidates"][0]
    assert candidate["load_satisfaction"]["final_total_credits"] == 14
    assert candidate["load_satisfaction"]["required_general_count"] == 1
    assert candidate["load_satisfaction"]["elective_count"] == 1
    assert candidate["load_satisfaction"]["within_credit_limit"] is True
    assert any(
        diagnostic["reason_code"] == "VALID_CANDIDATES"
        for diagnostic in body["diagnostics"]
    )

    saved = store.get(session.session_id)
    assert saved.generated_timetable_candidates
    assert saved.generation_course_load_target is not None
    assert saved.generation_hard_conditions is not None
    assert saved.session_stage is SessionStage.GENERAL_READY


def test_timetable_generation_api_rejects_wrong_session_stage() -> None:
    store = SessionStore()
    session = store.create("컴퓨터공학과")
    service = TimetableGenerationService(store=store)
    app.dependency_overrides[get_timetable_generation_service] = lambda: service
    client = TestClient(app)

    try:
        response = client.post(
            "/recommend/generate",
            json={"session_id": session.session_id},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_SESSION_STAGE"

