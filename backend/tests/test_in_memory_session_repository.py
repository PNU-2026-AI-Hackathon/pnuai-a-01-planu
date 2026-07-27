"""Tests for the in-memory PlaNU session repository."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backend.app.models import PlanuSessionState
from backend.app.repositories import (
    InMemorySessionRepository,
    SessionAlreadyExistsError,
    SessionNotFoundError,
)


def _now() -> datetime:
    return datetime(2026, 7, 26, 12, 0, tzinfo=timezone.utc)


def _state(
    session_id: str = "session-1",
    *,
    now: datetime | None = None,
    selected_major_course_ids: list[str] | None = None,
    expires_delta: timedelta = timedelta(minutes=30),
) -> PlanuSessionState:
    current = now or _now()
    return PlanuSessionState(
        session_id=session_id,
        department="컴퓨터공학부",
        major_catalog_id="major-catalog-1",
        elective_catalog_id="elective-catalog-1",
        selected_major_course_ids=selected_major_course_ids or ["MAJ001-001"],
        created_at=current,
        updated_at=current,
        last_accessed_at=current,
        expires_at=current + expires_delta,
    )


def test_create_then_get_returns_session() -> None:
    repository = InMemorySessionRepository()
    state = _state()

    created = repository.create(state, now=_now())
    found = repository.get(state.session_id, now=_now())

    assert created == state
    assert found == state


def test_create_duplicate_live_session_raises() -> None:
    repository = InMemorySessionRepository()
    state = _state()
    repository.create(state, now=_now())

    with pytest.raises(SessionAlreadyExistsError):
        repository.create(state, now=_now())


def test_create_can_replace_expired_session_with_same_id() -> None:
    repository = InMemorySessionRepository()
    current = _now()
    expired = _state(expires_delta=timedelta(minutes=5))
    session_id = expired.session_id
    replacement = _state(
        session_id,
        now=current + timedelta(minutes=10),
        expires_delta=timedelta(minutes=30),
    )
    repository.create(expired, now=current)

    created = repository.create(replacement, now=current + timedelta(minutes=10))

    assert created == replacement
    assert repository.get(session_id, now=current + timedelta(minutes=10)) == replacement


def test_get_missing_session_returns_none() -> None:
    repository = InMemorySessionRepository()

    assert repository.get("missing", now=_now()) is None


def test_save_existing_session_replaces_state() -> None:
    repository = InMemorySessionRepository()
    state = repository.create(_state(), now=_now())
    updated = state.model_copy(update={"department": "전자공학과"}, deep=True)

    saved = repository.save(updated, now=_now())

    assert saved.department == "전자공학과"
    assert repository.get(state.session_id, now=_now()) == updated


def test_save_missing_session_raises() -> None:
    repository = InMemorySessionRepository()

    with pytest.raises(SessionNotFoundError):
        repository.save(_state(), now=_now())


def test_save_expired_stored_session_raises_and_removes_it() -> None:
    repository = InMemorySessionRepository()
    state = _state(expires_delta=timedelta(minutes=5))
    repository.create(state, now=_now())

    with pytest.raises(SessionNotFoundError):
        repository.save(state, now=_now() + timedelta(minutes=5))

    assert repository.get(state.session_id, now=_now()) is None


def test_delete_removes_session() -> None:
    repository = InMemorySessionRepository()
    state = _state()
    repository.create(state, now=_now())

    repository.delete(state.session_id)

    assert repository.get(state.session_id, now=_now()) is None


def test_delete_missing_session_is_idempotent() -> None:
    repository = InMemorySessionRepository()

    repository.delete("missing")
    repository.delete("missing")


def test_touch_updates_only_access_and_expiration_times() -> None:
    repository = InMemorySessionRepository()
    state = _state()
    repository.create(state, now=_now())
    last_accessed_at = _now() + timedelta(minutes=5)
    expires_at = _now() + timedelta(minutes=35)

    touched = repository.touch(
        state.session_id,
        now=_now(),
        last_accessed_at=last_accessed_at,
        expires_at=expires_at,
    )

    assert touched.last_accessed_at == last_accessed_at
    assert touched.expires_at == expires_at
    assert touched.updated_at == state.updated_at
    assert touched.created_at == state.created_at
    assert touched.department == state.department
    assert touched.selected_major_course_ids == state.selected_major_course_ids


def test_touch_missing_session_raises() -> None:
    repository = InMemorySessionRepository()

    with pytest.raises(SessionNotFoundError):
        repository.touch(
            "missing",
            now=_now(),
            last_accessed_at=_now() + timedelta(minutes=1),
            expires_at=_now() + timedelta(minutes=31),
        )


def test_touch_expired_session_raises_and_removes_it() -> None:
    repository = InMemorySessionRepository()
    state = _state(expires_delta=timedelta(minutes=5))
    repository.create(state, now=_now())

    with pytest.raises(SessionNotFoundError):
        repository.touch(
            state.session_id,
            now=_now() + timedelta(minutes=5),
            last_accessed_at=_now() + timedelta(minutes=6),
            expires_at=_now() + timedelta(minutes=36),
        )

    assert repository.get(state.session_id, now=_now()) is None


def test_get_expired_session_returns_none_and_removes_it() -> None:
    repository = InMemorySessionRepository()
    state = _state(expires_delta=timedelta(minutes=10))
    repository.create(state, now=_now())
    expired_at = _now() + timedelta(minutes=10)

    assert repository.get(state.session_id, now=expired_at) is None

    replacement = _state(expires_delta=timedelta(minutes=20))
    repository.create(replacement, now=expired_at)
    assert repository.get(state.session_id, now=expired_at) == replacement


def test_delete_expired_removes_only_expired_sessions_and_returns_count() -> None:
    repository = InMemorySessionRepository()
    current = _now()
    expired = _state("expired", expires_delta=timedelta(minutes=5))
    equal_to_now = _state("equal-to-now", expires_delta=timedelta(minutes=10))
    live = _state("live", expires_delta=timedelta(minutes=20))
    repository.create(expired, now=current)
    repository.create(equal_to_now, now=current)
    repository.create(live, now=current)

    deleted_count = repository.delete_expired(now=current + timedelta(minutes=10))

    assert deleted_count == 2
    assert repository.get("expired", now=current + timedelta(minutes=10)) is None
    assert repository.get("equal-to-now", now=current + timedelta(minutes=10)) is None
    assert repository.get("live", now=current + timedelta(minutes=10)) == live


def test_create_stores_deep_copy_of_original_state() -> None:
    repository = InMemorySessionRepository()
    state = _state(selected_major_course_ids=["MAJ001-001"])

    repository.create(state, now=_now())
    state.selected_major_course_ids.append("MAJ002-001")

    stored = repository.get(state.session_id, now=_now())
    assert stored is not None
    assert stored.selected_major_course_ids == ["MAJ001-001"]


def test_get_returns_deep_copy_until_saved() -> None:
    repository = InMemorySessionRepository()
    state = _state(selected_major_course_ids=["MAJ001-001"])
    repository.create(state, now=_now())

    found = repository.get(state.session_id, now=_now())
    assert found is not None
    found.selected_major_course_ids.append("MAJ002-001")

    stored_again = repository.get(state.session_id, now=_now())
    assert stored_again is not None
    assert stored_again.selected_major_course_ids == ["MAJ001-001"]


def test_session_copies_do_not_share_nested_lists() -> None:
    repository = InMemorySessionRepository()
    state = _state(selected_major_course_ids=["MAJ001-001"])

    created = repository.create(state, now=_now())
    found = repository.get(state.session_id, now=_now())
    assert found is not None

    created.selected_major_course_ids.append("MAJ002-001")
    found.selected_major_course_ids.append("MAJ003-001")

    stored = repository.get(state.session_id, now=_now())
    assert stored is not None
    assert stored.selected_major_course_ids == ["MAJ001-001"]
