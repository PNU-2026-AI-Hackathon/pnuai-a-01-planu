"""API tests for ``POST /recommend/rank``."""

from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.deps import get_timetable_ranking_service
from backend.app.main import app
from backend.app.models import (
    Category,
    ClassTime,
    Course,
    CourseLoadSatisfaction,
    Day,
    PreferenceRules,
    PreferenceWarning,
    Timetable,
    UnsupportedCondition,
)
from backend.app.services.session_store import SessionStage, SessionStore
from backend.app.services.timetable_ranking_service import TimetableRankingService


def _course(
    course_id: str,
    *,
    name: str | None = None,
    day: Day = Day.MON,
    start: str = "11:00",
    end: str = "12:00",
    category: Category = Category.GENERAL_ELECTIVE,
    area: int | None = 1,
) -> Course:
    return Course(
        course_id=course_id,
        course_name=name or f"강의 {course_id}",
        category=category,
        area=area,
        credit=3,
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


def _candidate(
    course_id: str,
    *,
    day: Day = Day.MON,
    start: str = "11:00",
    end: str = "12:00",
    required_groups: int = 1,
) -> Timetable:
    return Timetable(
        courses=[_course(course_id, day=day, start=start, end=end)],
        load_satisfaction=CourseLoadSatisfaction(
            final_total_credits=3,
            target_total_credits=3,
            satisfied_required_group_count=required_groups,
            requested_required_group_count=1,
            credit_gap=0,
        ),
    )


def _client_for(store: SessionStore) -> TestClient:
    service = TimetableRankingService(store)
    app.dependency_overrides[get_timetable_ranking_service] = lambda: service
    return TestClient(app)


def test_recommend_rank_api_returns_top_three_and_saves_session() -> None:
    store = SessionStore()
    session = store.create("컴퓨터공학과")
    candidates = [
        _candidate("GEN-A", day=Day.MON, start="11:00"),
        _candidate("GEN-B", day=Day.TUE, start="08:00"),
        _candidate("GEN-C", day=Day.WED, start="10:00"),
        _candidate("GEN-D", day=Day.THU, start="13:00", end="14:00"),
    ]
    store.update_generated_candidates(
        session.session_id,
        candidates=candidates,
        preferences=PreferenceRules(preferred_free_days=[Day.FRI]),
    )
    store.update(
        session.session_id,
        preference_unsupported_conditions=[
            UnsupportedCondition(
                source_text="과제가 적은 수업",
                reason_code="DATA_NOT_AVAILABLE",
                reason="현재 수강편람 데이터에서는 과제량을 확인할 수 없습니다.",
            )
        ],
        preference_warnings=[
            PreferenceWarning(
                code="AMBIGUOUS_CONDITION_STRENGTH",
                message="애매한 표현을 soft 조건으로 해석했습니다.",
                source_text="오전 수업은 싫어",
            )
        ],
    )
    client = _client_for(store)

    try:
        response = client.post(
            "/recommend/rank",
            json={"session_id": session.session_id},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == session.session_id
    assert body["template"] == "balanced"
    assert body["template_name"] == "균형형"
    assert body["template_description"]
    assert body["requested_top_n"] == 3
    assert body["returned_count"] == 3
    assert body["total_candidate_count"] == 4
    assert body["session_stage"] == "ranking_completed"
    assert [item["rank"] for item in body["ranked_candidates"]] == [1, 2, 3]
    assert body["unsupported_conditions"][0]["reason_code"] == "DATA_NOT_AVAILABLE"
    assert body["warnings"][0]["code"] == "AMBIGUOUS_CONDITION_STRENGTH"
    for item in body["ranked_candidates"]:
        component_sum = sum(
            component["value"] for component in item["score_components"]
        )
        assert item["raw_score"] == component_sum
        assert item["timetable"]["score"] == component_sum
        assert item["load_satisfaction"]["final_total_credits"] == 3

    saved = store.get(session.session_id)
    assert saved.session_stage is SessionStage.RANKING_COMPLETED
    assert saved.latest_ranking_result is not None
    assert saved.latest_ranking_result.template.value == "balanced"


def test_recommend_rank_api_honors_top_n_smaller_and_larger_than_candidates() -> None:
    store = SessionStore()
    session = store.create("컴퓨터공학과")
    store.update_generated_candidates(
        session.session_id,
        candidates=[_candidate("GEN-A"), _candidate("GEN-B", day=Day.TUE)],
    )
    client = _client_for(store)

    try:
        one = client.post(
            "/recommend/rank",
            json={"session_id": session.session_id, "top_n": 1},
        )
        many = client.post(
            "/recommend/rank",
            json={"session_id": session.session_id, "top_n": 10},
        )
    finally:
        app.dependency_overrides.clear()

    assert one.status_code == 200
    assert one.json()["returned_count"] == 1
    assert many.status_code == 200
    assert many.json()["requested_top_n"] == 10
    assert many.json()["returned_count"] == 2


def test_recommend_rank_api_rejects_invalid_top_n_with_standard_error() -> None:
    store = SessionStore()
    session = store.create("컴퓨터공학과")
    store.update_generated_candidates(session.session_id, candidates=[_candidate("GEN-A")])
    client = _client_for(store)

    try:
        response = client.post(
            "/recommend/rank",
            json={"session_id": session.session_id, "top_n": 0},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_TOP_N"


def test_recommend_rank_api_rejects_unknown_template_with_standard_error() -> None:
    store = SessionStore()
    session = store.create("컴퓨터공학과")
    store.update_generated_candidates(session.session_id, candidates=[_candidate("GEN-A")])
    client = _client_for(store)

    try:
        response = client.post(
            "/recommend/rank",
            json={"session_id": session.session_id, "template": "unknown_template"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "UNKNOWN_RANKING_TEMPLATE"


def test_recommend_rank_api_uses_only_session_candidates_and_forbids_client_scores() -> None:
    store = SessionStore()
    session = store.create("컴퓨터공학과")
    store.update_generated_candidates(session.session_id, candidates=[_candidate("GEN-A")])
    client = _client_for(store)

    try:
        response = client.post(
            "/recommend/rank",
            json={
                "session_id": session.session_id,
                "candidates": [{"raw_score": 999}],
                "weights": {"valid_candidate": 999},
                "soft_conditions": {"preferred_free_days": ["MON"]},
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert store.get(session.session_id).session_stage is SessionStage.CANDIDATES_GENERATED


def test_recommend_rank_api_returns_no_generated_candidates_error() -> None:
    store = SessionStore()
    session = store.create("컴퓨터공학과")
    store.update(session.session_id, session_stage=SessionStage.CANDIDATES_GENERATED)
    client = _client_for(store)

    try:
        response = client.post(
            "/recommend/rank",
            json={"session_id": session.session_id},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "NO_GENERATED_CANDIDATES"


def test_recommend_rank_api_returns_no_rankable_candidates_error() -> None:
    store = SessionStore()
    session = store.create("컴퓨터공학과")
    store.update_generated_candidates(
        session.session_id,
        candidates=[_candidate("GEN-FRI", day=Day.FRI)],
        preferences=PreferenceRules(excluded_days=[Day.FRI]),
    )
    client = _client_for(store)

    try:
        response = client.post(
            "/recommend/rank",
            json={"session_id": session.session_id},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "NO_RANKABLE_CANDIDATES"


def test_recommend_rank_api_rejects_sessions_before_generation() -> None:
    store = SessionStore()
    session = store.create("컴퓨터공학과")
    client = _client_for(store)

    try:
        response = client.post(
            "/recommend/rank",
            json={"session_id": session.session_id},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_SESSION_STAGE"


def test_recommend_rank_api_returns_missing_session_error() -> None:
    store = SessionStore()
    client = _client_for(store)

    try:
        response = client.post(
            "/recommend/rank",
            json={"session_id": "missing"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "SESSION_NOT_FOUND"
