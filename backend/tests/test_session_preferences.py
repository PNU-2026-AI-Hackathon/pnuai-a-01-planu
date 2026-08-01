"""Tests for session-scoped hard constraints and soft preferences."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from backend.app.models import Day, HardConstraints, PlanuSessionState, SoftPreferences
from backend.app.repositories import InMemorySessionRepository
from backend.app.services.exceptions import (
    InvalidSessionStateValueError,
    SessionNotAvailableError,
)
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


def _state(session_id: str) -> PlanuSessionState:
    now = _now()
    return PlanuSessionState(
        session_id=session_id,
        created_at=now,
        updated_at=now,
        last_accessed_at=now,
        expires_at=now + timedelta(minutes=30),
    )


def _service(
    *,
    clock: MutableClock | None = None,
    repository: InMemorySessionRepository | None = None,
) -> SessionService:
    return SessionService(
        repository or InMemorySessionRepository(),
        now_provider=clock or MutableClock(_now()),
        session_id_provider=lambda: "session-1",
    )


def test_empty_preference_models_and_new_sessions_have_independent_defaults() -> None:
    hard = HardConstraints()
    soft = SoftPreferences()
    first = _state("session-1")
    second = _state("session-2")

    first.hard_constraints.required_free_days.append(Day.MON)
    first.soft_preferences.preferred_course_ids.append("GEN001-001")

    assert hard.required_free_days == []
    assert soft.compact_schedule is None
    assert second.hard_constraints.required_free_days == []
    assert second.soft_preferences.preferred_course_ids == []


def test_preference_models_deduplicate_and_reject_invalid_values() -> None:
    hard = HardConstraints(
        required_free_days=["FRI", "FRI", "MON"],
        required_course_ids=[" GEN001-001 ", "GEN001-001"],
    )
    soft = SoftPreferences(
        preferred_free_days=["TUE", "TUE"],
        preferred_course_ids=["GEN002-001", "GEN002-001"],
    )

    assert hard.required_free_days == [Day.FRI, Day.MON]
    assert hard.required_course_ids == ["GEN001-001"]
    assert soft.preferred_free_days == [Day.TUE]
    assert soft.preferred_course_ids == ["GEN002-001"]

    with pytest.raises(ValidationError):
        HardConstraints(required_course_ids=[" "])
    with pytest.raises(ValidationError, match="both required and excluded"):
        HardConstraints(required_course_ids=["GEN001-001"], excluded_course_ids=["GEN001-001"])
    with pytest.raises(ValidationError, match="both preferred and disliked"):
        SoftPreferences(preferred_course_ids=["GEN001-001"], disliked_course_ids=["GEN001-001"])
    with pytest.raises(ValidationError, match="earliest_start_time"):
        HardConstraints(earliest_start_time="18:00", latest_end_time="10:00")
    with pytest.raises(ValidationError, match="earliest_start_time"):
        HardConstraints(earliest_start_time="10:00", latest_end_time="10:00")
    with pytest.raises(ValidationError, match="preferred_earliest_start_time"):
        SoftPreferences(
            preferred_earliest_start_time="10:00",
            preferred_latest_end_time="10:00",
        )
    with pytest.raises(ValidationError, match="preferred_earliest_start_time"):
        SoftPreferences(
            preferred_earliest_start_time="18:00",
            preferred_latest_end_time="10:00",
        )


def test_hard_free_days_are_mutated_idempotently_and_remove_soft_duplicates() -> None:
    clock = MutableClock(_now())
    service = _service(clock=clock)
    created = service.create_session()
    first = service.add_preferred_free_day(created.session_id, "MON")
    clock.advance(timedelta(minutes=1))

    hard = service.add_required_free_day(created.session_id, "MON")
    duplicate = service.add_required_free_day(created.session_id, Day.MON)
    removed = service.remove_required_free_day(created.session_id, "MON")
    missing = service.remove_required_free_day(created.session_id, "MON")
    replaced = service.replace_required_free_days(created.session_id, ["FRI", "FRI"])

    assert first.soft_preferences.preferred_free_days == [Day.MON]
    assert hard.hard_constraints.required_free_days == [Day.MON]
    assert hard.soft_preferences.preferred_free_days == []
    assert duplicate.updated_at == hard.updated_at
    assert removed.hard_constraints.required_free_days == []
    assert missing.updated_at == removed.updated_at
    assert replaced.hard_constraints.required_free_days == [Day.FRI]


def test_hard_time_limits_validate_ranges_and_update_only_on_change() -> None:
    clock = MutableClock(_now())
    service = _service(clock=clock)
    created = service.create_session()
    first = service.set_earliest_start_time(created.session_id, "10:00")
    same = service.set_earliest_start_time(created.session_id, "10:00")
    latest = service.set_latest_end_time(created.session_id, "18:00")

    assert first.hard_constraints.earliest_start_time == "10:00"
    assert same.updated_at == first.updated_at
    assert latest.hard_constraints.latest_end_time == "18:00"

    with pytest.raises(InvalidSessionStateValueError):
        service.set_latest_end_time(created.session_id, "09:00")

    unchanged = service.get_session(created.session_id)
    cleared = service.clear_earliest_start_time(created.session_id)
    cleared_again = service.clear_earliest_start_time(created.session_id)

    assert unchanged.hard_constraints.latest_end_time == "18:00"
    assert cleared.hard_constraints.earliest_start_time is None
    assert cleared_again.updated_at == cleared.updated_at


def test_hard_course_conflicts_use_new_request_and_clear_related_soft_items() -> None:
    service = _service()
    created = service.create_session()
    service.add_preferred_course(created.session_id, "GEN001-001")
    excluded = service.add_excluded_course(created.session_id, "GEN001-001")
    required = service.add_required_course(created.session_id, " GEN001-001 ")
    removed = service.remove_required_course(created.session_id, "GEN001-001")
    replaced = service.replace_excluded_courses(created.session_id, ["GEN002-001", "GEN002-001"])

    assert excluded.hard_constraints.excluded_course_ids == ["GEN001-001"]
    assert excluded.soft_preferences.preferred_course_ids == []
    assert required.hard_constraints.required_course_ids == ["GEN001-001"]
    assert required.hard_constraints.excluded_course_ids == []
    assert removed.hard_constraints.required_course_ids == []
    assert replaced.hard_constraints.excluded_course_ids == ["GEN002-001"]

    with pytest.raises(InvalidSessionStateValueError):
        service.add_required_course(created.session_id, " ")


def test_soft_free_days_skip_existing_hard_days_and_replace_without_duplicates() -> None:
    service = _service()
    created = service.create_session()
    service.add_required_free_day(created.session_id, "MON")

    skipped = service.add_preferred_free_day(created.session_id, "MON")
    replaced = service.replace_preferred_free_days(created.session_id, ["MON", "TUE", "TUE"])
    removed = service.remove_preferred_free_day(created.session_id, "TUE")

    assert skipped.soft_preferences.preferred_free_days == []
    assert replaced.soft_preferences.preferred_free_days == [Day.TUE]
    assert removed.soft_preferences.preferred_free_days == []


def test_soft_time_preferences_validate_against_hard_time_limits() -> None:
    service = _service()
    created = service.create_session()
    service.set_earliest_start_time(created.session_id, "10:00")
    service.set_latest_end_time(created.session_id, "18:00")

    with pytest.raises(InvalidSessionStateValueError):
        service.set_preferred_earliest_start_time(created.session_id, "09:00")
    with pytest.raises(InvalidSessionStateValueError):
        service.set_preferred_latest_end_time(created.session_id, "19:00")

    earliest = service.set_preferred_earliest_start_time(created.session_id, "11:00")
    latest = service.set_preferred_latest_end_time(created.session_id, "17:00")
    cleared = service.clear_preferred_latest_end_time(created.session_id)

    assert earliest.soft_preferences.preferred_earliest_start_time == "11:00"
    assert latest.soft_preferences.preferred_latest_end_time == "17:00"
    assert cleared.soft_preferences.preferred_latest_end_time is None


def test_soft_course_conflicts_are_resolved_and_hard_conflicts_are_rejected() -> None:
    service = _service()
    created = service.create_session()
    preferred = service.add_preferred_course(created.session_id, "GEN001-001")
    disliked = service.add_disliked_course(created.session_id, "GEN001-001")
    removed = service.remove_disliked_course(created.session_id, "GEN001-001")

    assert preferred.soft_preferences.preferred_course_ids == ["GEN001-001"]
    assert disliked.soft_preferences.preferred_course_ids == []
    assert disliked.soft_preferences.disliked_course_ids == ["GEN001-001"]
    assert removed.soft_preferences.disliked_course_ids == []

    service.add_required_course(created.session_id, "GEN002-001")
    service.add_excluded_course(created.session_id, "GEN003-001")
    with pytest.raises(InvalidSessionStateValueError):
        service.add_disliked_course(created.session_id, "GEN002-001")
    with pytest.raises(InvalidSessionStateValueError):
        service.add_preferred_course(created.session_id, "GEN003-001")


def test_compact_schedule_and_clear_methods_preserve_session_metadata() -> None:
    clock = MutableClock(_now())
    service = _service(clock=clock)
    created = service.create_session()
    service.set_department(created.session_id, "컴퓨터공학부")
    service.register_major_catalog(created.session_id, "major-catalog")
    service.register_elective_catalog(created.session_id, "elective-catalog")
    service.add_selected_major_course(created.session_id, "MAJ001-001")
    hard = service.add_required_course(created.session_id, "GEN001-001")
    compact = service.set_compact_schedule_preference(created.session_id, True)
    cleared_compact = service.clear_compact_schedule_preference(created.session_id)
    cleared_soft = service.clear_soft_preferences(created.session_id)
    cleared_hard = service.clear_hard_constraints(created.session_id)
    cleared_all = service.clear_all_preferences(created.session_id)
    clock.advance(timedelta(minutes=1))
    unchanged = service.clear_all_preferences(created.session_id)

    assert hard.hard_constraints.required_course_ids == ["GEN001-001"]
    assert compact.soft_preferences.compact_schedule is True
    assert cleared_compact.soft_preferences.compact_schedule is None
    assert cleared_soft.hard_constraints.required_course_ids == ["GEN001-001"]
    assert cleared_hard.hard_constraints == HardConstraints()
    assert cleared_all.department == "컴퓨터공학부"
    assert cleared_all.major_catalog_id == "major-catalog"
    assert cleared_all.elective_catalog_id == "elective-catalog"
    assert cleared_all.selected_major_course_ids == ["MAJ001-001"]
    assert unchanged.updated_at == cleared_all.updated_at


def test_changed_constraints_are_persisted_and_returned_as_copies() -> None:
    repository = InMemorySessionRepository()
    service = _service(repository=repository)
    created = service.create_session()

    updated = service.add_required_course(created.session_id, "GEN001-001")
    updated.hard_constraints.required_course_ids.append("BYPASS")
    stored = service.get_session(created.session_id)

    assert stored.hard_constraints.required_course_ids == ["GEN001-001"]


def test_repository_copies_include_nested_preference_state() -> None:
    repository = InMemorySessionRepository()
    state = _state("session-1")
    state.hard_constraints.required_free_days.append(Day.MON)
    state.soft_preferences.preferred_course_ids.append("GEN001-001")

    created = repository.create(state, now=_now())
    found = repository.get(state.session_id, now=_now())
    assert found is not None

    created.hard_constraints.required_free_days.append(Day.TUE)
    found.soft_preferences.preferred_course_ids.append("GEN002-001")

    stored = repository.get(state.session_id, now=_now())
    assert stored is not None
    assert stored.hard_constraints.required_free_days == [Day.MON]
    assert stored.soft_preferences.preferred_course_ids == ["GEN001-001"]


def test_condition_updates_fail_for_missing_or_expired_sessions() -> None:
    clock = MutableClock(_now())
    service = SessionService(
        InMemorySessionRepository(),
        session_ttl=timedelta(minutes=5),
        now_provider=clock,
        session_id_provider=lambda: "session-1",
    )
    created = service.create_session()
    clock.advance(timedelta(minutes=5))

    with pytest.raises(SessionNotAvailableError):
        service.add_required_free_day(created.session_id, "MON")
    with pytest.raises(SessionNotAvailableError):
        service.add_required_free_day("missing", "MON")
