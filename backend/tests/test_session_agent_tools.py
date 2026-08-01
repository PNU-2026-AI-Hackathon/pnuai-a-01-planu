"""Tests for intent-level session tools exposed to future LLM agents."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backend.app.agent_tools import SessionAgentTools, SessionToolErrorCode
from backend.app.models import Day, PlanuSessionState
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


class CountingSessionRepository:
    def __init__(self) -> None:
        self.inner = InMemorySessionRepository()
        self.save_count = 0

    def create(self, state: PlanuSessionState, *, now: datetime) -> PlanuSessionState:
        return self.inner.create(state, now=now)

    def get(self, session_id: str, *, now: datetime) -> PlanuSessionState | None:
        return self.inner.get(session_id, now=now)

    def save(self, state: PlanuSessionState, *, now: datetime) -> PlanuSessionState:
        self.save_count += 1
        return self.inner.save(state, now=now)

    def delete(self, session_id: str) -> None:
        self.inner.delete(session_id)

    def touch(
        self,
        session_id: str,
        *,
        now: datetime,
        last_accessed_at: datetime,
        expires_at: datetime,
    ) -> PlanuSessionState:
        return self.inner.touch(
            session_id,
            now=now,
            last_accessed_at=last_accessed_at,
            expires_at=expires_at,
        )

    def delete_expired(self, *, now: datetime) -> int:
        return self.inner.delete_expired(now=now)


def _now() -> datetime:
    return datetime(2026, 7, 26, 12, 0, tzinfo=timezone.utc)


def _service(
    clock: MutableClock | None = None,
    repository: CountingSessionRepository | None = None,
) -> SessionService:
    return SessionService(
        repository or CountingSessionRepository(),
        session_ttl=timedelta(minutes=30),
        now_provider=clock or MutableClock(_now()),
        session_id_provider=lambda: "session-1",
    )


def _tools(
    clock: MutableClock | None = None,
    repository: CountingSessionRepository | None = None,
) -> tuple[SessionService, SessionAgentTools]:
    service = _service(clock, repository)
    return service, SessionAgentTools(service)


def test_update_session_profile_updates_multiple_fields_and_clears_explicitly() -> None:
    service, tools = _tools()
    created = service.create_session()

    first = tools.update_session_profile(
        {
            "session_id": created.session_id,
            "department": "컴퓨터공학부",
            "major_catalog_id": "major-1",
            "elective_catalog_id": "elective-1",
        }
    )
    second = tools.update_session_profile(
        {
            "session_id": created.session_id,
            "major_catalog_id": "major-2",
            "clear_fields": ["elective_catalog_id"],
        }
    )

    assert first.success is True
    assert first.changed_fields == [
        "department",
        "major_catalog_id",
        "elective_catalog_id",
    ]
    assert second.changed_fields == ["major_catalog_id", "elective_catalog_id"]
    assert second.state_summary is not None
    assert second.state_summary.department == "컴퓨터공학부"
    assert second.state_summary.major_catalog_id == "major-2"
    assert second.state_summary.elective_catalog_id is None


def test_update_session_profile_rejects_empty_strings() -> None:
    service, tools = _tools()
    created = service.create_session()

    result = tools.update_session_profile(
        {"session_id": created.session_id, "department": ""}
    )

    assert result.success is False
    assert result.error is not None
    assert result.error.code == SessionToolErrorCode.INVALID_VALUE
    assert result.error.field == "department"


def test_update_selected_major_courses_modes_deduplicate_and_keep_order() -> None:
    service, tools = _tools()
    created = service.create_session()

    replaced = tools.update_selected_major_courses(
        {
            "session_id": created.session_id,
            "course_ids": ["MAJ002-001", "MAJ001-001", "MAJ002-001"],
        }
    )
    added = tools.update_selected_major_courses(
        {
            "session_id": created.session_id,
            "mode": "add",
            "course_ids": ["MAJ003-001", "MAJ001-001"],
        }
    )
    removed = tools.update_selected_major_courses(
        {
            "session_id": created.session_id,
            "mode": "remove",
            "course_ids": ["missing", "MAJ002-001"],
        }
    )
    missing_remove = tools.update_selected_major_courses(
        {
            "session_id": created.session_id,
            "mode": "remove",
            "course_ids": ["missing"],
        }
    )

    assert replaced.state_summary is not None
    assert replaced.state_summary.selected_major_course_ids == [
        "MAJ002-001",
        "MAJ001-001",
    ]
    assert added.state_summary is not None
    assert added.state_summary.selected_major_course_ids == [
        "MAJ002-001",
        "MAJ001-001",
        "MAJ003-001",
    ]
    assert removed.state_summary is not None
    assert removed.state_summary.selected_major_course_ids == [
        "MAJ001-001",
        "MAJ003-001",
    ]
    assert removed.changed_fields == ["selected_major_course_ids"]
    assert missing_remove.changed_fields == []


def test_update_selected_major_courses_rejects_empty_id() -> None:
    service, tools = _tools()
    created = service.create_session()

    result = tools.update_selected_major_courses(
        {"session_id": created.session_id, "course_ids": ["MAJ001-001", " "]}
    )

    assert result.success is False
    assert result.error is not None
    assert result.error.code == SessionToolErrorCode.INVALID_VALUE
    assert result.error.field == "course_ids"


def test_update_timetable_preferences_hard_priority_over_soft_in_one_request() -> None:
    service, tools = _tools()
    created = service.create_session()

    result = tools.update_timetable_preferences(
        {
            "session_id": created.session_id,
            "hard": {
                "required_free_days": ["MON"],
                "required_course_ids": ["GEN001-001"],
                "excluded_course_ids": ["GEN002-001"],
            },
            "soft": {
                "preferred_free_days": ["MON", "TUE"],
                "preferred_course_ids": ["GEN002-001", "GEN003-001"],
                "disliked_course_ids": ["GEN001-001", "GEN004-001"],
            },
        }
    )

    assert result.success is True
    assert result.state_summary is not None
    summary = result.state_summary
    assert summary.hard_constraints.required_free_days == [Day.MON]
    assert summary.hard_constraints.required_course_ids == ["GEN001-001"]
    assert summary.hard_constraints.excluded_course_ids == ["GEN002-001"]
    assert summary.soft_preferences.preferred_free_days == [Day.TUE]
    assert summary.soft_preferences.preferred_course_ids == ["GEN003-001"]
    assert summary.soft_preferences.disliked_course_ids == ["GEN004-001"]


def test_update_timetable_preferences_updates_many_fields_and_preserves_omitted() -> None:
    service, tools = _tools()
    created = service.create_session()
    tools.update_timetable_preferences(
        {
            "session_id": created.session_id,
            "hard": {
                "required_free_days": ["MON"],
                "earliest_start_time": "09:00",
            },
            "soft": {
                "preferred_course_ids": ["GEN001-001"],
                "compact_schedule": True,
            },
        }
    )

    result = tools.update_timetable_preferences(
        {
            "session_id": created.session_id,
            "hard": {"latest_end_time": "18:00"},
            "soft": {"preferred_latest_end_time": "17:00"},
        }
    )

    assert result.state_summary is not None
    hard = result.state_summary.hard_constraints
    soft = result.state_summary.soft_preferences
    assert hard.required_free_days == [Day.MON]
    assert hard.earliest_start_time == "09:00"
    assert hard.latest_end_time == "18:00"
    assert soft.preferred_course_ids == ["GEN001-001"]
    assert soft.compact_schedule is True
    assert soft.preferred_latest_end_time == "17:00"
    assert result.changed_fields == [
        "hard_constraints.latest_end_time",
        "soft_preferences.preferred_latest_end_time",
    ]


def test_update_timetable_preferences_clear_fields_only_clear_named_fields() -> None:
    service, tools = _tools()
    created = service.create_session()
    tools.update_timetable_preferences(
        {
            "session_id": created.session_id,
            "hard": {
                "required_free_days": ["MON"],
                "earliest_start_time": "09:00",
                "latest_end_time": "18:00",
            },
            "soft": {
                "preferred_course_ids": ["GEN001-001"],
                "compact_schedule": True,
            },
        }
    )

    result = tools.update_timetable_preferences(
        {
            "session_id": created.session_id,
            "hard": {"clear_fields": ["earliest_start_time"]},
            "soft": {"clear_fields": ["compact_schedule"]},
        }
    )

    assert result.state_summary is not None
    assert result.state_summary.hard_constraints.required_free_days == [Day.MON]
    assert result.state_summary.hard_constraints.earliest_start_time is None
    assert result.state_summary.hard_constraints.latest_end_time == "18:00"
    assert result.state_summary.soft_preferences.preferred_course_ids == ["GEN001-001"]
    assert result.state_summary.soft_preferences.compact_schedule is None
    assert result.changed_fields == [
        "hard_constraints.earliest_start_time",
        "soft_preferences.compact_schedule",
    ]


def test_update_timetable_preferences_errors_for_invalid_time_and_range() -> None:
    service, tools = _tools()
    created = service.create_session()

    invalid_time = tools.update_timetable_preferences(
        {"session_id": created.session_id, "hard": {"earliest_start_time": "9am"}}
    )
    invalid_range = tools.update_timetable_preferences(
        {
            "session_id": created.session_id,
            "hard": {
                "earliest_start_time": "18:00",
                "latest_end_time": "10:00",
            },
        }
    )

    assert invalid_time.success is False
    assert invalid_time.error is not None
    assert invalid_time.error.code == SessionToolErrorCode.INVALID_VALUE
    assert invalid_time.error.field == "hard.earliest_start_time"
    assert invalid_range.success is False
    assert invalid_range.error is not None
    assert invalid_range.error.code == SessionToolErrorCode.INVALID_VALUE
    assert invalid_range.error.field == "earliest_start_time"


def test_update_timetable_preferences_missing_session_and_idempotent_request() -> None:
    clock = MutableClock(_now())
    service, tools = _tools(clock)
    created = service.create_session()
    first = tools.update_timetable_preferences(
        {
            "session_id": created.session_id,
            "hard": {"required_free_days": ["MON"]},
        }
    )
    same = tools.update_timetable_preferences(
        {
            "session_id": created.session_id,
            "hard": {"required_free_days": ["MON"]},
        }
    )
    clock.advance(timedelta(minutes=30))
    expired = tools.update_timetable_preferences(
        {
            "session_id": created.session_id,
            "hard": {"required_free_days": ["TUE"]},
        }
    )

    assert first.changed_fields == ["hard_constraints.required_free_days"]
    assert same.success is True
    assert same.changed_fields == []
    assert expired.success is False
    assert expired.error is not None
    assert expired.error.code == SessionToolErrorCode.SESSION_NOT_AVAILABLE


def test_update_timetable_preferences_uses_one_repository_save() -> None:
    repository = CountingSessionRepository()
    service, tools = _tools(repository=repository)
    created = service.create_session()

    result = tools.update_timetable_preferences(
        {
            "session_id": created.session_id,
            "hard": {
                "required_free_days": ["MON"],
                "earliest_start_time": "09:00",
                "required_course_ids": ["GEN001-001"],
            },
            "soft": {
                "preferred_free_days": ["TUE"],
                "preferred_latest_end_time": "17:00",
                "compact_schedule": True,
            },
        }
    )

    assert result.success is True
    assert repository.save_count == 1


def test_reset_session_preferences_targets_only_preferences() -> None:
    service, tools = _tools()
    created = service.create_session()
    tools.update_session_profile(
        {
            "session_id": created.session_id,
            "department": "컴퓨터공학부",
            "major_catalog_id": "major-1",
        }
    )
    tools.update_selected_major_courses(
        {"session_id": created.session_id, "course_ids": ["MAJ001-001"]}
    )
    tools.update_timetable_preferences(
        {
            "session_id": created.session_id,
            "hard": {"required_course_ids": ["GEN001-001"]},
            "soft": {"preferred_course_ids": ["GEN002-001"]},
        }
    )

    result = tools.reset_session_preferences(
        {"session_id": created.session_id, "target": "all"}
    )

    assert result.changed_fields == [
        "hard_constraints.required_course_ids",
        "soft_preferences.preferred_course_ids",
    ]
    assert result.state_summary is not None
    assert result.state_summary.department == "컴퓨터공학부"
    assert result.state_summary.major_catalog_id == "major-1"
    assert result.state_summary.selected_major_course_ids == ["MAJ001-001"]
    assert result.state_summary.hard_constraints.required_course_ids == []
    assert result.state_summary.soft_preferences.preferred_course_ids == []
