"""API tests for ``POST /recommend/generate``."""

from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.deps import get_timetable_generation_service
from backend.app.main import app
from backend.app.models import (
    Category,
    ClassTime,
    Course,
    CourseLoadTarget,
    Day,
    GeneralPreferenceParseResult,
    GeneralCoursePoolResult,
    GeneralCoursePools,
    PreferenceRules,
    PreferenceWarning,
    UnsupportedCondition,
    RankingTemplate,
)
from backend.app.services.session_store import SessionStage, SessionStore
from backend.app.services.timetable_generation_service import TimetableGenerationService
from backend.app.services.timetable_ranking_service import TimetableRankingService


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
    professor: str = "김교수",
) -> Course:
    return Course(
        course_id=course_id,
        course_name=name,
        category=category,
        area=area,
        credit=credit,
        division="001",
        professor=professor,
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


class FakeGeneralPreferenceParser:
    def __init__(self, result: GeneralPreferenceParseResult):
        self.result = result
        self.calls: list[str] = []

    def parse(self, prompt: str) -> GeneralPreferenceParseResult:
        self.calls.append(prompt)
        return self.result


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


def test_recommend_api_prompt_hard_conditions_reach_generator() -> None:
    store = SessionStore()
    session = store.create("컴퓨터공학과")
    store.update(
        session.session_id,
        fixed_courses=[
            _course("MAJ-001", "자료구조", Category.MAJOR_REQUIRED, credit=9, professor="박교수")
        ],
        confirmed_major_credits=9,
        session_stage=SessionStage.MAJOR_CONFIRMED,
    )
    kim_course = _course(
        "ELE-KIM",
        "철학의기초",
        Category.GENERAL_ELECTIVE,
        day=Day.TUE,
        start="10:00",
        end="11:00",
        area=1,
        professor="김교수",
    )
    lee_course = _course(
        "ELE-LEE",
        "과학기술과사회",
        Category.GENERAL_ELECTIVE,
        day=Day.WED,
        start="10:00",
        end="11:00",
        area=1,
        professor="이교수",
    )
    store.update_general_course_pool(
        session.session_id,
        GeneralCoursePoolResult(
            pools=GeneralCoursePools(elective_courses=[kim_course, lee_course])
        ),
    )
    parser = FakeGeneralPreferenceParser(
        GeneralPreferenceParseResult(
            hard_conditions=PreferenceRules(excluded_professors=["김교수"])
        )
    )
    service = TimetableGenerationService(store=store, preference_parser=parser)
    app.dependency_overrides[get_timetable_generation_service] = lambda: service
    client = TestClient(app)

    try:
        response = client.post(
            "/recommend/generate",
            json={
                "session_id": session.session_id,
                "target_total_credits": 12,
                "additional_elective_count": 1,
                "preference_prompt": "김교수 수업은 절대 넣지 마",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert parser.calls == ["김교수 수업은 절대 넣지 마"]
    assert body["hard_conditions"]["excluded_professors"] == ["김교수"]
    assert body["candidates"]
    for candidate in body["candidates"]:
        professors = [
            course["professor"]
            for course in candidate["timetable"]["courses"]
        ]
        assert "김교수" not in professors


def test_recommend_api_returns_unsupported_conditions_and_warnings() -> None:
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
            pools=GeneralCoursePools(elective_courses=[_elective()])
        ),
    )
    parser = FakeGeneralPreferenceParser(
        GeneralPreferenceParseResult(
            unsupported_conditions=[
                UnsupportedCondition(
                    source_text="과제가 적은 수업",
                    reason_code="DATA_NOT_AVAILABLE",
                    reason="현재 수강편람 데이터에서는 과제량을 확인할 수 없습니다.",
                )
            ],
            warnings=[
                PreferenceWarning(
                    code="AMBIGUOUS_CONDITION_STRENGTH",
                    message="애매한 표현을 soft 조건으로 해석했습니다.",
                    source_text="오전 수업은 싫어",
                )
            ],
        )
    )
    service = TimetableGenerationService(store=store, preference_parser=parser)
    app.dependency_overrides[get_timetable_generation_service] = lambda: service
    client = TestClient(app)

    try:
        response = client.post(
            "/recommend/generate",
            json={
                "session_id": session.session_id,
                "target_total_credits": 12,
                "additional_elective_count": 1,
                "preference_prompt": "과제가 적은 수업이면 좋고 오전 수업은 싫어",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["unsupported_conditions"][0]["reason_code"] == "DATA_NOT_AVAILABLE"
    assert body["warnings"][0]["code"] == "AMBIGUOUS_CONDITION_STRENGTH"


def test_empty_prompt_does_not_call_parser_and_keeps_generation_flow() -> None:
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
            pools=GeneralCoursePools(elective_courses=[_elective()])
        ),
    )
    parser = FakeGeneralPreferenceParser(GeneralPreferenceParseResult())
    service = TimetableGenerationService(store=store, preference_parser=parser)
    app.dependency_overrides[get_timetable_generation_service] = lambda: service
    client = TestClient(app)

    try:
        response = client.post(
            "/recommend/generate",
            json={
                "session_id": session.session_id,
                "target_total_credits": 12,
                "additional_elective_count": 1,
                "preference_prompt": "   ",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert parser.calls == []
    assert response.json()["candidates"]


def test_prompt_soft_conditions_reach_latest_ranking_service() -> None:
    store = SessionStore()
    session = store.create("컴퓨터공학과")
    store.update(
        session.session_id,
        fixed_courses=[
            _course("MAJ-001", "자료구조", Category.MAJOR_REQUIRED, day=Day.MON, credit=9)
        ],
        confirmed_major_credits=9,
        session_stage=SessionStage.MAJOR_CONFIRMED,
    )
    friday = _course(
        "ELE-FRI",
        "금요일수업",
        Category.GENERAL_ELECTIVE,
        day=Day.FRI,
        start="10:00",
        end="11:00",
        area=1,
    )
    wednesday = _course(
        "ELE-WED",
        "수요일수업",
        Category.GENERAL_ELECTIVE,
        day=Day.WED,
        start="10:00",
        end="11:00",
        area=1,
    )
    store.update_general_course_pool(
        session.session_id,
        GeneralCoursePoolResult(
            pools=GeneralCoursePools(elective_courses=[friday, wednesday])
        ),
    )
    parser = FakeGeneralPreferenceParser(
        GeneralPreferenceParseResult(
            soft_conditions=PreferenceRules(preferred_free_days=[Day.FRI])
        )
    )
    generation_service = TimetableGenerationService(store=store, preference_parser=parser)

    generation_service.generate_for_session(
        session_id=session.session_id,
        course_load_target=CourseLoadTarget(
            target_total_credits=12,
            additional_elective_count=1,
        ),
        preference_prompt="금요일은 가능하면 쉬고 싶어",
        max_candidates=10,
    )
    ranking = TimetableRankingService(store).rank_for_session(
        session_id=session.session_id,
        template=RankingTemplate.BALANCED,
        top_n=2,
    )

    assert store.get(session.session_id).ranking_preferences.preferred_free_days == [Day.FRI]
    assert ranking.ranked_candidates[0].timetable.courses[-1].course_id == "ELE-WED"
    assert any(
        component.key == "preferred_free_day"
        for component in ranking.ranked_candidates[0].score_components
    )


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

