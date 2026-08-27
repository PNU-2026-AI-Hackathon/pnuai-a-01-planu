"""Tests for deterministic condition summaries and generation confirmation gate."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backend.app.agent_tools import SessionAgentTools, SessionToolErrorCode
from backend.app.agent_tools.timetable_generation_tools import TimetableGenerationTools
from backend.app.models import Category, ClassTime, Course, Day, GeneralCoursePoolResult, GeneralCoursePools
from backend.app.models.timetable_generation import (
    GenerationFailureCode,
    SearchTerminationReason,
    TimetableGenerationRequest,
    TimetableGenerationResult,
)
from backend.app.repositories import InMemorySessionRepository, SessionStoreRepository
from backend.app.services.condition_summary_service import ConditionSummaryService
from backend.app.services.session_service import SessionService
from backend.app.services.session_store import SessionStore


class MutableClock:
    def __init__(self) -> None:
        self.current = datetime(2026, 7, 26, 12, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.current

    def advance(self) -> None:
        self.current += timedelta(minutes=1)


class FakeGenerationService:
    def __init__(self) -> None:
        self.called = False

    def generate(self, _request: TimetableGenerationRequest) -> TimetableGenerationResult:
        self.called = True
        return TimetableGenerationResult(
            success=True,
            candidates=[],
            total_candidates_found=0,
            search_nodes_visited=0,
            search_truncated=False,
            termination_reason=SearchTerminationReason.SEARCH_EXHAUSTED,
            message="generated",
        )


class FakeValidationService:
    pass


def _service() -> SessionService:
    return SessionService(
        InMemorySessionRepository(),
        session_id_provider=lambda: "session-1",
        now_provider=MutableClock(),
    )


def _ready_session(service: SessionService) -> str:
    state = service.create_session()
    service.update_profile(
        state.session_id,
        type(
            "Update",
            (),
            {
                "department": "컴퓨터공학부",
                "major_catalog_id": "session-1:major",
                "elective_catalog_id": None,
                "clear_fields": (),
            },
        )(),
    )
    service.update_selected_major_courses(state.session_id, ["MAJ-001"])
    return state.session_id


def _confirm(service: SessionService, session_id: str) -> None:
    result = SessionAgentTools(service, ConditionSummaryService()).confirm_timetable_conditions(
        {"session_id": session_id}
    )
    assert result.success is True
    state = service.get_session(session_id)
    assert state.generation_preferences_confirmed_at is not None
    assert state.generation_preferences_confirmed_version is not None


def _assert_confirmation_cleared(service: SessionService, session_id: str) -> None:
    state = service.get_session(session_id)
    assert state.generation_preferences_confirmed_at is None
    assert state.generation_preferences_confirmed_version is None


def _profile_update(**kwargs):
    return type(
        "Update",
        (),
        {
            "department": None,
            "major_catalog_id": None,
            "elective_catalog_id": None,
            "clear_fields": (),
            **kwargs,
        },
    )()


def _soft_patch(**kwargs):
    return type(
        "SoftPatch",
        (),
        {
            "preferred_free_days": None,
            "preferred_earliest_start_time": None,
            "preferred_latest_end_time": None,
            "preferred_course_ids": None,
            "disliked_course_ids": None,
            "compact_schedule": None,
            "clear_fields": (),
            **kwargs,
        },
    )()


def _course(course_id: str, name: str = "교양") -> Course:
    return Course(
        course_id=course_id,
        course_name=name,
        category=Category.GENERAL_ELECTIVE,
        area=1,
        credit=3,
        division="001",
        professor="김교수",
        class_times=[
            ClassTime(
                day=Day.MON,
                start="09:00",
                end="10:00",
                classroom="101",
                building_code="A",
            )
        ],
    )


def test_condition_summary_separates_hard_and_soft_items() -> None:
    service = _service()
    session_id = _ready_session(service)
    service.update_preferences(
        session_id,
        hard_patch=type(
            "HardPatch",
            (),
            {
                "required_free_days": [Day.FRI],
                "earliest_start_time": None,
                "latest_end_time": "18:00",
                "required_course_ids": ["MAJ-001"],
                "excluded_course_ids": [],
                "clear_fields": (),
            },
        )(),
        soft_patch=type(
            "SoftPatch",
            (),
            {
                "preferred_free_days": [],
                "preferred_earliest_start_time": "10:00",
                "preferred_latest_end_time": None,
                "preferred_course_ids": ["GEN-001"],
                "disliked_course_ids": [],
                "compact_schedule": None,
                "clear_fields": (),
            },
        )(),
    )

    summary = ConditionSummaryService().summarize(service.get_session(session_id))

    hard = {item.key: item for item in summary.hard_constraints}
    soft = {item.key: item for item in summary.soft_preferences}
    assert hard["required_free_days"].display_value == "금요일"
    assert hard["excluded_course_ids"].status == "EMPTY"
    assert hard["excluded_course_ids"].display_value == "없음"
    assert hard["earliest_start_time"].status == "UNSET"
    assert soft["preferred_earliest_start_time"].display_value == "10:00 이후 선호"
    assert soft["compact_schedule"].status == "UNSET"
    assert summary.selected_major_courses[0].course_id == "MAJ-001"


def test_condition_summary_marks_english_placement_course_with_notice() -> None:
    service = _service()
    state = service.create_session()
    service.update_preferences(
        state.session_id,
        hard_patch=type(
            "HardPatch",
            (),
            {
                "required_free_days": [],
                "earliest_start_time": None,
                "latest_end_time": None,
                "required_course_ids": ["ZE1000113-001"],
                "excluded_course_ids": [],
                "clear_fields": (),
            },
        )(),
    )

    result = ConditionSummaryService().summarize(service.get_session(state.session_id))

    required = next(item for item in result.hard_constraints if item.key == "required_course_ids")
    assert required.status == "SET"
    assert required.metadata["notice_code"] == "ENGLISH_PLACEMENT_ELIGIBILITY"
    assert "수능 성적" in required.metadata["notice"]


def test_confirm_tool_fails_when_generation_is_not_ready() -> None:
    service = _service()
    state = service.create_session()
    tools = SessionAgentTools(service, ConditionSummaryService())

    result = tools.confirm_timetable_conditions({"session_id": state.session_id})

    assert result.success is False
    assert result.error is not None
    assert result.error.code == SessionToolErrorCode.TIMETABLE_GENERATION_NOT_READY


def test_confirm_tool_sets_current_revision_and_hard_change_invalidates() -> None:
    service = _service()
    session_id = _ready_session(service)
    tools = SessionAgentTools(service, ConditionSummaryService())

    confirmed = tools.confirm_timetable_conditions({"session_id": session_id})
    state = service.get_session(session_id)
    assert confirmed.success is True
    assert state.generation_preferences_confirmed_at is not None
    assert state.generation_preferences_confirmed_version is not None

    service.add_required_free_day(session_id, Day.FRI)
    changed = service.get_session(session_id)
    assert changed.generation_preferences_confirmed_at is None
    assert changed.generation_preferences_confirmed_version is None


def test_read_only_summary_keeps_confirmation() -> None:
    service = _service()
    session_id = _ready_session(service)
    tools = SessionAgentTools(service, ConditionSummaryService())
    tools.confirm_timetable_conditions({"session_id": session_id})
    before = service.get_session(session_id)

    tools.get_session_summary({"session_id": session_id})
    after = service.get_session(session_id)

    assert after.generation_preferences_confirmed_at == before.generation_preferences_confirmed_at
    assert after.generation_preferences_confirmed_version == before.generation_preferences_confirmed_version


def test_generation_tool_rejects_until_conditions_are_confirmed() -> None:
    service = _service()
    session_id = _ready_session(service)
    generation_service = FakeGenerationService()
    tools = TimetableGenerationTools(
        generation_service=generation_service,
        validation_service=FakeValidationService(),
        session_service=service,
        condition_summary_service=ConditionSummaryService(),
    )

    result = tools.generate_timetable_candidates({"session_id": session_id})

    assert result.success is False
    assert result.error is not None
    assert result.error.code == GenerationFailureCode.TIMETABLE_CONDITIONS_NOT_CONFIRMED
    assert generation_service.called is False


def test_soft_preference_change_invalidates_confirmation() -> None:
    service = _service()
    session_id = _ready_session(service)
    _confirm(service, session_id)

    service.update_preferences(session_id, soft_patch=_soft_patch(compact_schedule=True))

    _assert_confirmation_cleared(service, session_id)


def test_selected_major_course_change_invalidates_confirmation() -> None:
    service = _service()
    session_id = _ready_session(service)
    _confirm(service, session_id)

    service.update_selected_major_courses(session_id, ["MAJ-002"])

    _assert_confirmation_cleared(service, session_id)


def test_department_change_invalidates_confirmation() -> None:
    service = _service()
    session_id = _ready_session(service)
    _confirm(service, session_id)

    service.update_profile(session_id, _profile_update(department="전자공학과"))

    _assert_confirmation_cleared(service, session_id)


def test_major_catalog_change_invalidates_confirmation() -> None:
    service = _service()
    session_id = _ready_session(service)
    _confirm(service, session_id)

    service.update_profile(session_id, _profile_update(major_catalog_id="session-1:new-major"))

    _assert_confirmation_cleared(service, session_id)


def test_elective_catalog_change_invalidates_confirmation() -> None:
    service = _service()
    session_id = _ready_session(service)
    _confirm(service, session_id)

    service.update_profile(session_id, _profile_update(elective_catalog_id="session-1:elective"))

    _assert_confirmation_cleared(service, session_id)


def test_general_catalog_input_change_invalidates_confirmation_in_session_store() -> None:
    store = SessionStore()
    service = SessionService(
        SessionStoreRepository(store),
        session_ttl=store.ttl,
        now_provider=store._clock,
        session_id_provider=lambda: "session-1",
    )
    session_id = _ready_session(service)
    _confirm(service, session_id)
    pools = GeneralCoursePools(required_courses=[], elective_courses=[_course("GEN-001")])
    result = GeneralCoursePoolResult(
        pools=pools,
        excluded_courses=[],
        warnings=[],
    )

    store.update_general_course_pool(session_id, result)

    _assert_confirmation_cleared(service, session_id)
