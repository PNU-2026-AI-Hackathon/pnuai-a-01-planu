"""Tests for natural-language major preview creation."""

from __future__ import annotations

import asyncio
from datetime import timedelta

import pytest

from backend.app.core.errors import AppError
from backend.app.models import (
    Category,
    ClassTime,
    Course,
    Day,
    MajorCourseReference,
    MajorSelectionParseResult,
)
from backend.app.services.major_preview_service import MajorPreviewService
from backend.app.services.major_selection_parser import InvalidMajorSelectionOutputError
from backend.app.services.session_store import SessionStore


class FakeMajorSelectionParser:
    def __init__(self, result: MajorSelectionParseResult | Exception) -> None:
        self.result = result
        self.prompts: list[str] = []

    def parse(self, prompt: str) -> MajorSelectionParseResult:
        self.prompts.append(prompt)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def _course(
    course_id: str,
    name: str,
    division: str,
    *,
    day: Day = Day.MON,
    start: str = "09:00",
    end: str = "10:15",
    professor: str = "김교수",
) -> Course:
    return Course(
        course_id=course_id,
        course_name=name,
        category=Category.MAJOR_REQUIRED,
        credit=3,
        division=division,
        professor=professor,
        class_times=[
            ClassTime(
                day=day,
                start=start,
                end=end,
                classroom="제6공학관 6201",
                building_code="6201",
            )
        ],
    )


def _service(
    store: SessionStore,
    result: MajorSelectionParseResult | Exception,
) -> MajorPreviewService:
    return MajorPreviewService(store=store, parser=FakeMajorSelectionParser(result))


def test_preview_matches_uploaded_catalog_courses_and_saves_latest_preview() -> None:
    uploaded_course = _course(
        "MA100-001",
        "자료구조",
        "001",
        professor="업로드교수",
    )
    store = SessionStore(ttl=timedelta(minutes=30))
    session = store.create("컴퓨터공학과", major_candidates=[uploaded_course])
    service = _service(
        store,
        MajorSelectionParseResult(
            selected_courses=[MajorCourseReference(course_name="자료구조", section="001")]
        ),
    )

    response = asyncio.run(service.create_preview(session.session_id, "자료구조 001분반"))

    assert response.session_id == session.session_id
    assert response.can_confirm is True
    assert response.matched_courses[0].course.course_id == "MA100-001"
    assert response.matched_courses[0].course.professor == "업로드교수"
    saved = store.get(session.session_id).latest_major_preview
    assert saved is not None
    assert saved["preview_id"] == response.preview_id
    assert saved["matched_course_ids"] == ["MA100-001"]


def test_unmatched_courses_are_returned_with_partial_success() -> None:
    store = SessionStore()
    session = store.create(
        "컴퓨터공학과",
        major_candidates=[_course("MA100-001", "자료구조", "001")],
    )
    service = _service(
        store,
        MajorSelectionParseResult(
            selected_courses=[
                MajorCourseReference(course_name="자료구조", section="001"),
                MajorCourseReference(course_name="컴퓨터구조", section="999"),
            ]
        ),
    )

    response = asyncio.run(service.create_preview(session.session_id, "자료구조와 컴퓨터구조"))

    assert [item.course.course_id for item in response.matched_courses] == ["MA100-001"]
    assert response.unmatched_courses[0].reference.course_name == "컴퓨터구조"
    assert response.can_confirm is False


def test_missing_section_becomes_ambiguous() -> None:
    store = SessionStore()
    session = store.create(
        "컴퓨터공학과",
        major_candidates=[_course("MA200-001", "운영체제", "001")],
    )
    service = _service(
        store,
        MajorSelectionParseResult(
            selected_courses=[MajorCourseReference(course_name="운영체제")]
        ),
    )

    response = asyncio.run(service.create_preview(session.session_id, "운영체제 들을래"))

    assert response.matched_courses == []
    assert response.ambiguous_courses[0].candidates[0].course_id == "MA200-001"
    assert response.can_confirm is False


