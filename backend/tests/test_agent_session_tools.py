"""Tests for framework-independent PlaNU agent session tools."""

from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone

from backend.app.agent_tools import (
    SessionCommandTools,
    SessionQueryTools,
    SessionToolErrorCode,
)
from backend.app.models import Day
from backend.app.repositories import InMemorySessionRepository
from backend.app.services.session_service import SessionService


class MutableClock:
    def __init__(self, current: datetime) -> None:
        self.current = current

    def __call__(self) -> datetime:
        return self.current

    def advance(self, delta: timedelta) -> datetime:
        self.current = self.current + delta
        return self.current


def _now() -> datetime:
    return datetime(2026, 7, 26, 12, 0, tzinfo=timezone.utc)


def _service(clock: MutableClock | None = None) -> SessionService:
    return SessionService(
        InMemorySessionRepository(),
        session_ttl=timedelta(minutes=30),
        now_provider=clock or MutableClock(_now()),
        session_id_provider=lambda: "session-1",
    )


def _toolset(clock: MutableClock | None = None) -> tuple[SessionService, SessionQueryTools, SessionCommandTools]:
    service = _service(clock)
    return service, SessionQueryTools(service), SessionCommandTools(service)


def test_get_session_summary_returns_compact_state_and_missing_information() -> None:
    service, queries, commands = _toolset()
    created = service.create_session()

    initial = queries.get_session_summary({"session_id": created.session_id})
    commands.set_department(
        {"session_id": created.session_id, "department": "컴퓨터공학부"}
    )
    commands.register_major_catalog(
        {"session_id": created.session_id, "catalog_id": "major-catalog"}
    )
    commands.add_selected_major_course(
        {"session_id": created.session_id, "course_id": "MAJ001-001"}
    )
    complete = queries.get_session_summary({"session_id": created.session_id})

    assert initial.success is True
    assert initial.changed is False
    assert initial.state_summary is not None
    assert initial.state_summary.missing_information == [
        "department",
        "major_catalog_id",
        "selected_major_course_ids",
    ]
    assert complete.state_summary is not None
    assert complete.state_summary.department == "컴퓨터공학부"
    assert complete.state_summary.major_catalog_id == "major-catalog"
    assert complete.state_summary.selected_major_course_ids == ["MAJ001-001"]
    assert complete.state_summary.missing_information == []


def test_query_tools_do_not_extend_session_times() -> None:
    clock = MutableClock(_now())
    service, queries, _commands = _toolset(clock)
    created = service.create_session()
    clock.advance(timedelta(minutes=1))

    result = queries.get_session_summary({"session_id": created.session_id})

    assert result.success is True
    found = service.get_session(created.session_id)
    assert found.updated_at == created.updated_at
    assert found.last_accessed_at == created.last_accessed_at
    assert found.expires_at == created.expires_at


def test_specific_query_tools_return_only_requested_detail_channels() -> None:
    service, queries, commands = _toolset()
    created = service.create_session()
    commands.add_required_free_day({"session_id": created.session_id, "day": "MON"})
    commands.add_preferred_course(
        {"session_id": created.session_id, "course_id": "GEN001-001"}
    )
    commands.add_selected_major_course(
        {"session_id": created.session_id, "course_id": "MAJ001-001"}
    )

    hard = queries.get_hard_constraints({"session_id": created.session_id})
    soft = queries.get_soft_preferences({"session_id": created.session_id})
    selected = queries.get_selected_major_courses({"session_id": created.session_id})

    assert hard.hard_constraints is not None
    assert hard.soft_preferences is None
    assert hard.selected_major_course_ids is None
    assert hard.hard_constraints.required_free_days == [Day.MON]
    assert soft.soft_preferences is not None
    assert soft.hard_constraints is None
    assert soft.soft_preferences.preferred_course_ids == ["GEN001-001"]
    assert selected.selected_major_course_ids == ["MAJ001-001"]
    assert selected.hard_constraints is None
    assert selected.soft_preferences is None


