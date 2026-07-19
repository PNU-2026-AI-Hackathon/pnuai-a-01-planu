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


def _course(
    course_id: str,
    name: str,
    division: str,
    *,
    professor: str = "김교수",
    class_times: list[ClassTime] | None = None,
) -> Course:
    return Course(
        course_id=course_id,
        course_name=name,
        category=Category.MAJOR_REQUIRED,
        credit=3,
        division=division,
        professor=professor,
        class_times=class_times or [
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
    course = body["matched_courses"][0]["course"]
    assert course["course_id"] == "MA100-001"
    assert course["course_name"] == "자료구조"
    assert course["division"] == "001"
    assert course["professor"] == "김교수"
    assert course["class_times"][0]["day"] == "MON"
    assert course["class_times"][0]["start"] == "09:00"
    assert course["class_times"][0]["end"] == "10:15"
    assert course["class_times"][0]["classroom"] == "제6공학관 6201"
    assert course["class_times"][0]["building_code"] == "6201"
    assert body["timetable_entries"] == [
        {
            "course_id": "MA100-001",
            "course_name": "자료구조",
            "category": "MAJOR_REQUIRED",
            "credit": 3.0,
            "division": "001",
            "professor": "김교수",
            "day": "MON",
            "start": "09:00",
            "end": "10:15",
            "classroom": "제6공학관 6201",
            "building_code": "6201",
        }
    ]
    assert body["can_confirm"] is True


def test_major_preview_api_flattens_multiple_class_times() -> None:
    store = SessionStore()
    session = store.create(
        "컴퓨터공학과",
        major_candidates=[
            _course(
                "MA100-001",
                "자료구조",
                "001",
                class_times=[
                    ClassTime(
                        day=Day.MON,
                        start="09:00",
                        end="10:15",
                        classroom="제6공학관 6201",
                        building_code="6201",
                    ),
                    ClassTime(
                        day=Day.WED,
                        start="09:00",
                        end="10:15",
                        classroom="제6공학관 6202",
                        building_code="6202",
                    ),
                ],
            )
        ],
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
            json={"session_id": session.session_id, "prompt": "자료구조 001분반"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    entries = response.json()["timetable_entries"]
    assert [(item["day"], item["classroom"]) for item in entries] == [
        ("MON", "제6공학관 6201"),
        ("WED", "제6공학관 6202"),
    ]


def test_major_preview_api_sorts_timetable_entries() -> None:
    monday_late = _course(
        "MA300-001",
        "알고리즘",
        "001",
        class_times=[
            ClassTime(
                day=Day.MON,
                start="11:00",
                end="12:15",
                classroom="A",
                building_code="A",
            )
        ],
    )
    monday_early = _course(
        "MA100-001",
        "자료구조",
        "001",
        class_times=[
            ClassTime(
                day=Day.MON,
                start="09:00",
                end="10:15",
                classroom="B",
                building_code="B",
            )
        ],
    )
    tuesday = _course(
        "MA200-001",
        "운영체제",
        "001",
        class_times=[
            ClassTime(
                day=Day.TUE,
                start="09:00",
                end="10:15",
                classroom="C",
                building_code="C",
            )
        ],
    )
    wednesday = _course(
        "MA400-001",
        "컴퓨터구조",
        "001",
        class_times=[
            ClassTime(
                day=Day.WED,
                start="09:00",
                end="10:15",
                classroom="D",
                building_code="D",
            )
        ],
    )
    store = SessionStore()
    session = store.create(
        "컴퓨터공학과",
        major_candidates=[wednesday, monday_late, tuesday, monday_early],
    )
    service = MajorPreviewService(
        store=store,
        parser=FakeParser(
            MajorSelectionParseResult(
                selected_courses=[
                    MajorCourseReference(course_name="컴퓨터구조", section="001"),
                    MajorCourseReference(course_name="알고리즘", section="001"),
                    MajorCourseReference(course_name="운영체제", section="001"),
                    MajorCourseReference(course_name="자료구조", section="001"),
                ]
            )
        ),
    )
    app.dependency_overrides[get_major_preview_service] = lambda: service
    client = TestClient(app)

    try:
        response = client.post(
            "/major/preview",
            json={"session_id": session.session_id, "prompt": "전공 네 과목"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert [
        (item["day"], item["start"], item["course_id"])
        for item in response.json()["timetable_entries"]
    ] == [
        ("MON", "09:00", "MA100-001"),
        ("MON", "11:00", "MA300-001"),
        ("TUE", "09:00", "MA200-001"),
        ("WED", "09:00", "MA400-001"),
    ]


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
