"""Integration coverage for general-course restrictions and fallback data."""

from __future__ import annotations

from pathlib import Path

from backend.app.deps import get_general_course_preparation_service
from backend.app.main import app
from backend.app.services.general_course_pool_service import (
    GeneralCoursePoolService,
    GeneralCoursePreparationService,
)

from .conftest import prepare_generate_rank, run_until_confirmed


def test_department_restrictions_include_all_required_courses_for_allowed_department(
    integration_app,
    major_catalog_path: Path,
) -> None:
    client = integration_app.client
    session_id, _ = run_until_confirmed(client, major_catalog_path, department="컴퓨터공학과")

    response = client.post(
        "/general/prepare",
        data={"session_id": session_id, "elective_area": "2"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["required_course_count"] == 2
    assert response.json()["data_source"] == "fallback_catalog"
    assert {course.course_id for course in integration_app.store.get(session_id).general_required_candidates} == {
        "GR101-001",
        "GR102-001",
    }


def test_department_restrictions_filter_partially_allowed_department(
    integration_app,
    second_major_catalog_path: Path,
) -> None:
    client = integration_app.client
    session_id, _ = run_until_confirmed(client, second_major_catalog_path, department="전자공학과")

    response = client.post(
        "/general/prepare",
        data={"session_id": session_id, "elective_area": "2"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["required_course_count"] == 1
    assert body["excluded_course_count"] == 1
    assert [course.course_id for course in integration_app.store.get(session_id).general_required_candidates] == [
        "GR101-001"
    ]


def test_department_restrictions_with_no_allowed_required_courses_return_diagnostics_not_500(
    integration_app,
    major_catalog_path: Path,
) -> None:
    client = integration_app.client
    session_id, _ = run_until_confirmed(client, major_catalog_path, department="기계공학과")

    response = client.post(
        "/general/prepare",
        data={"session_id": session_id, "elective_area": "2"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["required_course_count"] == 0
    assert body["excluded_course_count"] == 2
    diagnostics = integration_app.store.get(session_id).general_pool_diagnostics
    assert {item.reason_code for item in diagnostics} == {"DEPARTMENT_NOT_ELIGIBLE"}


def test_general_prepare_without_upload_uses_fallback_and_can_generate_and_rank(
    integration_app,
    major_catalog_path: Path,
) -> None:
    client = integration_app.client
    session_id, _ = run_until_confirmed(client, major_catalog_path)

    prepare = client.post(
        "/general/prepare",
        data={"session_id": session_id, "elective_area": "2"},
    )
    assert prepare.status_code == 200, prepare.text
    assert prepare.json()["data_source"] == "fallback_catalog"
    assert prepare.json()["elective_course_count"] == 1
    assert [course.area for course in integration_app.store.get(session_id).general_elective_candidates] == [2]

    generate = client.post(
        "/recommend/generate",
        json={
            "session_id": session_id,
            "target_total_credits": 14,
            "additional_elective_count": 1,
            "preference_prompt": "금요일은 가능하면 쉬고 싶어",
        },
    )
    assert generate.status_code == 200, generate.text
    assert generate.json()["candidates"]

    rank = client.post(
        "/recommend/rank",
        json={"session_id": session_id, "template": "balanced", "top_n": 3},
    )
    assert rank.status_code == 200, rank.text
    assert rank.json()["ranked_candidates"]


def test_general_prepare_without_upload_errors_when_fallback_data_is_missing(
    integration_app,
    major_catalog_path: Path,
) -> None:
    client = integration_app.client
    session_id, _ = run_until_confirmed(client, major_catalog_path)
    original = app.dependency_overrides[get_general_course_preparation_service]
    app.dependency_overrides[get_general_course_preparation_service] = lambda: GeneralCoursePreparationService(
        store=integration_app.store,
        pool_service=GeneralCoursePoolService(),
        general_required_courses=[],
        fallback_elective_courses=[],
    )
    try:
        response = client.post(
            "/general/prepare",
            data={"session_id": session_id, "elective_area": "2"},
        )
    finally:
        app.dependency_overrides[get_general_course_preparation_service] = original

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "FALLBACK_ELECTIVE_DATA_NOT_FOUND"
