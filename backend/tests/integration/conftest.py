"""Shared HTTP-level integration fixtures for the PlaNU backend."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

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
from backend.app.models import (
    Category,
    ClassTime,
    Course,
    Day,
    GeneralPreferenceParseResult,
    MajorCourseReference,
    MajorSelectionParseResult,
    PreferenceRules,
    PreferenceWarning,
    UnsupportedCondition,
)
from backend.app.services.general_course_pool_service import (
    CourseRestrictionPolicy,
    DepartmentRestrictionRule,
    GeneralCoursePoolService,
    GeneralCoursePreparationService,
)
from backend.app.services.major_catalog_upload_service import MajorCatalogUploadService
from backend.app.services.major_confirm_service import MajorConfirmService
from backend.app.services.major_preview_service import MajorPreviewService
from backend.app.services.session_store import SessionStore
from backend.app.services.timetable_generation_service import TimetableGenerationService
from backend.app.services.timetable_ranking_service import TimetableRankingService


@dataclass
class MutableClock:
    current: datetime

    def __call__(self) -> datetime:
        return self.current

    def advance(self, delta: timedelta) -> None:
        self.current += delta


class FakeMajorSelectionParser:
    def parse(self, prompt: str) -> MajorSelectionParseResult:
        if "운영체제" in prompt:
            return MajorSelectionParseResult(
                selected_courses=[MajorCourseReference(course_name="운영체제", section="001")]
            )
        if "분반 없이" in prompt:
            return MajorSelectionParseResult(
                selected_courses=[MajorCourseReference(course_name="자료구조")]
            )
        return MajorSelectionParseResult(
            selected_courses=[
                MajorCourseReference(course_name="자료구조", section="001"),
                MajorCourseReference(course_name="컴퓨터구조", section="003"),
            ]
        )


class FakeGeneralPreferenceParser:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def parse(self, prompt: str) -> GeneralPreferenceParseResult:
        self.calls.append(prompt)
        if "절대 안" in prompt:
            return GeneralPreferenceParseResult(
                hard_conditions=PreferenceRules(excluded_days=[Day.FRI])
            )
        if "과제가 적은" in prompt:
            return GeneralPreferenceParseResult(
                soft_conditions=PreferenceRules(preferred_free_days=[Day.FRI]),
                unsupported_conditions=[
                    UnsupportedCondition(
                        source_text="과제가 적은 수업",
                        reason_code="DATA_NOT_AVAILABLE",
                        reason="현재 수강편람 데이터에서는 과제량을 확인할 수 없습니다.",
                    )
                ],
            )
        return GeneralPreferenceParseResult(
            soft_conditions=PreferenceRules(
                preferred_free_days=[Day.FRI],
                preferred_first_class_time="10:00",
            ),
            warnings=[
                PreferenceWarning(
                    code="SOFT_CONDITION_APPLIED",
                    message="오전 수업 회피를 soft 조건으로 반영했습니다.",
                    source_text="오전 수업은 피하고 싶어",
                )
            ],
        )


@dataclass
class IntegrationApp:
    client: TestClient
    store: SessionStore
    preference_parser: FakeGeneralPreferenceParser
    clock: MutableClock


@pytest.fixture
def integration_app() -> Iterator[IntegrationApp]:
    clock = MutableClock(datetime(2026, 7, 21, tzinfo=timezone.utc))
    store = SessionStore(ttl=timedelta(minutes=30), clock=clock)
    preference_parser = FakeGeneralPreferenceParser()
    required = [
        _course("GR101-001", "고전읽기와토론", Category.GENERAL_REQUIRED, Day.WED, "10:30", "11:45", credit=2),
        _course("GR102-001", "인공지능과컴퓨팅사고", Category.GENERAL_REQUIRED, Day.THU, "10:30", "11:45", credit=2),
    ]
    pool_service = GeneralCoursePoolService(
        restriction_policy=CourseRestrictionPolicy(
            rules=[
                DepartmentRestrictionRule(
                    course_code="GR101",
                    division="001",
                    allowed_departments=frozenset({"컴퓨터공학과", "전자공학과"}),
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
    template_service = None

    app.dependency_overrides.update(
        {
            get_session_store: lambda: store,
            get_major_catalog_upload_service: lambda: MajorCatalogUploadService(store=store),
            get_major_preview_service: lambda: MajorPreviewService(
                store=store,
                parser=FakeMajorSelectionParser(),
            ),
            get_major_confirm_service: lambda: MajorConfirmService(store=store),
            get_general_course_preparation_service: lambda: GeneralCoursePreparationService(
                store=store,
                pool_service=pool_service,
                general_required_courses=required,
                fallback_elective_courses=[
                    _course("GE201-001", "과학기술과사회", Category.GENERAL_ELECTIVE, Day.TUE, "13:00", "14:15", area=2),
                ],
            ),
            get_timetable_generation_service: lambda: TimetableGenerationService(
                store=store,
                preference_parser=preference_parser,
            ),
            get_timetable_ranking_service: lambda: TimetableRankingService(
                store=store,
                template_service=template_service,
            ),
        }
    )
    client = TestClient(app)
    try:
        yield IntegrationApp(
            client=client,
            store=store,
            preference_parser=preference_parser,
            clock=clock,
        )
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def major_catalog_path(tmp_path: Path) -> Path:
    path = tmp_path / "major.xlsx"
    _write_catalog(
        path,
        [
            ["전공필수", "자료구조", "MA100", "001", 3, "김교수", "월 09:00-10:15 609-101"],
            ["전공필수", "자료구조", "002", "002", 3, "김교수", "금 09:00-10:15 609-102"],
            ["전공필수", "컴퓨터구조", "MA200", "003", 3, "박교수", "화 09:00-10:15 609-201"],
        ],
    )
    return path


@pytest.fixture
def second_major_catalog_path(tmp_path: Path) -> Path:
    path = tmp_path / "major-b.xlsx"
    _write_catalog(
        path,
        [
            ["전공필수", "자료구조", "MA300", "001", 3, "최교수", "월 13:00-14:15 609-301"],
            ["전공필수", "컴퓨터구조", "MA400", "003", 3, "정교수", "화 13:00-14:15 609-401"],
        ],
    )
    return path


@pytest.fixture
def conflicting_major_catalog_path(tmp_path: Path) -> Path:
    path = tmp_path / "major-conflict.xlsx"
    _write_catalog(
        path,
        [
            ["전공필수", "자료구조", "MA100", "001", 3, "김교수", "월 09:00-10:15 609-101"],
            ["전공필수", "컴퓨터구조", "MA200", "003", 3, "박교수", "월 09:30-10:45 609-201"],
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


def upload_major(client: TestClient, path: Path, *, department: str = "컴퓨터공학과") -> dict:
    with path.open("rb") as stream:
        response = client.post(
            "/catalog/major",
            data={"department": department},
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


def run_until_confirmed(client: TestClient, path: Path, *, department: str = "컴퓨터공학과") -> tuple[str, dict]:
    upload = upload_major(client, path, department=department)
    session_id = upload["session_id"]
    preview = client.post(
        "/major/preview",
        json={
            "session_id": session_id,
            "prompt": "자료구조 001분반과 컴퓨터구조 003분반을 들을 거야",
        },
    )
    assert preview.status_code == 200, preview.text
    confirm = client.post(
        "/major/confirm",
        json={"session_id": session_id, "preview_id": preview.json()["preview_id"]},
    )
    assert confirm.status_code == 200, confirm.text
    return session_id, confirm.json()


def prepare_generate_rank(
    client: TestClient,
    session_id: str,
    elective_path: Path,
    *,
    prompt: str = "금요일은 가능하면 쉬고 싶고 오전 수업은 피하고 싶어",
    target_total_credits: float | None = 14,
    additional_elective_count: int | None = 1,
    template: str = "balanced",
) -> tuple[dict, dict, dict]:
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
            "target_total_credits": target_total_credits,
            "additional_elective_count": additional_elective_count,
            "preference_prompt": prompt,
            "max_candidates": 100,
        },
    )
    assert generate.status_code == 200, generate.text
    rank = client.post(
        "/recommend/rank",
        json={"session_id": session_id, "template": template, "top_n": 3},
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


def write_catalog(path: Path, rows: list[list[object]]) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["교과구분", "교과목명", "교과목번호", "분반", "학점", "담당교수", "시간/강의실"])
    for row in rows:
        sheet.append(row)
    workbook.save(path)


def _write_catalog(path: Path, rows: list[list[object]]) -> None:
    write_catalog(path, rows)
