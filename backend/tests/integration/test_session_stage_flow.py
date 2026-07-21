"""Session stage and request idempotency checks across HTTP routes."""

from __future__ import annotations

from pathlib import Path

from .conftest import prepare_generate_rank, upload_major


def _assert_error(response, *, status_code: int, code: str) -> None:
    assert response.status_code == status_code
    body = response.json()
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message", "hint", "details"}
    assert body["error"]["code"] == code
    assert isinstance(body["error"]["details"], dict)


def test_major_preview_detects_time_conflicts_and_confirm_rejects_them(
    integration_app,
    conflicting_major_catalog_path: Path,
) -> None:
    client = integration_app.client
    session_id = upload_major(client, conflicting_major_catalog_path)["session_id"]

    preview = client.post(
        "/major/preview",
        json={"session_id": session_id, "prompt": "자료구조 001분반과 컴퓨터구조 003분반"},
    )
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["has_time_conflict"] is True
    assert body["can_confirm"] is False
    assert body["conflicts"]
    assert {
        body["conflicts"][0]["first_course_id"],
        body["conflicts"][0]["second_course_id"],
    } == {"MA100-001", "MA200-003"}

    confirm = client.post(
        "/major/confirm",
        json={"session_id": session_id, "preview_id": body["preview_id"]},
    )
    _assert_error(confirm, status_code=409, code="MAJOR_TIME_CONFLICT")


def test_wrong_stage_requests_are_rejected(
    integration_app,
    major_catalog_path: Path,
    elective_catalog_path: Path,
) -> None:
    client = integration_app.client
    session_id = upload_major(client, major_catalog_path)["session_id"]

    confirm = client.post(
        "/major/confirm",
        json={"session_id": session_id, "preview_id": "missing-preview"},
    )
    prepare = client.post(
        "/general/prepare",
        data={"session_id": session_id, "elective_area": "2"},
    )
    generate = client.post(
        "/recommend/generate",
        json={"session_id": session_id, "target_total_credits": 14},
    )
    rank = client.post(
        "/recommend/rank",
        json={"session_id": session_id, "template": "balanced"},
    )

    _assert_error(confirm, status_code=409, code="INVALID_SESSION_STAGE")
    _assert_error(prepare, status_code=409, code="INVALID_SESSION_STAGE")
    _assert_error(generate, status_code=400, code="INVALID_SESSION_STAGE")
    _assert_error(rank, status_code=409, code="INVALID_SESSION_STAGE")

    preview = client.post(
        "/major/preview",
        json={"session_id": session_id, "prompt": "자료구조 001분반과 컴퓨터구조 003분반"},
    ).json()
    client.post("/major/confirm", json={"session_id": session_id, "preview_id": preview["preview_id"]})
    early_rank = client.post(
        "/recommend/rank",
        json={"session_id": session_id, "template": "balanced"},
    )
    _assert_error(early_rank, status_code=409, code="INVALID_SESSION_STAGE")


def test_duplicate_confirm_and_rank_do_not_mutate_session(
    integration_app,
    major_catalog_path: Path,
    elective_catalog_path: Path,
) -> None:
    client = integration_app.client
    session_id = upload_major(client, major_catalog_path)["session_id"]
    preview = client.post(
        "/major/preview",
        json={"session_id": session_id, "prompt": "자료구조 001분반과 컴퓨터구조 003분반"},
    ).json()

    first_confirm = client.post(
        "/major/confirm",
        json={"session_id": session_id, "preview_id": preview["preview_id"]},
    )
    second_confirm = client.post(
        "/major/confirm",
        json={"session_id": session_id, "preview_id": preview["preview_id"]},
    )
    assert first_confirm.status_code == 200
    assert second_confirm.status_code == 200
    assert second_confirm.json()["confirmed_course_count"] == 2
    assert integration_app.store.get(session_id).confirmed_major_credits == 6

    _, _, first_rank = prepare_generate_rank(client, session_id, elective_catalog_path)
    second_rank = client.post(
        "/recommend/rank",
        json={"session_id": session_id, "template": "balanced", "top_n": 3},
    )
    assert second_rank.status_code == 200, second_rank.text
    assert second_rank.json()["ranked_candidates"] == first_rank["ranked_candidates"]


