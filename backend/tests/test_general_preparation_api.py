"""API tests for ``POST /general/prepare``."""

from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.deps import get_general_course_preparation_service
from backend.app.main import app
from backend.app.models import Category, ClassTime, Course, Day
from backend.app.services.general_course_pool_service import (
    CourseRestrictionPolicy,
    DepartmentRestrictionRule,
    GeneralCoursePoolService,
    GeneralCoursePreparationService,
)
from backend.app.services.session_store import SessionStage, SessionStore
from backend.app.models.course_load import CourseLoadTarget
from backend.app.models.timetable import (
    CourseLoadSatisfaction,
    GenerationDiagnostic,
    RankingResult,
    Timetable,
    TimetableGenerationCandidate,
    TimetableRankingResult,
)


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


def _pool_service_for_required(*courses: Course) -> GeneralCoursePoolService:
    return GeneralCoursePoolService(
        restriction_policy=CourseRestrictionPolicy(
            rules=[
                DepartmentRestrictionRule(
                    course_code=course.course_id.rsplit("-", 1)[0],
                    division=course.division,
                    allowed_departments=frozenset({"컴퓨터공학과"}),
                    blocked_departments=frozenset(),
                )
                for course in courses
                if course.category is Category.GENERAL_REQUIRED
            ],
        ),
    )


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
    required = _course("ZE100-001", "고전읽기와토론", Category.GENERAL_REQUIRED, "001")
    service = GeneralCoursePreparationService(
        store=store,
        pool_service=_pool_service_for_required(required),
        general_required_courses=[required],
        fallback_elective_courses=[
            _course("ZE200-001", "과학기술과사회", Category.GENERAL_ELECTIVE, "001", area=2),
        ],
    )
    app.dependency_overrides[get_general_course_preparation_service] = lambda: service
    client = TestClient(app)

    try:
        response = client.post(
            "/general/prepare",
            data={"session_id": session_id, "elective_area": "2"},
        )
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


