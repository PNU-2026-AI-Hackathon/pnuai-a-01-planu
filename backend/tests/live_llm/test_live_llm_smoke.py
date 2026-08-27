"""Opt-in live LLM smoke tests across parser and HTTP API boundaries."""

from __future__ import annotations

import pytest

from .conftest import prepare_generate_rank, upload_major


pytestmark = pytest.mark.live_llm


def test_live_llm_environment_is_configured(live_llm_config) -> None:
    assert live_llm_config.model
    assert live_llm_config.openai_enabled is True
    assert live_llm_config.timeout_seconds > 0


def test_live_llm_full_http_api_flow(
    live_api_app,
    major_catalog_path,
    elective_catalog_path,
    trace_call,
) -> None:
    client = live_api_app.client
    upload = upload_major(client, major_catalog_path)
    session_id = upload["session_id"]

    preview = trace_call(
        "api_major_preview",
        "major_selection",
        lambda: client.post(
            "/major/preview",
            json={
                "session_id": session_id,
                "prompt": "자료구조 001분반과 컴퓨터구조 003분반을 들을 거야.",
            },
        ),
    )
    assert preview.status_code == 200, preview.text
    preview_body = preview.json()
    assert preview_body["can_confirm"] is True
    assert {item["course"]["course_name"] for item in preview_body["matched_courses"]} == {
        "자료구조",
        "컴퓨터구조",
    }

    confirm = client.post(
        "/major/confirm",
        json={"session_id": session_id, "preview_id": preview_body["preview_id"]},
    )
    assert confirm.status_code == 200, confirm.text

    prepare, generate, rank = trace_call(
        "api_general_generate_and_rank",
        "general_preference",
        lambda: prepare_generate_rank(
            client,
            session_id,
            elective_catalog_path,
            prompt=(
                "금요일은 가능하면 쉬고 싶고 오전 수업은 절대 안 돼.\n"
                "과제가 적은 수업이면 좋겠어."
            ),
        ),
    )
    assert prepare["session_stage"] == "general_ready"
    assert generate["hard_conditions"]["earliest_start_time"] == "10:00"
    assert generate["soft_conditions"]["preferred_free_days"] == ["FRI"]
    assert any("과제" in item["source_text"] for item in generate["unsupported_conditions"])
    assert rank["returned_count"] >= 1
    assert rank["unsupported_conditions"] == generate["unsupported_conditions"]
