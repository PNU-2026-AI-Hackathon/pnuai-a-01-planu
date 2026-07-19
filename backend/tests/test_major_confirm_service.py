"""Tests for confirming server-stored major previews."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from backend.app.core.errors import AppError
from backend.app.models import Category, ClassTime, Course, Day
from backend.app.services.major_confirm_service import MajorConfirmService
from backend.app.services.session_store import SessionStage, SessionStore


class BarrierValidator:
    def __init__(self, parties: int) -> None:
        self.barrier = Barrier(parties)

    def has_time_conflict(self, _: list[Course]) -> bool:
        self.barrier.wait(timeout=5)
        return False


def _course(
    course_id: str,
    name: str,
    division: str,
    *,
    credit: float = 3,
    start: str = "09:00",
    end: str = "10:15",
) -> Course:
    return Course(
        course_id=course_id,
        course_name=name,
        category=Category.MAJOR_REQUIRED,
        credit=credit,
        division=division,
        professor="김교수",
        class_times=[
            ClassTime(
                day=Day.MON,
                start=start,
                end=end,
                classroom="제6공학관 6201",
                building_code="6201",
            )
        ],
    )


def _save_preview(
    store: SessionStore,
    session_id: str,
    *,
    preview_id: str = "preview-1",
    matched_course_ids: list[str] | None = None,
    ambiguous_courses: list[object] | None = None,
    unmatched_courses: list[object] | None = None,
    ambiguous_texts: list[str] | None = None,
    has_time_conflict: bool = False,
    session_owner: str | None = None,
) -> None:
    store.update(
        session_id,
        session_stage=SessionStage.MAJOR_PREVIEW_CREATED,
        latest_major_preview={
            "session_id": session_owner or session_id,
            "preview_id": preview_id,
            "matched_course_ids": (
                ["MA100-001"] if matched_course_ids is None else matched_course_ids
            ),
            "ambiguous_courses": [] if ambiguous_courses is None else ambiguous_courses,
            "unmatched_courses": [] if unmatched_courses is None else unmatched_courses,
            "ambiguous_texts": [] if ambiguous_texts is None else ambiguous_texts,
            "has_time_conflict": has_time_conflict,
            "conflicts": [],
        },
    )


def test_confirm_saves_actual_courses_credits_stage_and_preview_status() -> None:
    first = _course("MA100-001", "자료구조", "001", credit=3)
    second = _course("MA200-001", "운영체제", "001", credit=2, start="10:30", end="11:45")
    store = SessionStore()
    session = store.create("컴퓨터공학과", major_candidates=[first, second])
    _save_preview(store, session.session_id, matched_course_ids=["MA100-001", "MA200-001"])
    service = MajorConfirmService(store=store)

    response = asyncio.run(service.confirm(session.session_id, "preview-1"))

    saved = store.get(session.session_id)
    assert saved.fixed_courses == [first, second]
    assert saved.confirmed_major_credits == 5
    assert saved.session_stage is SessionStage.MAJOR_CONFIRMED
    assert saved.confirmed_major_preview_id == "preview-1"
    assert saved.latest_major_preview is not None
    assert saved.latest_major_preview["is_confirmed"] is True
    assert response.confirmed_course_count == 2
    assert response.confirmed_major_credits == 5
    assert response.session_stage is SessionStage.MAJOR_CONFIRMED
    assert response.confirmed_courses[0].professor == "김교수"


def test_confirm_rejects_unconfirmable_preview_states() -> None:
    cases = [
        {"matched_course_ids": []},
        {"ambiguous_courses": [{"reason": "missing section"}]},
        {"unmatched_courses": [{"reason": "not found"}]},
        {"ambiguous_texts": ["자료구조나 운영체제"]},
    ]

    for index, kwargs in enumerate(cases):
        store = SessionStore()
        session = store.create(
            "컴퓨터공학과",
            major_candidates=[_course("MA100-001", "자료구조", "001")],
            session_id=f"session-{index}",
        )
        _save_preview(store, session.session_id, **kwargs)

        with pytest.raises(AppError) as exc_info:
            asyncio.run(MajorConfirmService(store=store).confirm(session.session_id, "preview-1"))

        assert exc_info.value.code == "MAJOR_PREVIEW_NOT_CONFIRMABLE"
        assert store.get(session.session_id).fixed_courses == []


def test_confirm_rejects_time_conflict_from_preview_or_revalidation() -> None:
    store = SessionStore()
    session = store.create(
        "컴퓨터공학과",
        major_candidates=[_course("MA100-001", "자료구조", "001")],
    )
    _save_preview(store, session.session_id, has_time_conflict=True)

    with pytest.raises(AppError) as exc_info:
        asyncio.run(MajorConfirmService(store=store).confirm(session.session_id, "preview-1"))

    assert exc_info.value.code == "MAJOR_TIME_CONFLICT"

    first = _course("MA100-001", "자료구조", "001", start="09:00", end="10:15")
    second = _course("MA200-001", "운영체제", "001", start="10:00", end="11:15")
    store = SessionStore()
    session = store.create("컴퓨터공학과", major_candidates=[first, second])
    _save_preview(store, session.session_id, matched_course_ids=["MA100-001", "MA200-001"])

    with pytest.raises(AppError) as exc_info:
        asyncio.run(MajorConfirmService(store=store).confirm(session.session_id, "preview-1"))

    assert exc_info.value.code == "MAJOR_TIME_CONFLICT"
    assert store.get(session.session_id).fixed_courses == []


def test_confirm_rejects_stale_wrong_session_and_invalid_course_reference() -> None:
    store = SessionStore()
    session = store.create(
        "컴퓨터공학과",
        major_candidates=[_course("MA100-001", "자료구조", "001")],
    )
    _save_preview(store, session.session_id, preview_id="latest")

    with pytest.raises(AppError) as exc_info:
        asyncio.run(MajorConfirmService(store=store).confirm(session.session_id, "old"))
    assert exc_info.value.code == "STALE_MAJOR_PREVIEW"

    store.update(
        session.session_id,
        latest_major_preview={
            **store.get(session.session_id).latest_major_preview,
            "session_id": "other-session",
        },
    )
    with pytest.raises(AppError) as exc_info:
        asyncio.run(MajorConfirmService(store=store).confirm(session.session_id, "latest"))
    assert exc_info.value.code == "INVALID_PREVIEW_SESSION"

    store.update(
        session.session_id,
        latest_major_preview={
            "session_id": session.session_id,
            "preview_id": "latest",
            "matched_course_ids": ["missing-course"],
            "ambiguous_courses": [],
            "unmatched_courses": [],
            "ambiguous_texts": [],
            "has_time_conflict": False,
            "conflicts": [],
        },
    )
    with pytest.raises(AppError) as exc_info:
        asyncio.run(MajorConfirmService(store=store).confirm(session.session_id, "latest"))
    assert exc_info.value.code == "MAJOR_COURSE_REFERENCE_INVALID"


def test_confirm_is_idempotent_for_same_preview_and_rejects_different_preview() -> None:
    course = _course("MA100-001", "자료구조", "001")
    store = SessionStore()
    session = store.create("컴퓨터공학과", major_candidates=[course])
    _save_preview(store, session.session_id, preview_id="preview-1")
    service = MajorConfirmService(store=store)

    first = asyncio.run(service.confirm(session.session_id, "preview-1"))
    second = asyncio.run(service.confirm(session.session_id, "preview-1"))

    assert first == second
    with pytest.raises(AppError) as exc_info:
        asyncio.run(service.confirm(session.session_id, "preview-2"))
    assert exc_info.value.code == "INVALID_SESSION_STAGE"


def test_concurrent_same_preview_confirm_keeps_session_consistent() -> None:
    course = _course("MA100-001", "자료구조", "001")
    store = SessionStore()
    session = store.create("컴퓨터공학과", major_candidates=[course])
    _save_preview(store, session.session_id, preview_id="preview-1")
    service = MajorConfirmService(store=store, validator=BarrierValidator(parties=2))

    def confirm_once():
        return asyncio.run(service.confirm(session.session_id, "preview-1"))

    with ThreadPoolExecutor(max_workers=2) as executor:
        first_future = executor.submit(confirm_once)
        second_future = executor.submit(confirm_once)
        first = first_future.result(timeout=10)
        second = second_future.result(timeout=10)

    saved = store.get(session.session_id)
    assert first == second
    assert saved.session_stage is SessionStage.MAJOR_CONFIRMED
    assert saved.confirmed_major_preview_id == "preview-1"
    assert [course.course_id for course in saved.fixed_courses] == ["MA100-001"]
    assert saved.confirmed_major_credits == 3
