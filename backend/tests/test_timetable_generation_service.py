"""Tests for session-backed timetable candidate generation."""

from __future__ import annotations

import pytest

from backend.app.core.errors import AppError
from backend.app.models import (
    Category,
    ClassTime,
    Course,
    CourseLoadTarget,
    Day,
    GeneralCoursePoolResult,
    GeneralCoursePools,
    PreferenceRules,
)
from backend.app.services.session_store import SessionStage, SessionStore
from backend.app.services.timetable_generation_service import TimetableGenerationService
from backend.app.services.timetable_generator import TimetableGenerator


def _course(
    course_id: str,
    name: str,
    category: Category,
    *,
    day: Day = Day.MON,
    start: str = "09:00",
    end: str = "10:00",
    credit: float = 3,
    area: int | None = None,
    division: str = "001",
) -> Course:
    return Course(
        course_id=course_id,
        course_name=name,
        category=category,
        area=area,
        credit=credit,
        division=division,
        professor="김교수",
        class_times=[
            ClassTime(
                day=day,
                start=start,
                end=end,
                classroom="강의실",
                building_code="A",
            )
        ],
    )


def _major(course_id: str = "MAJ-001", *, credit: float = 9) -> Course:
    return _course(course_id, "자료구조", Category.MAJOR_REQUIRED, credit=credit)


def _required(course_id: str, *, day: Day = Day.TUE, start: str = "10:00") -> Course:
    return _course(
        course_id,
        "고전읽기와토론",
        Category.GENERAL_REQUIRED,
        day=day,
        start=start,
        end="11:00",
        credit=2,
    )


def _elective(course_id: str, *, day: Day = Day.WED, start: str = "13:00") -> Course:
    return _course(
        course_id,
        f"교양선택 {course_id}",
        Category.GENERAL_ELECTIVE,
        day=day,
        start=start,
        end="14:00",
        credit=3,
        area=1,
    )


def test_detailed_generation_keeps_fixed_major_and_records_load_metadata() -> None:
    major = _major()
    required = _required("REQ-001")
    elective = _elective("ELE-001")

    result = TimetableGenerator().generate_detailed(
        fixed_major_courses=[major],
        required_general_candidates=[required],
        elective_general_candidates=[elective],
        course_load_target=CourseLoadTarget(
            target_total_credits=14,
            additional_elective_count=1,
        ),
    )

    assert result.candidates
    best = result.candidates[0]
    assert [course.course_id for course in best.timetable.courses] == [
        "MAJ-001",
        "REQ-001",
        "ELE-001",
    ]
    assert best.load_satisfaction.final_total_credits == 14
    assert best.load_satisfaction.required_general_count == 1
    assert best.load_satisfaction.elective_count == 1
    assert best.load_satisfaction.credit_gap == 0
    assert best.load_satisfaction.within_credit_limit is True
    assert best.load_satisfaction.elective_count_gap == 0


def test_target_total_credit_is_hard_upper_bound() -> None:
    result = TimetableGenerator().generate_detailed(
        fixed_major_courses=[_major(credit=15)],
        required_general_candidates=[_required("REQ-001")],
        elective_general_candidates=[_elective("ELE-001")],
        course_load_target=CourseLoadTarget(
            target_total_credits=18,
            additional_elective_count=2,
        ),
    )

    assert result.candidates
    assert all(
        candidate.load_satisfaction.final_total_credits <= 18
        for candidate in result.candidates
    )
    assert max(
        candidate.load_satisfaction.elective_count
        for candidate in result.candidates
    ) == 1
    assert any(
        diagnostic.reason_code == "ELECTIVE_TARGET_NOT_MET"
        for diagnostic in result.diagnostics
    )


def test_time_conflict_duplicate_logical_course_and_hard_conditions_are_excluded() -> None:
    major = _major()
    conflicting = _required("REQ-CONFLICT", day=Day.MON, start="09:30")
    duplicate_section = _course(
        "REQ-002",
        "고전읽기와토론",
        Category.GENERAL_REQUIRED,
        day=Day.THU,
        start="12:00",
        end="13:00",
        credit=2,
    )
    valid = _course(
        "REQ-003",
        "대학영어",
        Category.GENERAL_REQUIRED,
        day=Day.FRI,
        start="12:00",
        end="13:00",
        credit=2,
    )

    result = TimetableGenerator().generate_detailed(
        fixed_major_courses=[major],
        required_general_candidates=[conflicting, duplicate_section, valid],
        hard_conditions=PreferenceRules(excluded_days=[Day.FRI]),
    )

    assert all(
        "REQ-CONFLICT" not in [course.course_id for course in candidate.timetable.courses]
        for candidate in result.candidates
    )
    assert all(
        "REQ-003" not in [course.course_id for course in candidate.timetable.courses]
        for candidate in result.candidates
    )
    assert any(
        diagnostic.reason_code == "ALL_CANDIDATES_TIME_CONFLICT"
        for diagnostic in result.diagnostics
    )
    assert any(
        diagnostic.reason_code == "ALL_CANDIDATES_HARD_CONDITION_FAILED"
        for diagnostic in result.diagnostics
    )


