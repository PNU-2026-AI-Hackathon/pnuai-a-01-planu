"""Shared fixtures for opt-in live LLM tests.

These tests intentionally call the configured OpenAI LLM only when
RUN_LIVE_LLM_TESTS=1 is present.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook

from backend.app.deps import (
    get_general_course_preparation_service,
    get_major_catalog_upload_service,
    get_major_confirm_service,
    get_major_preview_service,
    get_session_store,
    get_timetable_generation_service,
    get_timetable_ranking_service,
)
from backend.app.main import app
from backend.app.models import Category, ClassTime, Course, Day
from backend.app.services.general_course_pool_service import (
    CourseRestrictionPolicy,
    DepartmentRestrictionRule,
    GeneralCoursePoolService,
    GeneralCoursePreparationService,
)
from backend.app.services.llm_preference_parser import (
    DEFAULT_OPENAI_MODEL,
    load_proxy_env,
)
from backend.app.services.openai_client import has_openai_api_key, normalize_openai_model_name
from backend.app.services.major_catalog_upload_service import MajorCatalogUploadService
from backend.app.services.major_confirm_service import MajorConfirmService
from backend.app.services.major_preview_service import MajorPreviewService
from backend.app.services.major_selection_parser import MajorSelectionParser
from backend.app.services.ranking_template_service import RankingTemplateService
from backend.app.services.session_store import SessionStore
from backend.app.services.timetable_generation_service import TimetableGenerationService
from backend.app.services.timetable_ranker import TimetableRanker
from backend.app.services.timetable_ranking_service import TimetableRankingService


LIVE_LLM_CALLS: list[dict[str, Any]] = []


@dataclass(frozen=True)
class LiveLLMConfig:
    model: str
    openai_enabled: bool
    timeout_seconds: int


@pytest.fixture(scope="session")
def live_llm_enabled() -> None:
    if os.getenv("RUN_LIVE_LLM_TESTS") != "1":
        pytest.skip("RUN_LIVE_LLM_TESTS=1 is required")
    load_proxy_env()
    if not has_openai_api_key(os.getenv("OPENAI_API_KEY")):
        pytest.skip("OPENAI_API_KEY is not configured")


@pytest.fixture(scope="session")
def live_llm_config(live_llm_enabled: None) -> LiveLLMConfig:
    model = normalize_openai_model_name(os.getenv("OPENAI_MODEL", DEFAULT_OPENAI_MODEL))
    timeout_seconds = int(os.getenv("LIVE_LLM_TIMEOUT_SECONDS", "60"))
    config = LiveLLMConfig(
        model=model,
        openai_enabled=True,
        timeout_seconds=timeout_seconds,
    )
    print(
        "live_llm_config: "
        + json.dumps(
            {
                "model": config.model,
                "openai_enabled": config.openai_enabled,
                "timeout_seconds": config.timeout_seconds,
            },
            ensure_ascii=False,
        )
    )
    return config


@pytest.fixture
def trace_call(live_llm_config: LiveLLMConfig):
    def _trace(case_name: str, parser_name: str, fn):
        started = time.perf_counter()
        success = False
        error_code = None
        try:
            result = fn()
            success = True
            return result
        except Exception as exc:
            error_code = getattr(exc, "code", type(exc).__name__)
            raise
        finally:
            latency_ms = int((time.perf_counter() - started) * 1000)
            record = {
                "case": case_name,
                "parser": parser_name,
                "model": live_llm_config.model,
                "latency_ms": latency_ms,
                "success": success,
                "error_code": error_code,
            }
            LIVE_LLM_CALLS.append(record)
            print("live_llm_trace: " + json.dumps(record, ensure_ascii=False))

    return _trace


def pytest_terminal_summary(terminalreporter, exitstatus, config) -> None:
    if not LIVE_LLM_CALLS:
        return
    latencies = [record["latency_ms"] for record in LIVE_LLM_CALLS]
    summary = {
        "total_calls": len(LIVE_LLM_CALLS),
        "success_count": sum(1 for record in LIVE_LLM_CALLS if record["success"]),
        "failure_count": sum(1 for record in LIVE_LLM_CALLS if not record["success"]),
        "min_latency_ms": min(latencies),
        "max_latency_ms": max(latencies),
        "avg_latency_ms": int(sum(latencies) / len(latencies)),
    }
    terminalreporter.write_line(
        "live_llm_summary: " + json.dumps(summary, ensure_ascii=False)
    )


@pytest.fixture
def live_major_parser(live_llm_config: LiveLLMConfig) -> MajorSelectionParser:
    return MajorSelectionParser(timeout_seconds=live_llm_config.timeout_seconds)


@dataclass
class LiveApiApp:
    client: TestClient
    store: SessionStore


@pytest.fixture
def live_api_app(live_llm_enabled: None) -> Iterator[LiveApiApp]:
    store = SessionStore(
        ttl=timedelta(minutes=30),
        clock=lambda: datetime(2026, 7, 21, tzinfo=timezone.utc),
    )
    template_service = RankingTemplateService()
    pool_service = GeneralCoursePoolService(
        restriction_policy=CourseRestrictionPolicy(
            rules=[
                DepartmentRestrictionRule(
                    course_code="GR101",
                    division="001",
                    allowed_departments=frozenset({"컴퓨터공학과"}),
                    blocked_departments=frozenset(),
                ),
                DepartmentRestrictionRule(
                    course_code="GR102",
                    division="001",
                    allowed_departments=frozenset({"컴퓨터공학과"}),
                    blocked_departments=frozenset(),
                ),
            ]
        )
    )
    app.dependency_overrides.update(
        {
            get_session_store: lambda: store,
            get_major_catalog_upload_service: lambda: MajorCatalogUploadService(store=store),
            get_major_preview_service: lambda: MajorPreviewService(
                store=store,
                parser=MajorSelectionParser(),
            ),
            get_major_confirm_service: lambda: MajorConfirmService(store=store),
            get_general_course_preparation_service: lambda: GeneralCoursePreparationService(
                store=store,
                pool_service=pool_service,
                general_required_courses=[
                    _course("GR101-001", "고전읽기와토론", Category.GENERAL_REQUIRED, Day.WED, "10:30", "11:45", credit=2),
                    _course("GR102-001", "인공지능과컴퓨팅사고", Category.GENERAL_REQUIRED, Day.THU, "10:30", "11:45", credit=2),
                ],
                fallback_elective_courses=[
                    _course("GE201-001", "과학기술과사회", Category.GENERAL_ELECTIVE, Day.TUE, "13:00", "14:15", area=2),
                ],
            ),
            get_timetable_generation_service: lambda: TimetableGenerationService(store=store),
            get_timetable_ranking_service: lambda: TimetableRankingService(
                store=store,
                template_service=template_service,
                ranker=TimetableRanker(template_service=template_service),
            ),
        }
    )
    try:
        yield LiveApiApp(client=TestClient(app), store=store)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def major_catalog_path(tmp_path: Path) -> Path:
    path = tmp_path / "major.xlsx"
    _write_catalog(
        path,
        [
            ["전공필수", "자료구조", "MA100", "001", 3, "김교수", "월 13:00-14:15 609-101"],
            ["전공필수", "컴퓨터구조", "MA200", "003", 3, "박교수", "화 13:00-14:15 609-201"],
        ],
    )
    return path


@pytest.fixture
def elective_catalog_path(tmp_path: Path) -> Path:
    path = tmp_path / "elective.xlsx"
    _write_catalog(
        path,
        [
            ["교양선택", "과학기술과사회", "GE201", "001", 3, "이교수", "수 13:00-14:15 609-301"],
            ["교양선택", "미래사회와윤리", "GE202", "001", 3, "오교수", "금 13:00-14:15 609-302"],
            ["교양선택", "창의적문제해결", "GE203", "001", 3, "한교수", "목 13:00-14:15 609-303"],
            ["교양선택", "아침의예술", "GE204", "001", 3, "문교수", "목 08:00-09:00 609-304"],
        ],
    )
    return path


def upload_major(client: TestClient, path: Path) -> dict[str, Any]:
    with path.open("rb") as stream:
        response = client.post(
            "/catalog/major",
            data={"department": "컴퓨터공학과"},
            files={
                "major_catalog": (
                    path.name,
                    stream,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
    assert response.status_code == 200, response.text
    return response.json()


def prepare_generate_rank(
    client: TestClient,
    session_id: str,
    elective_path: Path,
    *,
    prompt: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
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
            "preference_prompt": prompt,
            "max_candidates": 100,
        },
    )
    assert generate.status_code == 200, generate.text
    rank = client.post(
        "/recommend/rank",
        json={"session_id": session_id, "template": "balanced", "top_n": 3},
    )
    assert rank.status_code == 200, rank.text
    return prepare.json(), generate.json(), rank.json()


def _course(
    course_id: str,
    name: str,
    category: Category,
    day: Day,
    start: str,
    end: str,
    *,
    credit: float = 3,
    area: int | None = None,
) -> Course:
    return Course(
        course_id=course_id,
        course_name=name,
        category=category,
        area=area,
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


def _write_catalog(path: Path, rows: list[list[object]]) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["교과구분", "교과목명", "교과목번호", "분반", "학점", "담당교수", "시간/강의실"])
    for row in rows:
        sheet.append(row)
    workbook.save(path)