def test_missing_or_expired_session_returns_structured_error() -> None:
    clock = MutableClock(_now())
    service = _service(clock)
    queries = SessionQueryTools(service)
    created = service.create_session()
    clock.advance(timedelta(minutes=30))

    result = queries.get_session_summary({"session_id": created.session_id})

    assert result.success is False
    assert result.error is not None
    assert result.error.code == SessionToolErrorCode.SESSION_NOT_AVAILABLE
    assert result.session_id == created.session_id


def test_basic_command_tools_update_state_and_report_changed() -> None:
    service, _queries, commands = _toolset()
    created = service.create_session()

    department = commands.set_department(
        {"session_id": created.session_id, "department": " 컴퓨터공학부 "}
    )
    major_catalog = commands.register_major_catalog(
        {"session_id": created.session_id, "catalog_id": " major-1 "}
    )
    elective_catalog = commands.register_elective_catalog(
        {"session_id": created.session_id, "catalog_id": " elective-1 "}
    )
    added = commands.add_selected_major_course(
        {"session_id": created.session_id, "course_id": " MAJ001-001 "}
    )
    duplicate = commands.add_selected_major_course(
        {"session_id": created.session_id, "course_id": "MAJ001-001"}
    )
    missing_remove = commands.remove_selected_major_course(
        {"session_id": created.session_id, "course_id": "missing"}
    )
    replaced = commands.replace_selected_major_courses(
        {"session_id": created.session_id, "course_ids": ["MAJ002-001", "MAJ002-001"]}
    )

    assert department.changed is True
    assert major_catalog.changed is True
    assert elective_catalog.changed is True
    assert added.changed is True
    assert added.selected_major_course_ids == ["MAJ001-001"]
    assert duplicate.changed is False
    assert missing_remove.changed is False
    assert replaced.changed is True
    assert replaced.selected_major_course_ids == ["MAJ002-001"]


def test_invalid_input_returns_structured_error() -> None:
    service, _queries, commands = _toolset()
    created = service.create_session()

    result = commands.set_earliest_start_time(
        {"session_id": created.session_id, "time": "9am"}
    )

    assert result.success is False
    assert result.error is not None
    assert result.error.code == SessionToolErrorCode.INVALID_VALUE
    assert result.error.field == "time"


def test_hard_constraint_tools_delegate_rules_and_report_changed() -> None:
    service, _queries, commands = _toolset()
    created = service.create_session()

    add_day = commands.add_required_free_day(
        {"session_id": created.session_id, "day": "MON"}
    )
    duplicate_day = commands.add_required_free_day(
        {"session_id": created.session_id, "day": "MON"}
    )
    replace_days = commands.replace_required_free_days(
        {"session_id": created.session_id, "days": ["TUE", "WED"]}
    )
    set_time = commands.set_earliest_start_time(
        {"session_id": created.session_id, "time": "09:00"}
    )
    clear_time = commands.clear_earliest_start_time(
        {"session_id": created.session_id}
    )
    add_required = commands.add_required_course(
        {"session_id": created.session_id, "course_id": "GEN001-001"}
    )
    add_excluded = commands.add_excluded_course(
        {"session_id": created.session_id, "course_id": "GEN002-001"}
    )
    remove_missing = commands.remove_excluded_course(
        {"session_id": created.session_id, "course_id": "missing"}
    )
    clear_hard = commands.clear_hard_constraints({"session_id": created.session_id})

    assert add_day.changed is True
    assert duplicate_day.changed is False
    assert replace_days.hard_constraints is not None
    assert replace_days.hard_constraints.required_free_days == [Day.TUE, Day.WED]
    assert set_time.changed is True
    assert clear_time.changed is True
    assert add_required.hard_constraints is not None
    assert add_required.hard_constraints.required_course_ids == ["GEN001-001"]
    assert add_excluded.hard_constraints is not None
    assert add_excluded.hard_constraints.excluded_course_ids == ["GEN002-001"]
    assert remove_missing.changed is False
    assert clear_hard.changed is True
    assert clear_hard.hard_constraints is not None
    assert clear_hard.hard_constraints.required_course_ids == []