def test_time_conflict_is_returned_without_failing_preview() -> None:
    store = SessionStore()
    first = _course("MA100-001", "자료구조", "001", start="09:00", end="10:15")
    second = _course("MA200-001", "컴퓨터구조", "001", start="10:00", end="11:15")
    session = store.create("컴퓨터공학과", major_candidates=[first, second])
    service = _service(
        store,
        MajorSelectionParseResult(
            selected_courses=[
                MajorCourseReference(course_name="자료구조", section="001"),
                MajorCourseReference(course_name="컴퓨터구조", section="001"),
            ]
        ),
    )

    response = asyncio.run(service.create_preview(session.session_id, "자료구조랑 컴퓨터구조"))

    assert response.has_time_conflict is True
    assert response.conflicts[0].overlap_start == "10:00"
    assert response.conflicts[0].overlap_end == "10:15"
    assert response.can_confirm is False


def test_no_matched_courses_cannot_confirm() -> None:
    store = SessionStore()
    session = store.create(
        "컴퓨터공학과",
        major_candidates=[_course("MA100-001", "자료구조", "001")],
    )
    service = _service(
        store,
        MajorSelectionParseResult(
            ambiguous_texts=["자료구조나 알고리즘 중 하나 들을 예정"]
        ),
    )

    response = asyncio.run(service.create_preview(session.session_id, "자료구조나 알고리즘"))

    assert response.matched_courses == []
    assert response.ambiguous_texts == ["자료구조나 알고리즘 중 하나 들을 예정"]
    assert response.can_confirm is False


def test_latest_preview_replaces_previous_preview() -> None:
    store = SessionStore()
    session = store.create(
        "컴퓨터공학과",
        major_candidates=[
            _course("MA100-001", "자료구조", "001"),
            _course("MA200-001", "운영체제", "001"),
        ],
    )

    first = asyncio.run(_service(
        store,
        MajorSelectionParseResult(
            selected_courses=[MajorCourseReference(course_name="자료구조", section="001")]
        ),
    ).create_preview(session.session_id, "자료구조"))
    second = asyncio.run(_service(
        store,
        MajorSelectionParseResult(
            selected_courses=[MajorCourseReference(course_name="운영체제", section="001")]
        ),
    ).create_preview(session.session_id, "운영체제"))

    saved = store.get(session.session_id).latest_major_preview
    assert saved is not None
    assert saved["preview_id"] == second.preview_id
    assert saved["preview_id"] != first.preview_id
    assert saved["matched_course_ids"] == ["MA200-001"]


def test_session_validation_errors_are_standardized() -> None:
    store = SessionStore()
    service = _service(
        store,
        MajorSelectionParseResult(
            selected_courses=[MajorCourseReference(course_name="자료구조", section="001")]
        ),
    )

    with pytest.raises(AppError) as exc_info:
        asyncio.run(service.create_preview("missing", "자료구조 001분반"))

    assert exc_info.value.code == "SESSION_NOT_FOUND"


def test_missing_major_catalog_is_rejected_before_parser_call() -> None:
    store = SessionStore()
    session = store.create("컴퓨터공학과")
    parser = FakeMajorSelectionParser(
        MajorSelectionParseResult(
            selected_courses=[MajorCourseReference(course_name="자료구조", section="001")]
        )
    )
    service = MajorPreviewService(store=store, parser=parser)

    with pytest.raises(AppError) as exc_info:
        asyncio.run(service.create_preview(session.session_id, "자료구조 001분반"))

    assert exc_info.value.code == "MAJOR_CATALOG_NOT_FOUND"
    assert parser.prompts == []


def test_confirmed_session_rejects_preview() -> None:
    fixed = _course("MA100-001", "자료구조", "001")
    store = SessionStore()
    session = store.create(
        "컴퓨터공학과",
        major_candidates=[fixed],
    )
    store.update(session.session_id, fixed_courses=[fixed])
    service = _service(
        store,
        MajorSelectionParseResult(
            selected_courses=[MajorCourseReference(course_name="자료구조", section="001")]
        ),
    )

    with pytest.raises(AppError) as exc_info:
        asyncio.run(service.create_preview(session.session_id, "자료구조 001분반"))

    assert exc_info.value.code == "INVALID_SESSION_STAGE"


def test_parser_failure_is_sanitized() -> None:
    store = SessionStore()
    session = store.create(
        "컴퓨터공학과",
        major_candidates=[_course("MA100-001", "자료구조", "001")],
    )
    service = _service(
        store,
        InvalidMajorSelectionOutputError("raw invalid output"),
    )

    with pytest.raises(AppError) as exc_info:
        asyncio.run(service.create_preview(session.session_id, "자료구조 001분반"))

    assert exc_info.value.code == "MAJOR_SELECTION_PARSE_FAILED"
    assert "raw invalid output" not in exc_info.value.message
