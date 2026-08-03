"""Run raw Excel recommendation examples without starting uvicorn.

Usage from the repository root:

    python -m backend.tests.manual_raw_excel_examples

The script uses FastAPI's TestClient in-process, reads files from
backend/data/raw, and calls the same route handlers used by the server.
Set OPENAI_API_KEY and OPENAI_MODEL in backend/.env before running examples
with non-empty preference prompts.
"""

from __future__ import annotations

import json
import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from backend.app.deps import (
    get_general_course_preparation_service,
    get_session_store,
    get_timetable_generation_service,
    get_timetable_ranking_service,
)
from backend.app.main import app
from backend.app.models import Category, ClassTime, Course, Day
from backend.app.services.course_parser import parse_catalog_workbook, parse_restrictions
from backend.app.services.general_course_pool_service import (
    CourseRestrictionPolicy,
    GeneralCoursePoolService,
    GeneralCoursePreparationService,
)
from backend.app.services.ranking_template_service import RankingTemplateService
from backend.app.services.session_store import SessionStage, SessionStore
from backend.app.services.timetable_generation_service import TimetableGenerationService
from backend.app.services.timetable_ranker import TimetableRanker
from backend.app.services.timetable_ranking_service import TimetableRankingService
from backend.app.services.uploaded_catalog_parser import UploadedCatalogParser


ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "backend" / "data" / "raw"


@dataclass(frozen=True)
class RawExcelExample:
    name: str
    area: int
    prompt: str
    target_total_credits: float = 14
    additional_elective_count: int = 1
    template: str = "balanced"

    @property
    def elective_path(self) -> Path:
        return RAW_DIR / f"general_elective_area_{self.area}.xlsx"


EXAMPLES = [
    RawExcelExample(
        name="area_1_friday_free",
        area=1,
        prompt="금요일은 가능하면 공강이면 좋고, 오전 10시 이전 수업은 피하고 싶어.",
        template="free_day_priority",
    ),
    RawExcelExample(
        name="area_2_no_morning",
        area=2,
        prompt="오전 10시 이전 수업은 절대 넣지 말고, 수업일은 적을수록 좋아.",
        template="no_morning_priority",
    ),
    RawExcelExample(
        name="area_4_course_preference",
        area=4,
        prompt="가능하면 대학영어를 듣고 싶고, 발표나 팀플이 적은 수업이면 좋겠어.",
        template="balanced",
    ),
]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run raw Excel PlaNU examples without starting uvicorn.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="Only print raw Excel parse counts; do not call OpenAI.",
    )
    parser.add_argument(
        "--example",
        choices=[example.name for example in EXAMPLES],
        help="Run one example instead of all examples.",
    )
    args = parser.parse_args()

    _print_raw_summary()
    if args.list:
        return 0

    required_courses = parse_catalog_workbook(
        RAW_DIR / "general_required.xlsx",
        Category.GENERAL_REQUIRED,
    )

    examples = [
        example for example in EXAMPLES
        if args.example is None or example.name == args.example
    ]
    for example in examples:
        print(f"\n=== {example.name} ===")
        result = run_example(example, required_courses=required_courses)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    return 0


def run_example(
    example: RawExcelExample,
    *,
    required_courses: list[Course],
) -> dict[str, Any]:
    store = SessionStore()
    template_service = RankingTemplateService()

    app.dependency_overrides.update(
        {
            get_session_store: lambda: store,
            get_general_course_preparation_service: lambda: GeneralCoursePreparationService(
                store=store,
                pool_service=GeneralCoursePoolService(
                    restriction_policy=CourseRestrictionPolicy()
                ),
                general_required_courses=required_courses,
                elective_parser=UploadedCatalogParser(),
            ),
            get_timetable_generation_service: lambda: TimetableGenerationService(
                store=store,
            ),
            get_timetable_ranking_service: lambda: TimetableRankingService(
                store=store,
                template_service=template_service,
                ranker=TimetableRanker(template_service=template_service),
            ),
        }
    )
    try:
        client = TestClient(app)
        session_id = _create_confirmed_major_session(store)

        prepare = _post_prepare(client, session_id, example)
        generate = _post_generate(client, session_id, example)
        rank = _post_rank(client, session_id, example)
        return _summarize(example, session_id, prepare, generate, rank)
    finally:
        app.dependency_overrides.clear()


