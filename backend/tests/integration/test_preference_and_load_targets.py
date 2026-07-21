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
    if additional_elective_count == 2:
        assert any(
            diagnostic["reason_code"] in {"ELECTIVE_TARGET_NOT_MET", "CREDIT_TARGET_PRUNED"}
            for diagnostic in generate["diagnostics"]
        )
    if additional_elective_count == 1:
        assert any(
            candidate["load_satisfaction"]["elective_count"] == 1
            for candidate in generate["candidates"]
        )