def test_general_prepare_api_filters_fallback_by_elective_area() -> None:
    store = SessionStore()
    session_id = _confirmed_session(store)
    required = _course("ZE100-001", "고전읽기와토론", Category.GENERAL_REQUIRED, "001")
    area_3 = _course("ZE203-001", "다른영역", Category.GENERAL_ELECTIVE, "001", area=3)
    area_4 = _course("ZE204-001", "선택영역", Category.GENERAL_ELECTIVE, "001", area=4)
    service = GeneralCoursePreparationService(
        store=store,
        pool_service=_pool_service_for_required(required),
        general_required_courses=[required],
        fallback_elective_courses=[area_3, area_4],
    )
    app.dependency_overrides[get_general_course_preparation_service] = lambda: service
    client = TestClient(app)

    try:
        response = client.post(
            "/general/prepare",
            data={"session_id": session_id, "elective_area": "4"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["elective_course_count"] == 1
    saved = store.get(session_id)
    assert saved.general_pool_elective_area == 4
    assert saved.general_elective_candidates == [area_4]


def test_general_prepare_api_upload_passes_area_to_parser() -> None:
    store = SessionStore()
    session_id = _confirmed_session(store)
    required = _course("ZE100-001", "고전읽기와토론", Category.GENERAL_REQUIRED, "001")
    parser = FakeElectiveParser(
        [_course("UP100-001", "업로드교양", Category.GENERAL_ELECTIVE, "001", area=4)]
    )
    service = GeneralCoursePreparationService(
        store=store,
        pool_service=_pool_service_for_required(required),
        general_required_courses=[required],
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


def test_general_prepare_api_requires_area_without_upload() -> None:
    store = SessionStore()
    session_id = _confirmed_session(store)
    required = _course("ZE100-001", "고전읽기와토론", Category.GENERAL_REQUIRED, "001")
    service = GeneralCoursePreparationService(
        store=store,
        pool_service=_pool_service_for_required(required),
        general_required_courses=[required],
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

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "ELECTIVE_AREA_REQUIRED"


def test_general_prepare_api_requires_area_with_upload() -> None:
    store = SessionStore()
    session_id = _confirmed_session(store)
    required = _course("ZE100-001", "고전읽기와토론", Category.GENERAL_REQUIRED, "001")
    service = GeneralCoursePreparationService(
        store=store,
        pool_service=_pool_service_for_required(required),
        general_required_courses=[required],
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


def test_general_prepare_api_rejects_invalid_area() -> None:
    store = SessionStore()
    session_id = _confirmed_session(store)
    service = GeneralCoursePreparationService(store=store)
    app.dependency_overrides[get_general_course_preparation_service] = lambda: service
    client = TestClient(app)

    try:
        response = client.post(
            "/general/prepare",
            data={"session_id": session_id, "elective_area": "10"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_ELECTIVE_AREA"


def test_general_prepare_api_returns_error_when_fallback_area_is_empty() -> None:
    store = SessionStore()
    session_id = _confirmed_session(store)
    required = _course("ZE100-001", "고전읽기와토론", Category.GENERAL_REQUIRED, "001")
    service = GeneralCoursePreparationService(
        store=store,
        pool_service=_pool_service_for_required(required),
        general_required_courses=[required],
        fallback_elective_courses=[
            _course("ZE203-001", "다른영역", Category.GENERAL_ELECTIVE, "001", area=3),
        ],
    )
    app.dependency_overrides[get_general_course_preparation_service] = lambda: service
    client = TestClient(app)

    try:
        response = client.post(
            "/general/prepare",
            data={"session_id": session_id, "elective_area": "4"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "FALLBACK_ELECTIVE_AREA_NOT_FOUND"


def test_general_ready_session_can_prepare_again_with_different_area() -> None:
    store = SessionStore()
    session_id = _confirmed_session(store)
    required = _course("ZE100-001", "고전읽기와토론", Category.GENERAL_REQUIRED, "001")
    area_2 = _course("ZE202-001", "이전영역", Category.GENERAL_ELECTIVE, "001", area=2)
    area_4 = _course("ZE204-001", "새영역", Category.GENERAL_ELECTIVE, "001", area=4)
    service = GeneralCoursePreparationService(
        store=store,
        pool_service=_pool_service_for_required(required),
        general_required_courses=[required],
        fallback_elective_courses=[area_2, area_4],
    )
    app.dependency_overrides[get_general_course_preparation_service] = lambda: service
    client = TestClient(app)

    try:
        first = client.post(
            "/general/prepare",
            data={"session_id": session_id, "elective_area": "2"},
        )
        second = client.post(
            "/general/prepare",
            data={"session_id": session_id, "elective_area": "4"},
        )
    finally:
        app.dependency_overrides.clear()

    assert first.status_code == 200
    assert second.status_code == 200
    saved = store.get(session_id)
    assert saved.general_pool_elective_area == 4
    assert saved.general_elective_candidates == [area_4]
    assert area_2 not in saved.general_elective_candidates


def test_general_ready_session_can_replace_candidates_with_uploaded_catalog() -> None:
    store = SessionStore()
    session_id = _confirmed_session(store)
    required = _course("ZE100-001", "고전읽기와토론", Category.GENERAL_REQUIRED, "001")
    fallback = _course("ZE202-001", "기본교양", Category.GENERAL_ELECTIVE, "001", area=2)
    uploaded = _course("UP202-001", "업로드교양", Category.GENERAL_ELECTIVE, "001", area=2)
    parser = FakeElectiveParser([uploaded])
    service = GeneralCoursePreparationService(
        store=store,
        pool_service=_pool_service_for_required(required),
        general_required_courses=[required],
        fallback_elective_courses=[fallback],
        elective_parser=parser,
    )
    app.dependency_overrides[get_general_course_preparation_service] = lambda: service
    client = TestClient(app)

    try:
        first = client.post(
            "/general/prepare",
            data={"session_id": session_id, "elective_area": "2"},
        )
        second = client.post(
            "/general/prepare",
            data={"session_id": session_id, "elective_area": "2"},
            files={"elective_catalog": ("elective.xlsx", b"placeholder")},
        )
    finally:
        app.dependency_overrides.clear()

    assert first.status_code == 200
    assert second.status_code == 200
    saved = store.get(session_id)
    assert saved.general_pool_data_source == "uploaded_catalog"
    assert saved.general_elective_candidates == [uploaded]
    assert fallback not in saved.general_elective_candidates


def test_general_prepare_clears_downstream_data_when_reprepared() -> None:
    store = SessionStore()
    session_id = _confirmed_session(store)
    required = _course("ZE100-001", "고전읽기와토론", Category.GENERAL_REQUIRED, "001")
    area_2 = _course("ZE202-001", "이전영역", Category.GENERAL_ELECTIVE, "001", area=2)
    area_4 = _course("ZE204-001", "새영역", Category.GENERAL_ELECTIVE, "001", area=4)
    service = GeneralCoursePreparationService(
        store=store,
        pool_service=_pool_service_for_required(required),
        general_required_courses=[required],
        fallback_elective_courses=[area_2, area_4],
    )
    app.dependency_overrides[get_general_course_preparation_service] = lambda: service
    client = TestClient(app)

    try:
        client.post(
            "/general/prepare",
            data={"session_id": session_id, "elective_area": "2"},
        )
        timetable = Timetable(courses=[required, area_2])
        generated = TimetableGenerationCandidate(
            timetable=timetable,
            load_satisfaction=CourseLoadSatisfaction(elective_count=1),
        )
        store.update(
            session_id,
            generated_candidates=[timetable],
            generated_timetable_candidates=[generated],
            generation_diagnostics=[
                GenerationDiagnostic(reason_code="TEST", reason="테스트 진단", count=1),
            ],
            generation_course_load_target=CourseLoadTarget.mvp_default_policy(),
            latest_ranking_result=TimetableRankingResult(
                ranked_candidates=[RankingResult(timetable=timetable)],
                total_candidate_count=1,
            ),
            session_stage=SessionStage.RANKING_COMPLETED,
        )
        response = client.post(
            "/general/prepare",
            data={"session_id": session_id, "elective_area": "4"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    saved = store.get(session_id)
    assert saved.generated_candidates == []
    assert saved.generated_timetable_candidates == []
    assert saved.generation_diagnostics == []
    assert saved.latest_ranking_result is None
    assert saved.general_elective_candidates == [area_4]


def test_general_prepare_api_rejects_wrong_stage() -> None:
    store = SessionStore()
    session = store.create("컴퓨터공학과")
    required = _course("ZE100-001", "고전읽기와토론", Category.GENERAL_REQUIRED, "001")
    service = GeneralCoursePreparationService(
        store=store,
        pool_service=_pool_service_for_required(required),
        general_required_courses=[required],
        fallback_elective_courses=[
            _course("ZE200-001", "과학기술과사회", Category.GENERAL_ELECTIVE, "001", area=2),
        ],
    )
    app.dependency_overrides[get_general_course_preparation_service] = lambda: service
    client = TestClient(app)

    try:
        response = client.post(
            "/general/prepare",
            data={"session_id": session.session_id, "elective_area": "2"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_SESSION_STAGE"