def _create_confirmed_major_session(store: SessionStore) -> str:
    fixed_courses = [
        _course("MA100-001", "자료구조", Category.MAJOR_REQUIRED, Day.MON, "13:00", "14:15"),
        _course("MA200-003", "컴퓨터구조", Category.MAJOR_REQUIRED, Day.TUE, "13:00", "14:15"),
    ]
    session = store.create(
        department="컴퓨터공학과",
        major_candidates=fixed_courses,
    )
    store.update(
        session.session_id,
        fixed_courses=fixed_courses,
        confirmed_major_credits=sum(course.credit for course in fixed_courses),
        session_stage=SessionStage.MAJOR_CONFIRMED,
    )
    return session.session_id


def _post_prepare(
    client: TestClient,
    session_id: str,
    example: RawExcelExample,
) -> dict[str, Any]:
    with example.elective_path.open("rb") as stream:
        response = client.post(
            "/general/prepare",
            data={
                "session_id": session_id,
                "elective_area": str(example.area),
            },
            files={
                "elective_catalog": (
                    example.elective_path.name,
                    stream,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
    _raise_for_response("prepare", response)
    return response.json()


def _post_generate(
    client: TestClient,
    session_id: str,
    example: RawExcelExample,
) -> dict[str, Any]:
    response = client.post(
        "/recommend/generate",
        json={
            "session_id": session_id,
            "target_total_credits": example.target_total_credits,
            "additional_elective_count": example.additional_elective_count,
            "preference_prompt": example.prompt,
            "max_candidates": 50,
        },
    )
    _raise_for_response("generate", response)
    return response.json()


def _post_rank(
    client: TestClient,
    session_id: str,
    example: RawExcelExample,
) -> dict[str, Any]:
    response = client.post(
        "/recommend/rank",
        json={
            "session_id": session_id,
            "template": example.template,
            "top_n": 3,
        },
    )
    _raise_for_response("rank", response)
    return response.json()


def _summarize(
    example: RawExcelExample,
    session_id: str,
    prepare: dict[str, Any],
    generate: dict[str, Any],
    rank: dict[str, Any],
) -> dict[str, Any]:
    top = rank["ranked_candidates"][0] if rank["ranked_candidates"] else None
    return {
        "example": example.name,
        "session_id": session_id,
        "input": {
            "elective_file": example.elective_path.name,
            "elective_area": example.area,
            "prompt": example.prompt,
            "template": example.template,
        },
        "prepare": {
            "required_course_count": prepare["required_course_count"],
            "elective_course_count": prepare["elective_course_count"],
            "excluded_course_count": prepare["excluded_course_count"],
            "data_source": prepare["data_source"],
        },
        "generate": {
            "candidate_count": len(generate["candidates"]),
            "truncated": generate["truncated"],
            "hard_conditions": generate["hard_conditions"],
            "soft_conditions": generate["soft_conditions"],
            "unsupported_conditions": generate["unsupported_conditions"],
            "warnings": generate["warnings"],
        },
        "rank": {
            "template": rank["template"],
            "returned_count": rank["returned_count"],
            "top_score": None if top is None else top["raw_score"],
            "top_course_names": [] if top is None else [
                course["course_name"]
                for course in top["timetable"]["courses"]
            ],
        },
    }


def _print_raw_summary() -> None:
    required = parse_catalog_workbook(
        RAW_DIR / "general_required.xlsx",
        Category.GENERAL_REQUIRED,
    )
    electives = {
        area: len(
            parse_catalog_workbook(
                RAW_DIR / f"general_elective_area_{area}.xlsx",
                Category.GENERAL_ELECTIVE,
                area=area,
            )
        )
        for area in range(1, 8)
    }
    restrictions, departments = parse_restrictions(RAW_DIR / "course_restriction.xlsx")
    print(
        json.dumps(
            {
                "raw_dir": str(RAW_DIR),
                "general_required_count": len(required),
                "general_elective_counts": electives,
                "restriction_row_count": len(restrictions),
                "department_count": len(departments),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def _course(
    course_id: str,
    name: str,
    category: Category,
    day: Day,
    start: str,
    end: str,
    *,
    credit: float = 3,
) -> Course:
    return Course(
        course_id=course_id,
        course_name=name,
        category=category,
        credit=credit,
        division=course_id.rsplit("-", 1)[-1],
        professor="테스트교수",
        class_times=[
            ClassTime(
                day=day,
                start=start,
                end=end,
                classroom="609-101",
                building_code="609",
            )
        ],
    )


def _raise_for_response(name: str, response) -> None:
    if response.status_code < 400:
        return
    raise RuntimeError(
        f"{name} failed with HTTP {response.status_code}: {response.text}"
    )


if __name__ == "__main__":
    raise SystemExit(main())
