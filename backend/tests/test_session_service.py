"""Tests for the PlaNU session service boundary."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

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


def _service(
    *,
    clock: MutableClock | None = None,
    session_ttl: timedelta = timedelta(minutes=30),
) -> SessionService:
    return SessionService(
        InMemorySessionRepository(),
        session_ttl=session_ttl,
        now_provider=clock or MutableClock(_now()),
        session_id_provider=lambda: "session-1",
    )


def test_create_session_creates_and_stores_state_with_ttl_times() -> None:
    clock = MutableClock(_now())
    service = _service(clock=clock)

    created = service.create_session()
    found = service.get_session(created.session_id)

    assert found == created
    assert created.session_id == "session-1"
    assert created.created_at == _now()
    assert created.updated_at == _now()
    assert created.last_accessed_at == _now()
    assert created.expires_at == _now() + timedelta(minutes=30)


def test_create_session_uses_configured_session_ttl() -> None:
    service = _service(session_ttl=timedelta(minutes=5))

    created = service.create_session()

    assert created.expires_at == _now() + timedelta(minutes=5)


def test_get_session_missing_raises_service_error() -> None:
    service = _service()

    with pytest.raises(SessionNotAvailableError) as exc_info:
        service.get_session("missing")

    assert exc_info.value.session_id == "missing"


def test_get_session_expired_raises_service_error() -> None:
    clock = MutableClock(_now())
    service = _service(clock=clock, session_ttl=timedelta(minutes=5))
    created = service.create_session()
    clock.advance(timedelta(minutes=5))

    with pytest.raises(SessionNotAvailableError):
        service.get_session(created.session_id)


def test_refresh_session_updates_access_and_expiration_only() -> None:
    clock = MutableClock(_now())
    service = _service(clock=clock)
    created = service.create_session()
    service.set_department(created.session_id, "컴퓨터공학부")
    before_refresh = service.get_session(created.session_id)
    clock.advance(timedelta(minutes=3))

    refreshed = service.refresh_session(created.session_id)

    assert refreshed.last_accessed_at == clock.current
    assert refreshed.expires_at == clock.current + timedelta(minutes=30)
    assert refreshed.updated_at == before_refresh.updated_at
    assert refreshed.created_at == before_refresh.created_at
    assert refreshed.department == "컴퓨터공학부"
    assert refreshed.selected_major_course_ids == []


def test_refresh_session_missing_raises_service_error() -> None:
    service = _service()

    with pytest.raises(SessionNotAvailableError):
        service.refresh_session("missing")


def test_delete_session_is_idempotent_and_removes_session() -> None:
    service = _service()
    created = service.create_session()

    service.delete_session(created.session_id)
    service.delete_session(created.session_id)

    with pytest.raises(SessionNotAvailableError):
        service.get_session(created.session_id)


def test_set_department_trims_value_and_updates_timestamp() -> None:
    clock = MutableClock(_now())
    service = _service(clock=clock)
    created = service.create_session()
    clock.advance(timedelta(minutes=1))

    updated = service.set_department(created.session_id, "  컴퓨터공학부  ")

    assert updated.department == "컴퓨터공학부"
    assert updated.updated_at == clock.current
    assert updated.last_accessed_at == clock.current
    assert updated.expires_at == clock.current + timedelta(minutes=30)


def test_set_department_rejects_empty_value() -> None:
    service = _service()
    created = service.create_session()

    with pytest.raises(InvalidSessionStateValueError) as exc_info:
        service.set_department(created.session_id, " ")

    assert exc_info.value.field_name == "department"


def test_register_major_catalog_can_set_and_replace_catalog_id() -> None:
    service = _service()
    created = service.create_session()

    first = service.register_major_catalog(created.session_id, " major-1 ")
    second = service.register_major_catalog(created.session_id, "major-2")

    assert first.major_catalog_id == "major-1"
    assert second.major_catalog_id == "major-2"


def test_register_elective_catalog_can_set_and_replace_catalog_id() -> None:
    service = _service()
    created = service.create_session()

    first = service.register_elective_catalog(created.session_id, " elective-1 ")
    second = service.register_elective_catalog(created.session_id, "elective-2")

    assert first.elective_catalog_id == "elective-1"
    assert second.elective_catalog_id == "elective-2"


@pytest.mark.parametrize(
    ("method_name", "field_name"),
    [
        ("register_major_catalog", "major_catalog_id"),
        ("register_elective_catalog", "elective_catalog_id"),
    ],
)
def test_register_catalog_rejects_empty_id(
    method_name: str,
    field_name: str,
) -> None:
    service = _service()
    created = service.create_session()
    method = getattr(service, method_name)

    with pytest.raises(InvalidSessionStateValueError) as exc_info:
        method(created.session_id, " ")

    assert exc_info.value.field_name == field_name


def test_add_selected_major_course_adds_course_and_avoids_duplicates() -> None:
    service = _service()
    created = service.create_session()

    first = service.add_selected_major_course(created.session_id, " MAJ001-001 ")
    second = service.add_selected_major_course(created.session_id, "MAJ001-001")

    assert first.selected_major_course_ids == ["MAJ001-001"]
    assert second.selected_major_course_ids == ["MAJ001-001"]


def test_add_selected_major_course_rejects_empty_id() -> None:
    service = _service()
    created = service.create_session()

    with pytest.raises(InvalidSessionStateValueError):
        service.add_selected_major_course(created.session_id, " ")


def test_remove_selected_major_course_removes_existing_and_ignores_missing() -> None:
    service = _service()
    created = service.create_session()
    service.replace_selected_major_courses(
        created.session_id,
        ["MAJ001-001", "MAJ002-001"],
    )

    removed = service.remove_selected_major_course(created.session_id, "MAJ001-001")
    unchanged = service.remove_selected_major_course(created.session_id, "missing")

    assert removed.selected_major_course_ids == ["MAJ002-001"]
    assert unchanged.selected_major_course_ids == ["MAJ002-001"]


def test_replace_selected_major_courses_deduplicates_in_first_seen_order() -> None:
    service = _service()
    created = service.create_session()

    replaced = service.replace_selected_major_courses(
        created.session_id,
        [" MAJ002-001 ", "MAJ001-001", "MAJ002-001"],
    )

    assert replaced.selected_major_course_ids == ["MAJ002-001", "MAJ001-001"]


def test_replace_selected_major_courses_rejects_empty_course_id() -> None:
    service = _service()
    created = service.create_session()

    with pytest.raises(InvalidSessionStateValueError) as exc_info:
        service.replace_selected_major_courses(created.session_id, ["MAJ001-001", " "])

    assert exc_info.value.field_name == "selected_major_course_ids"


def test_replace_selected_major_courses_accepts_empty_list() -> None:
    service = _service()
    created = service.create_session()
    service.add_selected_major_course(created.session_id, "MAJ001-001")

    replaced = service.replace_selected_major_courses(created.session_id, [])

    assert replaced.selected_major_course_ids == []


def test_actual_state_changes_update_updated_at() -> None:
    clock = MutableClock(_now())
    service = _service(clock=clock)
    created = service.create_session()
    clock.advance(timedelta(minutes=1))

    updated = service.register_major_catalog(created.session_id, "major-1")

    assert updated.updated_at == clock.current
    assert updated.last_accessed_at == clock.current
    assert updated.expires_at == clock.current + timedelta(minutes=30)


def test_state_change_updates_access_time_and_extends_ttl() -> None:
    clock = MutableClock(_now())
    session_ttl = timedelta(minutes=30)
    service = _service(clock=clock, session_ttl=session_ttl)
    created = service.create_session()
    clock.advance(timedelta(minutes=10))

    updated = service.add_selected_major_course(created.session_id, "MAJ001-001")

    assert updated.updated_at == clock.current
    assert updated.last_accessed_at == clock.current
    assert updated.expires_at == clock.current + session_ttl


def test_state_change_just_before_expiration_keeps_session_alive() -> None:
    clock = MutableClock(_now())
    service = _service(clock=clock)
    created = service.create_session()
    clock.advance(timedelta(minutes=29))

    service.set_department(created.session_id, "컴퓨터공학부")
    clock.advance(timedelta(minutes=2))
    found = service.get_session(created.session_id)

    assert found.department == "컴퓨터공학부"
    assert found.expires_at == _now() + timedelta(minutes=59)


def test_duplicate_add_does_not_update_updated_at() -> None:
    clock = MutableClock(_now())
    service = _service(clock=clock)
    created = service.create_session()
    first = service.add_selected_major_course(created.session_id, "MAJ001-001")
    clock.advance(timedelta(minutes=1))

    second = service.add_selected_major_course(created.session_id, "MAJ001-001")

    assert second.selected_major_course_ids == ["MAJ001-001"]
    assert second.updated_at == first.updated_at
    assert second.last_accessed_at == clock.current
    assert second.expires_at == clock.current + timedelta(minutes=30)


def test_missing_remove_does_not_update_updated_at() -> None:
    clock = MutableClock(_now())
    service = _service(clock=clock)
    created = service.create_session()
    clock.advance(timedelta(minutes=1))

    unchanged = service.remove_selected_major_course(created.session_id, "missing")

    assert unchanged.updated_at == created.updated_at
    assert unchanged.last_accessed_at == clock.current
    assert unchanged.expires_at == clock.current + timedelta(minutes=30)


def test_replace_with_same_courses_does_not_update_updated_at() -> None:
    clock = MutableClock(_now())
    service = _service(clock=clock)
    created = service.create_session()
    first = service.replace_selected_major_courses(created.session_id, ["MAJ001-001"])
    clock.advance(timedelta(minutes=1))

    second = service.replace_selected_major_courses(created.session_id, [" MAJ001-001 "])

    assert second.updated_at == first.updated_at
    assert second.last_accessed_at == clock.current
    assert second.expires_at == clock.current + timedelta(minutes=30)


def test_setting_same_department_only_refreshes_session() -> None:
    clock = MutableClock(_now())
    service = _service(clock=clock)
    created = service.create_session()
    first = service.set_department(created.session_id, "컴퓨터공학부")
    clock.advance(timedelta(minutes=1))

    second = service.set_department(created.session_id, "  컴퓨터공학부  ")

    assert second.department == "컴퓨터공학부"
    assert second.updated_at == first.updated_at
    assert second.last_accessed_at == clock.current
    assert second.expires_at == clock.current + timedelta(minutes=30)


@pytest.mark.parametrize(
    ("register_method", "catalog_id_attr"),
    [
        ("register_major_catalog", "major_catalog_id"),
        ("register_elective_catalog", "elective_catalog_id"),
    ],
)
def test_setting_same_catalog_id_only_refreshes_session(
    register_method: str,
    catalog_id_attr: str,
) -> None:
    clock = MutableClock(_now())
    service = _service(clock=clock)
    created = service.create_session()
    register = getattr(service, register_method)
    first = register(created.session_id, "catalog-1")
    clock.advance(timedelta(minutes=1))

    second = register(created.session_id, " catalog-1 ")

    assert getattr(second, catalog_id_attr) == "catalog-1"
    assert second.updated_at == first.updated_at
    assert second.last_accessed_at == clock.current
    assert second.expires_at == clock.current + timedelta(minutes=30)


def test_state_change_uses_full_model_validation() -> None:
    service = _service()
    created = service.create_session()
    service._session_ttl = -timedelta(minutes=1)

    with pytest.raises(ValidationError, match="expires_at"):
        service.set_department(created.session_id, "컴퓨터공학부")


def test_get_session_does_not_change_time_fields() -> None:
    clock = MutableClock(_now())
    service = _service(clock=clock)
    created = service.create_session()
    clock.advance(timedelta(minutes=1))

    found = service.get_session(created.session_id)

    assert found.created_at == created.created_at
    assert found.updated_at == created.updated_at
    assert found.last_accessed_at == created.last_accessed_at
    assert found.expires_at == created.expires_at
