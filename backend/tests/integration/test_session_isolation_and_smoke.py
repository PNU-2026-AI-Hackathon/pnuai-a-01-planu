"""Isolation, expiry, failure, and schema smoke tests for HTTP integration."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from .conftest import prepare_generate_rank, run_until_confirmed, upload_major


def test_two_user_sessions_remain_isolated(
    integration_app,
    major_catalog_path: Path,
    second_major_catalog_path: Path,
    elective_catalog_path: Path,
) -> None:
    client = integration_app.client
    session_a, _ = run_until_confirmed(client, major_catalog_path, department="컴퓨터공학과")
    upload_b = upload_major(client, second_major_catalog_path, department="전자공학과")
    session_b = upload_b["session_id"]
    preview_b = client.post(
        "/major/preview",
        json={"session_id": session_b, "prompt": "자료구조 001분반과 컴퓨터구조 003분반"},
    )
    assert preview_b.status_code == 200, preview_b.text

    assert session_a != session_b
    assert {
        course.course_id for course in integration_app.store.get(session_a).fixed_courses
    } == {"MA100-001", "MA200-003"}

    preview_a = integration_app.store.get(session_a).confirmed_major_preview_id
    cross_confirm = client.post(
        "/major/confirm",
        json={"session_id": session_b, "preview_id": preview_a},
    )
    assert cross_confirm.status_code == 409
    assert cross_confirm.json()["error"]["code"] == "STALE_MAJOR_PREVIEW"

    confirm_b = client.post(
        "/major/confirm",
        json={"session_id": session_b, "preview_id": preview_b.json()["preview_id"]},
    )
    assert confirm_b.status_code == 200, confirm_b.text
    assert {
        course.course_id for course in integration_app.store.get(session_b).fixed_courses
    } == {"MA300-001", "MA400-003"}

    prepare_generate_rank(client, session_a, elective_catalog_path)
    prepare_generate_rank(client, session_b, elective_catalog_path)
    assert integration_app.store.get(session_a).latest_ranking_result is not None
    assert integration_app.store.get(session_b).latest_ranking_result is not None
    assert integration_app.store.get(session_a).fixed_courses != integration_app.store.get(session_b).fixed_courses


def test_expired_session_returns_standard_error_without_affecting_other_session(
    integration_app,
    major_catalog_path: Path,
) -> None:
    client = integration_app.client
    expired_session = upload_major(client, major_catalog_path)["session_id"]

    integration_app.clock.advance(timedelta(minutes=31))
    expired = client.post(
        "/major/preview",
        json={"session_id": expired_session, "prompt": "자료구조 001분반"},
    )
    assert expired.status_code == 404
    assert expired.json()["error"]["code"] == "SESSION_NOT_FOUND"

    live_session = upload_major(client, major_catalog_path)["session_id"]
    live = client.post(
        "/major/preview",
        json={"session_id": live_session, "prompt": "자료구조 001분반과 컴퓨터구조 003분반"},
    )
    assert live.status_code == 200, live.text


def test_upload_failures_use_standard_error_and_do_not_create_session(integration_app) -> None:
    client = integration_app.client

    missing = client.post("/catalog/major", data={"department": "컴퓨터공학과"})
    invalid_ext = client.post(
        "/catalog/major",
        data={"department": "컴퓨터공학과"},
        files={"major_catalog": ("major.csv", b"placeholder")},
    )
    damaged = client.post(
        "/catalog/major",
        data={"department": "컴퓨터공학과"},
        files={"major_catalog": ("major.xlsx", b"not a zip file")},
    )
    oversized = client.post(
        "/catalog/major",
        data={"department": "컴퓨터공학과"},
        files={"major_catalog": ("major.xlsx", b"x" * (5 * 1024 * 1024 + 1))},
    )

    assert missing.status_code == 400
    assert missing.json()["error"]["code"] == "MAJOR_CATALOG_REQUIRED"
    assert invalid_ext.status_code == 400
    assert invalid_ext.json()["error"]["code"] == "INVALID_FILE_EXTENSION"
    assert damaged.status_code == 400
    assert damaged.json()["error"]["code"] == "INVALID_EXCEL_FILE"
    assert oversized.status_code == 413
    assert oversized.json()["error"]["code"] == "FILE_TOO_LARGE"
    assert len(integration_app.store) == 0


def test_openapi_and_app_smoke(integration_app) -> None:
    response = integration_app.client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    paths = schema["paths"]
    for path in (
        "/catalog/major",
        "/major/preview",
        "/major/confirm",
        "/general/prepare",
        "/recommend/generate",
        "/recommend/rank",
    ):
        assert path in paths
    assert paths["/catalog/major"]["post"]["requestBody"]["content"]["multipart/form-data"]
    assert paths["/recommend/generate"]["post"]["requestBody"]["content"]["application/json"]
