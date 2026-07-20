"""API tests for ``POST /general/prepare``."""

from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.deps import get_general_course_preparation_service
from backend.app.main import app
from backend.app.models import Category, ClassTime, Course, Day
from backend.app.services.general_course_pool_service import GeneralCoursePreparationService
from backend.app.services.session_store import SessionStage, SessionStore


def _course(
    course_id: str,
    name: str,
    category: Category,
    division: str,
    *,
    area: int | None = None,
) -> Course:
    return Course(
        course_id=course_id,
        course_name=name,
        category=category,
        area=area,
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


class FakeElectiveParser:
    def __init__(self, courses: list[Course]) -> None:
        self.courses = courses
        self.received_area: int | None = None

    def parse_elective(self, _: object, *, area: int | None = None) -> list[Course]:
        self.received_area = area
        return self.courses


def _confirmed_session(store: SessionStore) -> str:
    session = store.create("컴퓨터공학과")
    store.update(
        session.session_id,
        fixed_courses=[
            _course("MA100-001", "자료구조", Category.MAJOR_REQUIRED, "001"),
        ],
        session_stage=SessionStage.MAJOR_CONFIRMED,
    )
    return session.session_id


def test_general_prepare_api_uses_fallback_and_marks_session_ready() -> None:
    store = SessionStore()
    session_id = _confirmed_session(store)
    service = GeneralCoursePreparationService(
        store=store,
        general_required_courses=[
            _course("ZE100-001", "고전읽기와토론", Category.GENERAL_REQUIRED, "001"),
        ],
        fallback_elective_courses=[
            _course("ZE200-001", "과학기술과사회", Category.GENERAL_ELECTIVE, "001", area=2),
        ],
    )
    app.dependency_overrides[get_general_course_preparation_service] = lambda: service
    client = TestClient(app)

    try:
        response = client.post("/general/prepare", data={"session_id": session_id})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["session_stage"] == "general_ready"
    assert body["required_course_count"] == 1
    assert body["elective_course_count"] == 1
    assert body["data_source"] == "fallback_catalog"
    assert body["warnings"]
    saved = store.get(session_id)
    assert saved.session_stage is SessionStage.GENERAL_READY
    assert saved.general_pool_data_source == "fallback_catalog"
    assert saved.general_pool_prepared_at is not None


def test_general_prepare_api_upload_passes_area_to_parser() -> None:
    store = SessionStore()
    session_id = _confirmed_session(store)
    parser = FakeElectiveParser(
        [_course("UP100-001", "업로드교양", Category.GENERAL_ELECTIVE, "001", area=4)]
    )
    service = GeneralCoursePreparationService(
        store=store,
        general_required_courses=[
            _course("ZE100-001", "고전읽기와토론", Category.GENERAL_REQUIRED, "001"),
        ],
        fallback_elective_courses=[],
        elective_parser=parser,
    )
    app.dependency_overrides[get_general_course_preparation_service] = lambda: service
    client = TestClient(app)

    try:
        response = client.post(
            "/general/prepare",
            data={"session_id": session_id, "elective_area": "4"},
            files={
                "elective_catalog": (
                    "elective.xlsx",
                    b"placeholder",
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["data_source"] == "uploaded_catalog"
    assert body["elective_area"] == 4
    assert parser.received_area == 4
    saved = store.get(session_id)
    assert saved.general_pool_data_source == "uploaded_catalog"
    assert saved.general_pool_elective_area == 4


def test_general_prepare_api_requires_area_with_upload() -> None:
    store = SessionStore()
    session_id = _confirmed_session(store)
    service = GeneralCoursePreparationService(
        store=store,
        general_required_courses=[
            _course("ZE100-001", "고전읽기와토론", Category.GENERAL_REQUIRED, "001"),
        ],
        fallback_elective_courses=[],
        elective_parser=FakeElectiveParser([]),
    )
    app.dependency_overrides[get_general_course_preparation_service] = lambda: service
    client = TestClient(app)

    try:
        response = client.post(
            "/general/prepare",
            data={"session_id": session_id},
            files={"elective_catalog": ("elective.xlsx", b"placeholder")},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "ELECTIVE_AREA_REQUIRED"


def test_general_prepare_api_rejects_wrong_stage() -> None:
    store = SessionStore()
    session = store.create("컴퓨터공학과")
    service = GeneralCoursePreparationService(
        store=store,
        general_required_courses=[
            _course("ZE100-001", "고전읽기와토론", Category.GENERAL_REQUIRED, "001"),
        ],
        fallback_elective_courses=[
            _course("ZE200-001", "과학기술과사회", Category.GENERAL_ELECTIVE, "001", area=2),
        ],
    )
    app.dependency_overrides[get_general_course_preparation_service] = lambda: service
    client = TestClient(app)

    try:
        response = client.post("/general/prepare", data={"session_id": session.session_id})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_SESSION_STAGE"