def test_ambiguous_preview_can_not_be_confirmed(
    integration_app,
    major_catalog_path: Path,
) -> None:
    client = integration_app.client
    session_id = upload_major(client, major_catalog_path)["session_id"]
    preview = client.post(
        "/major/preview",
        json={"session_id": session_id, "prompt": "자료구조를 분반 없이 들을 거야"},
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["can_confirm"] is False
    assert preview.json()["ambiguous_courses"]

    confirm = client.post(
        "/major/confirm",
        json={"session_id": session_id, "preview_id": preview.json()["preview_id"]},
    )
    _assert_error(confirm, status_code=409, code="MAJOR_PREVIEW_NOT_CONFIRMABLE")


def test_additional_http_error_boundaries_use_standard_error_shape(
    integration_app,
    major_catalog_path: Path,
    elective_catalog_path: Path,
) -> None:
    client = integration_app.client
    session_id = upload_major(client, major_catalog_path)["session_id"]

    blank_prompt = client.post(
        "/major/preview",
        json={"session_id": session_id, "prompt": "   "},
    )
    missing_major = client.post(
        "/major/preview",
        json={"session_id": session_id, "prompt": "운영체제 001분반"},
    )
    assert missing_major.status_code == 200, missing_major.text
    assert missing_major.json()["unmatched_courses"]
    assert missing_major.json()["can_confirm"] is False
    _assert_error(blank_prompt, status_code=422, code="REQUEST_VALIDATION_ERROR")

    preview = client.post(
        "/major/preview",
        json={"session_id": session_id, "prompt": "자료구조 001분반과 컴퓨터구조 003분반"},
    ).json()
    client.post("/major/confirm", json={"session_id": session_id, "preview_id": preview["preview_id"]})

    too_low_area = client.post(
        "/general/prepare",
        data={"session_id": session_id, "elective_area": "0"},
    )
    too_high_area = client.post(
        "/general/prepare",
        data={"session_id": session_id, "elective_area": "10"},
    )
    damaged_elective = client.post(
        "/general/prepare",
        data={"session_id": session_id, "elective_area": "2"},
        files={"elective_catalog": ("elective.xlsx", b"not an xlsx")},
    )
    oversized_elective = client.post(
        "/general/prepare",
        data={"session_id": session_id, "elective_area": "2"},
        files={"elective_catalog": ("elective.xlsx", b"x" * (5 * 1024 * 1024 + 1))},
    )
    _assert_error(too_low_area, status_code=400, code="INVALID_ELECTIVE_AREA")
    _assert_error(too_high_area, status_code=400, code="INVALID_ELECTIVE_AREA")
    _assert_error(damaged_elective, status_code=400, code="INVALID_EXCEL_FILE")
    _assert_error(oversized_elective, status_code=413, code="FILE_TOO_LARGE")

    prepare_generate_rank(client, session_id, elective_catalog_path)
    unknown_template = client.post(
        "/recommend/rank",
        json={"session_id": session_id, "template": "unknown_template"},
    )
    zero_top_n = client.post(
        "/recommend/rank",
        json={"session_id": session_id, "top_n": 0},
    )
    too_large_top_n = client.post(
        "/recommend/rank",
        json={"session_id": session_id, "top_n": 11},
    )
    _assert_error(unknown_template, status_code=400, code="UNKNOWN_RANKING_TEMPLATE")
    _assert_error(zero_top_n, status_code=400, code="INVALID_TOP_N")
    _assert_error(too_large_top_n, status_code=400, code="INVALID_TOP_N")
