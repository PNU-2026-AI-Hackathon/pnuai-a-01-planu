"""Session stage and request idempotency checks across HTTP routes."""

from __future__ import annotations

from pathlib import Path

from .conftest import prepare_generate_rank, upload_major


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

    assert confirm.status_code == 409
    assert confirm.json()["error"]["code"] == "INVALID_SESSION_STAGE"
    assert prepare.status_code == 409
    assert prepare.json()["error"]["code"] == "INVALID_SESSION_STAGE"
    assert generate.status_code == 400
    assert generate.json()["error"]["code"] == "INVALID_SESSION_STAGE"
    assert rank.status_code == 409
    assert rank.json()["error"]["code"] == "INVALID_SESSION_STAGE"

    preview = client.post(
        "/major/preview",
        json={"session_id": session_id, "prompt": "자료구조 001분반과 컴퓨터구조 003분반"},
    ).json()
    client.post("/major/confirm", json={"session_id": session_id, "preview_id": preview["preview_id"]})
    early_rank = client.post(
        "/recommend/rank",
        json={"session_id": session_id, "template": "balanced"},
    )
    assert early_rank.status_code == 409
    assert early_rank.json()["error"]["code"] == "INVALID_SESSION_STAGE"


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
    assert confirm.status_code == 409
    assert confirm.json()["error"]["code"] == "MAJOR_PREVIEW_NOT_CONFIRMABLE"
