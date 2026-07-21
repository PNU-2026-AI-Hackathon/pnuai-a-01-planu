"""HTTP integration tests for campus travel rules during generation."""

from __future__ import annotations

from pathlib import Path

from backend.app.deps import get_timetable_generation_service
from backend.app.main import app
from backend.app.services.campus_rule_engine import CampusRuleEngine
from backend.app.services.timetable_generation_service import TimetableGenerationService
from backend.app.services.timetable_generator import TimetableGenerator
from backend.app.services.timetable_validator import TimetableValidator

from .conftest import run_until_confirmed, write_catalog


def test_campus_travel_rules_remove_impossible_back_to_back_candidates(
    integration_app,
    major_catalog_path: Path,
    tmp_path: Path,
) -> None:
    client = integration_app.client
    session_id, _ = run_until_confirmed(client, major_catalog_path)
    elective_path = tmp_path / "movement-electives.xlsx"
    write_catalog(
        elective_path,
        [
            ["교양선택", "같은건물연강", "GM301", "001", 3, "이교수", "월 10:15-11:00 609-501"],
            ["교양선택", "이동가능연강", "GM302", "001", 3, "박교수", "월 10:30-11:15 700-201"],
            ["교양선택", "이동불가연강", "GM303", "001", 3, "최교수", "월 10:20-11:05 999-101"],
        ],
    )
    campus_rules = CampusRuleEngine(
        {
            "building_zones": {
                "609": "ENGINEERING",
                "700": "NEAR",
                "999": "FAR",
            },
            "travel_times": {
                "ENGINEERING": {"NEAR": 10, "FAR": 20},
            },
            "same_zone_travel_minutes": 0,
            "default_travel_minutes": 20,
        }
    )
    original_generation_override = app.dependency_overrides[get_timetable_generation_service]
    app.dependency_overrides[get_timetable_generation_service] = lambda: TimetableGenerationService(
        store=integration_app.store,
        preference_parser=integration_app.preference_parser,
        generator=TimetableGenerator(
            validator=TimetableValidator(campus_rules),
        ),
    )

    try:
        with elective_path.open("rb") as stream:
            prepare = client.post(
                "/general/prepare",
                data={"session_id": session_id, "elective_area": "2"},
                files={
                    "elective_catalog": (
                        elective_path.name,
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
                "target_total_credits": 14,
                "additional_elective_count": 1,
                "max_candidates": 100,
            },
        )
        assert generate.status_code == 200, generate.text
        body = generate.json()
        generated_course_ids = {
            course["course_id"]
            for candidate in body["candidates"]
            for course in candidate["timetable"]["courses"]
        }
        assert "GM301-001" in generated_course_ids
        assert "GM302-001" in generated_course_ids
        assert "GM303-001" not in generated_course_ids
        assert any(
            diagnostic["reason_code"] == "ALL_CANDIDATES_MOVEMENT_INVALID"
            and diagnostic["count"] >= 1
            for diagnostic in body["diagnostics"]
        )

        rank = client.post(
            "/recommend/rank",
            json={"session_id": session_id, "template": "balanced", "top_n": 3},
        )
        assert rank.status_code == 200, rank.text
        assert rank.json()["ranked_candidates"]
    finally:
        app.dependency_overrides[get_timetable_generation_service] = original_generation_override
