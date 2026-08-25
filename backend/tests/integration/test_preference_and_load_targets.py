"""HTTP integration checks for hard/soft preferences and load targets."""

from __future__ import annotations

from pathlib import Path

import pytest

from .conftest import prepare_generate_rank, run_until_confirmed


def test_hard_friday_condition_filters_generated_candidates(
    integration_app,
    major_catalog_path: Path,
    elective_catalog_path: Path,
) -> None:
    client = integration_app.client
    session_id, _ = run_until_confirmed(client, major_catalog_path)

    _, generate, rank = prepare_generate_rank(
        client,
        session_id,
        elective_catalog_path,
        prompt="금요일 수업은 절대 안 돼",
    )

    assert generate["hard_conditions"]["excluded_days"] == ["FRI"]
    for candidate in generate["candidates"]:
        days = {
            meeting["day"]
            for course in candidate["timetable"]["courses"]
            for meeting in course["class_times"]
        }
        assert "FRI" not in days
    assert rank["ranked_candidates"]


def test_soft_friday_condition_keeps_valid_friday_candidates_but_ranks_free_day_high(
    integration_app,
    major_catalog_path: Path,
    elective_catalog_path: Path,
) -> None:
    client = integration_app.client
    session_id, _ = run_until_confirmed(client, major_catalog_path)

    _, generate, rank = prepare_generate_rank(
        client,
        session_id,
        elective_catalog_path,
        prompt="금요일은 가능하면 쉬고 싶어",
    )

    assert generate["soft_conditions"]["preferred_free_days"] == ["FRI"]
    generated_has_friday = any(
        meeting["day"] == "FRI"
        for candidate in generate["candidates"]
        for course in candidate["timetable"]["courses"]
        for meeting in course["class_times"]
    )
    assert generated_has_friday is True
    top_days = {
        meeting["day"]
        for course in rank["ranked_candidates"][0]["timetable"]["courses"]
        for meeting in course["class_times"]
    }
    assert "FRI" not in top_days
    assert any(
        component["key"] == "preferred_free_day"
        for component in rank["ranked_candidates"][0]["score_components"]
    )


@pytest.mark.parametrize(
    ("target_total_credits", "additional_elective_count"),
    [
        (None, None),
        (14, None),
        (None, 1),
        (14, 2),
    ],
)
def test_course_load_target_combinations_flow_over_http(
    integration_app,
    major_catalog_path: Path,
    elective_catalog_path: Path,
    target_total_credits: float | None,
    additional_elective_count: int | None,
) -> None:
    client = integration_app.client
    session_id, _ = run_until_confirmed(client, major_catalog_path)

    _, generate, rank = prepare_generate_rank(
        client,
        session_id,
        elective_catalog_path,
        target_total_credits=target_total_credits,
        additional_elective_count=additional_elective_count,
    )

    assert generate["candidates"]
    for candidate in generate["candidates"]:
        load = candidate["load_satisfaction"]
        if target_total_credits is not None:
            assert load["final_total_credits"] <= target_total_credits
            assert load["within_credit_limit"] is True
        if additional_elective_count is not None:
            assert load["requested_elective_count"] == additional_elective_count
    assert rank["ranked_candidates"]
    if target_total_credits is None and additional_elective_count is None:
        assert all(
            candidate["load_satisfaction"]["elective_count"] == 0
            for candidate in generate["candidates"]
        )
    if additional_elective_count == 2 and not any(
        candidate["load_satisfaction"]["elective_count"] >= additional_elective_count
        for candidate in generate["candidates"]
    ):
        assert any(
            diagnostic["reason_code"] in {"ELECTIVE_TARGET_NOT_MET", "CREDIT_TARGET_PRUNED"}
            for diagnostic in generate["diagnostics"]
        )
    if additional_elective_count == 1:
        assert any(
            candidate["load_satisfaction"]["elective_count"] == 1
            for candidate in generate["candidates"]
        )