def test_soft_preference_tools_delegate_rules_and_report_changed() -> None:
    service, _queries, commands = _toolset()
    created = service.create_session()

    add_day = commands.add_preferred_free_day(
        {"session_id": created.session_id, "day": "FRI"}
    )
    duplicate_day = commands.add_preferred_free_day(
        {"session_id": created.session_id, "day": "FRI"}
    )
    replace_days = commands.replace_preferred_free_days(
        {"session_id": created.session_id, "days": ["THU"]}
    )
    set_start = commands.set_preferred_earliest_start_time(
        {"session_id": created.session_id, "time": "10:00"}
    )
    clear_start = commands.clear_preferred_earliest_start_time(
        {"session_id": created.session_id}
    )
    set_end = commands.set_preferred_latest_end_time(
        {"session_id": created.session_id, "time": "17:00"}
    )
    clear_end = commands.clear_preferred_latest_end_time(
        {"session_id": created.session_id}
    )
    preferred = commands.add_preferred_course(
        {"session_id": created.session_id, "course_id": "GEN001-001"}
    )
    disliked = commands.add_disliked_course(
        {"session_id": created.session_id, "course_id": "GEN002-001"}
    )
    compact = commands.set_compact_schedule_preference(
        {"session_id": created.session_id, "value": True}
    )
    clear_compact = commands.clear_compact_schedule_preference(
        {"session_id": created.session_id}
    )
    clear_soft = commands.clear_soft_preferences({"session_id": created.session_id})

    assert add_day.changed is True
    assert duplicate_day.changed is False
    assert replace_days.soft_preferences is not None
    assert replace_days.soft_preferences.preferred_free_days == [Day.THU]
    assert set_start.changed is True
    assert clear_start.changed is True
    assert set_end.changed is True
    assert clear_end.changed is True
    assert preferred.soft_preferences is not None
    assert preferred.soft_preferences.preferred_course_ids == ["GEN001-001"]
    assert disliked.soft_preferences is not None
    assert disliked.soft_preferences.disliked_course_ids == ["GEN002-001"]
    assert compact.soft_preferences is not None
    assert compact.soft_preferences.compact_schedule is True
    assert clear_compact.changed is True
    assert clear_soft.changed is True


def test_soft_conflict_service_error_is_structured() -> None:
    service, _queries, commands = _toolset()
    created = service.create_session()
    commands.add_excluded_course(
        {"session_id": created.session_id, "course_id": "GEN001-001"}
    )

    result = commands.add_preferred_course(
        {"session_id": created.session_id, "course_id": "GEN001-001"}
    )

    assert result.success is False
    assert result.error is not None
    assert result.error.code == SessionToolErrorCode.CONFLICTING_CONSTRAINT
    assert result.error.field == "preferred_course_ids"


def test_clear_all_preferences_wraps_existing_service_method() -> None:
    service, _queries, commands = _toolset()
    created = service.create_session()
    commands.add_required_course(
        {"session_id": created.session_id, "course_id": "GEN001-001"}
    )
    commands.add_preferred_course(
        {"session_id": created.session_id, "course_id": "GEN002-001"}
    )

    result = commands.clear_all_preferences({"session_id": created.session_id})

    assert result.changed is True
    assert result.hard_constraints is not None
    assert result.soft_preferences is not None
    assert result.hard_constraints.required_course_ids == []
    assert result.soft_preferences.preferred_course_ids == []


def test_tool_modules_do_not_directly_depend_on_repositories() -> None:
    command_source = inspect.getsource(SessionCommandTools)
    query_source = inspect.getsource(SessionQueryTools)

    assert "_repository" not in command_source
    assert "_repository" not in query_source
    assert "InMemorySessionRepository" not in command_source
    assert "InMemorySessionRepository" not in query_source
