"""HTTP integration tests for the complete PlaNU recommendation flow."""

from __future__ import annotations

from pathlib import Path

from backend.app.services.session_store import SessionStage

from .conftest import prepare_generate_rank, upload_major


def test_full_http_recommendation_flow_with_real_upload_parser(
    integration_app,
    major_catalog_path: Path,
    elective_catalog_path: Path,
) -> None:
    client = integration_app.client

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    upload = upload_major(client, major_catalog_path)
    session_id = upload["session_id"]
    assert session_id
    assert upload["session_stage"] == "catalog_parsed"
    assert upload["parsed_course_count"] == 3

    preview = client.post(
        "/major/preview",
        json={
            "session_id": session_id,
            "prompt": "자료구조 001분반과 컴퓨터구조 003분반을 들을 거야",
        },
    )
    assert preview.status_code == 200, preview.text
    preview_body = preview.json()
    preview_id = preview_body["preview_id"]
    assert [item["course"]["course_name"] for item in preview_body["matched_courses"]] == [
        "자료구조",
        "컴퓨터구조",
    ]
    assert preview_body["ambiguous_courses"] == []
    assert preview_body["unmatched_courses"] == []
    assert preview_body["has_time_conflict"] is False
    assert preview_body["can_confirm"] is True
    assert preview_body["matched_courses"][0]["course"]["class_times"][0]["day"] == "MON"
    assert integration_app.store.get(session_id, touch=False).session_stage is SessionStage.MAJOR_PREVIEW_CREATED

    confirm = client.post(
        "/major/confirm",
        json={"session_id": session_id, "preview_id": preview_id},
    )
    assert confirm.status_code == 200, confirm.text
    confirm_body = confirm.json()
    assert confirm_body["confirmed_course_count"] == 2
    assert confirm_body["confirmed_major_credits"] == 6
    assert confirm_body["session_stage"] == "major_confirmed"

    prepare, generate, rank = prepare_generate_rank(client, session_id, elective_catalog_path)
    assert prepare["session_stage"] == "general_ready"
    assert prepare["required_course_count"] == 2
    assert prepare["elective_course_count"] == 4
    assert prepare["excluded_course_count"] == 0
    assert prepare["data_source"] == "uploaded_catalog"

    assert generate["session_stage"] == "candidates_generated"
    assert generate["candidates"]
    assert generate["truncated"] is False
    assert generate["soft_conditions"]["preferred_free_days"] == ["FRI"]
    assert generate["warnings"][0]["code"] == "SOFT_CONDITION_APPLIED"
    for candidate in generate["candidates"]:
        courses = candidate["timetable"]["courses"]
        assert {"자료구조", "컴퓨터구조"}.issubset({course["course_name"] for course in courses})
        assert candidate["load_satisfaction"]["within_credit_limit"] is True
        assert candidate["load_satisfaction"]["requested_elective_count"] == 1
    assert any(
        candidate["load_satisfaction"]["elective_count"] == 1
        for candidate in generate["candidates"]
    )

    assert rank["session_stage"] == "ranking_completed"
    assert rank["template"] == "balanced"
    assert rank["template_name"]
    assert 1 <= rank["returned_count"] <= 3
    assert [item["rank"] for item in rank["ranked_candidates"]] == list(
        range(1, rank["returned_count"] + 1)
    )
    for item in rank["ranked_candidates"]:
        component_sum = sum(component["value"] for component in item["score_components"])
        assert item["raw_score"] == component_sum
        assert item["timetable"]["score"] == component_sum
        assert item["load_satisfaction"]["final_total_credits"] <= 14
        names = {course["course_name"] for course in item["timetable"]["courses"]}
        assert {"자료구조", "컴퓨터구조"}.issubset(names)
    assert integration_app.store.get(session_id, touch=False).session_stage is SessionStage.RANKING_COMPLETED


def test_template_reranking_reuses_generated_candidates(
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
    client.post("/major/confirm", json={"session_id": session_id, "preview_id": preview["preview_id"]})
    _, generate, balanced = prepare_generate_rank(client, session_id, elective_catalog_path)
    generated_ids = [
        [course["course_id"] for course in candidate["timetable"]["courses"]]
        for candidate in generate["candidates"]
    ]
    parser_calls_after_generate = list(integration_app.preference_parser.calls)

    free_day = client.post(
        "/recommend/rank",
        json={"session_id": session_id, "template": "free_day_priority", "top_n": 3},
    )
    no_morning = client.post(
        "/recommend/rank",
        json={"session_id": session_id, "template": "no_morning_priority", "top_n": 3},
    )
    balanced_again = client.post(
        "/recommend/rank",
        json={"session_id": session_id, "template": "balanced", "top_n": 3},
    )

    assert free_day.status_code == 200, free_day.text
    assert no_morning.status_code == 200, no_morning.text
    assert balanced_again.status_code == 200, balanced_again.text
    assert integration_app.preference_parser.calls == parser_calls_after_generate
    saved_ids = [
        [course.course_id for course in candidate.courses]
        for candidate in integration_app.store.get(session_id).generated_candidates
    ]
    assert saved_ids == generated_ids
    assert balanced_again.json()["ranked_candidates"] == balanced["ranked_candidates"]


def test_unsupported_condition_survives_until_rank_response(
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
    client.post("/major/confirm", json={"session_id": session_id, "preview_id": preview["preview_id"]})

    _, generate, rank = prepare_generate_rank(
        client,
        session_id,
        elective_catalog_path,
        prompt="금요일은 가능하면 쉬고 싶고 과제가 적은 수업을 듣고 싶어",
    )

    assert generate["soft_conditions"]["preferred_free_days"] == ["FRI"]
    assert generate["unsupported_conditions"][0]["source_text"] == "과제가 적은 수업"
    assert rank["unsupported_conditions"] == generate["unsupported_conditions"]