def test_generation_returns_reachable_target_credit_candidate_not_only_lower_loads(
    integration_app,
    major_catalog_path: Path,
    elective_catalog_path: Path,
) -> None:
    client = integration_app.client
    session_id, _ = run_until_confirmed(client, major_catalog_path)

    _, generate, rank = prepare_generate_rank(
        client,
        session_id,
        elective_catalog_path,
        target_total_credits=13,
        additional_elective_count=1,
    )

    final_credits = [
        candidate["load_satisfaction"]["final_total_credits"]
        for candidate in generate["candidates"]
    ]
    assert max(final_credits) == 13
    assert all(value <= 13 for value in final_credits)
    assert rank["ranked_candidates"][0]["load_satisfaction"]["final_total_credits"] == 13


def test_hard_condition_that_removes_all_candidates_returns_empty_generation_diagnostic(
    integration_app,
    major_catalog_path: Path,
    elective_catalog_path: Path,
) -> None:
    client = integration_app.client
    session_id, _ = run_until_confirmed(client, major_catalog_path)
    with elective_catalog_path.open("rb") as stream:
        prepare = client.post(
            "/general/prepare",
            data={"session_id": session_id, "elective_area": "2"},
            files={
                "elective_catalog": (
                    elective_catalog_path.name,
                    stream,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
    assert prepare.status_code == 200, prepare.text

    generate = client.post(
        "/recommend/generate",
        json={
            "session_id": session_id,
            "target_total_credits": 13,
            "additional_elective_count": 1,
            "hard_conditions": {"required_course_names": ["존재하지않는교양"]},
            "max_candidates": 100,
        },
    )

    assert generate.status_code == 200, generate.text
    body = generate.json()
    assert body["candidates"] == []
    assert any(
        diagnostic["reason_code"] == "ALL_CANDIDATES_HARD_CONDITION_FAILED"
        for diagnostic in body["diagnostics"]
    )


def test_regenerating_candidates_clears_previous_ranking_and_replaces_candidates(
    integration_app,
    major_catalog_path: Path,
    elective_catalog_path: Path,
) -> None:
    client = integration_app.client
    session_id, _ = run_until_confirmed(client, major_catalog_path)

    _, first_generate, first_rank = prepare_generate_rank(
        client,
        session_id,
        elective_catalog_path,
        target_total_credits=13,
        additional_elective_count=1,
    )
    assert first_rank["ranked_candidates"]
    assert integration_app.store.get(session_id).latest_ranking_result is not None
    first_candidate_sets = [
        sorted(course["course_id"] for course in candidate["timetable"]["courses"])
        for candidate in first_generate["candidates"]
    ]

    second_generate = client.post(
        "/recommend/generate",
        json={
            "session_id": session_id,
            "target_total_credits": 10,
            "additional_elective_count": 0,
            "preference_prompt": "금요일 수업은 절대 안 돼",
            "max_candidates": 100,
        },
    )

    assert second_generate.status_code == 200, second_generate.text
    assert integration_app.store.get(session_id).latest_ranking_result is None
    second_candidate_sets = [
        sorted(course["course_id"] for course in candidate["timetable"]["courses"])
        for candidate in second_generate.json()["candidates"]
    ]
    assert second_candidate_sets != first_candidate_sets
    assert all(
        candidate["load_satisfaction"]["requested_elective_count"] == 0
        for candidate in second_generate.json()["candidates"]
    )

    third_generate = client.post(
        "/recommend/generate",
        json={
            "session_id": session_id,
            "target_total_credits": 10,
            "additional_elective_count": 0,
            "preference_prompt": "금요일 수업은 절대 안 돼",
            "max_candidates": 100,
        },
    )
    assert third_generate.status_code == 200, third_generate.text
    assert [
        sorted(course["course_id"] for course in candidate["timetable"]["courses"])
        for candidate in third_generate.json()["candidates"]
    ] == second_candidate_sets