def test_generation_service_requires_general_ready_and_saves_result() -> None:
    store = SessionStore()
    major = _major()
    session = store.create("컴퓨터공학과")
    store.update(
        session.session_id,
        fixed_courses=[major],
        confirmed_major_credits=9,
        session_stage=SessionStage.GENERAL_READY,
    )
    store.update_general_course_pool(
        session.session_id,
        type(
            "PoolResult",
            (),
            {
                "pools": type(
                    "Pools",
                    (),
                    {
                        "required_courses": [_required("REQ-001")],
                        "elective_courses": [_elective("ELE-001")],
                    },
                )(),
                "excluded_courses": [],
                "warnings": [],
            },
        )(),
    )

    result = TimetableGenerationService(store=store).generate_for_session(
        session_id=session.session_id,
        course_load_target=CourseLoadTarget(additional_elective_count=1),
    )

    saved = store.get(session.session_id)
    assert result.candidates
    assert saved.generated_timetable_candidates == result.candidates
    assert saved.generation_course_load_target is not None
    assert saved.generated_at is not None


def test_generation_service_rejects_wrong_stage_without_partial_save() -> None:
    store = SessionStore()
    session = store.create("컴퓨터공학과")

    with pytest.raises(AppError) as exc_info:
        TimetableGenerationService(store=store).generate_for_session(
            session_id=session.session_id,
        )

    saved = store.get(session.session_id)
    assert exc_info.value.code == "INVALID_SESSION_STAGE"
    assert saved.generated_timetable_candidates == []


def test_generation_service_rejects_confirmed_major_credit_mismatch() -> None:
    store = SessionStore()
    session = store.create("컴퓨터공학과")
    store.update(
        session.session_id,
        fixed_courses=[_major(credit=9)],
        confirmed_major_credits=6,
        session_stage=SessionStage.GENERAL_READY,
    )

    with pytest.raises(AppError) as exc_info:
        TimetableGenerationService(store=store).generate_for_session(
            session_id=session.session_id,
        )

    assert exc_info.value.code == "CONFIRMED_MAJOR_CREDIT_MISMATCH"


def test_generation_service_returns_fixed_major_integrity_diagnostic() -> None:
    first = _major("MAJ-001", credit=3)
    second = _course(
        "MAJ-002",
        "운영체제",
        Category.MAJOR_REQUIRED,
        day=Day.MON,
        start="09:30",
        end="10:30",
        credit=3,
    )
    store = SessionStore()
    session = store.create("컴퓨터공학과")
    store.update(
        session.session_id,
        fixed_courses=[first, second],
        confirmed_major_credits=6,
        session_stage=SessionStage.GENERAL_READY,
    )

    result = TimetableGenerationService(store=store).generate_for_session(
        session_id=session.session_id,
    )

    assert result.candidates == []
    assert result.diagnostics[0].reason_code == "FIXED_MAJOR_INTEGRITY_ERROR"


def test_generation_service_returns_major_credits_exceed_target_diagnostic() -> None:
    store = SessionStore()
    session = store.create("컴퓨터공학과")
    store.update(
        session.session_id,
        fixed_courses=[_major(credit=15)],
        confirmed_major_credits=15,
        session_stage=SessionStage.GENERAL_READY,
    )

    result = TimetableGenerationService(store=store).generate_for_session(
        session_id=session.session_id,
        course_load_target=CourseLoadTarget(target_total_credits=12),
    )

    assert result.candidates == []
    assert result.diagnostics[0].reason_code == "MAJOR_CREDITS_EXCEED_TARGET"


def test_generation_service_marks_truncated_when_max_candidates_reached() -> None:
    store = SessionStore()
    session = store.create("컴퓨터공학과")
    store.update(
        session.session_id,
        fixed_courses=[_major(credit=3)],
        confirmed_major_credits=3,
        session_stage=SessionStage.GENERAL_READY,
    )
    store.update_general_course_pool(
        session.session_id,
        GeneralCoursePoolResult(
            pools=GeneralCoursePools(
                elective_courses=[
                    _elective("ELE-001", day=Day.TUE, start="10:00"),
                    _elective("ELE-002", day=Day.WED, start="11:00"),
                    _elective("ELE-003", day=Day.THU, start="12:00"),
                ],
            )
        ),
    )

    result = TimetableGenerationService(store=store).generate_for_session(
        session_id=session.session_id,
        course_load_target=CourseLoadTarget(target_total_credits=12),
        max_candidates=1,
    )

    assert result.truncated is True
    assert any(
        diagnostic.reason_code == "GENERATION_TRUNCATED"
        for diagnostic in result.diagnostics
    )


def test_generation_service_uses_standard_session_not_found_error() -> None:
    with pytest.raises(AppError) as exc_info:
        TimetableGenerationService(store=SessionStore()).generate_for_session(
            session_id="missing-session",
        )

    assert exc_info.value.code == "SESSION_NOT_FOUND"
    assert exc_info.value.status_code == 404
