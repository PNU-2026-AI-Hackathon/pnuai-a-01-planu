"""SessionRepository adapter over the legacy application SessionStore."""

from __future__ import annotations

from datetime import datetime

from ..models import PlanuSessionState
from ..services.session_store import SessionData, SessionNotFoundError as StoreSessionNotFoundError, SessionStore
from .exceptions import (
    SessionAlreadyExistsError,
    SessionNotFoundError,
    SessionVersionConflictError,
)


class SessionStoreRepository:
    """Expose ``SessionStore`` through the new ``SessionRepository`` contract.

    This is a compatibility layer, not a second store. Existing API services and
    the session-state agent read and write the same ``SessionData`` instances.
    """

    def __init__(self, store: SessionStore) -> None:
        self._store = store

    def create(self, state: PlanuSessionState, *, now: datetime) -> PlanuSessionState:
        try:
            data = self._store.create(
                department=state.department or "미정",
                session_id=state.session_id,
            )
        except ValueError as exc:
            raise SessionAlreadyExistsError(state.session_id) from exc
        last_accessed_at = max(data.created_at, state.last_accessed_at)
        data = self._store.update(
            state.session_id,
            department=state.department,
            major_catalog_id=state.major_catalog_id,
            elective_catalog_id=state.elective_catalog_id,
            selected_major_course_ids=state.selected_major_course_ids,
            hard_constraints=state.hard_constraints,
            soft_preferences=state.soft_preferences,
            selected_timetable=state.selected_timetable,
            selected_timetable_status=state.selected_timetable_status,
            clear_selected_timetable=state.selected_timetable is None,
            generation_preferences_confirmed_at=state.generation_preferences_confirmed_at,
            generation_preferences_confirmed_version=state.generation_preferences_confirmed_version,
            clear_generation_preferences_confirmation=state.generation_preferences_confirmed_at is None,
            last_accessed_at=last_accessed_at,
            expires_at=max(state.expires_at, last_accessed_at),
        )
        return _to_state(data)

    def get(self, session_id: str, *, now: datetime) -> PlanuSessionState | None:
        try:
            return _to_state(self._store.get(session_id, touch=False))
        except StoreSessionNotFoundError:
            return None

    def save(self, state: PlanuSessionState, *, now: datetime) -> PlanuSessionState:
        try:
            current = self._store.get(state.session_id, touch=False)
        except StoreSessionNotFoundError as exc:
            raise SessionNotFoundError(state.session_id) from exc
        if current.version != state.version:
            raise SessionVersionConflictError(
                state.session_id,
                expected=state.version,
                actual=current.version,
            )
        try:
            data = self._store.update(
                state.session_id,
                department=state.department,
                major_catalog_id=state.major_catalog_id,
                elective_catalog_id=state.elective_catalog_id,
                selected_major_course_ids=state.selected_major_course_ids,
                hard_constraints=state.hard_constraints,
                soft_preferences=state.soft_preferences,
                selected_timetable=state.selected_timetable,
                selected_timetable_status=state.selected_timetable_status,
                clear_selected_timetable=state.selected_timetable is None,
                generation_preferences_confirmed_at=state.generation_preferences_confirmed_at,
                generation_preferences_confirmed_version=state.generation_preferences_confirmed_version,
                clear_generation_preferences_confirmation=state.generation_preferences_confirmed_at is None,
                last_accessed_at=state.last_accessed_at,
                expires_at=state.expires_at,
            )
        except StoreSessionNotFoundError as exc:
            raise SessionNotFoundError(state.session_id) from exc
        return _to_state(data)

    def delete(self, session_id: str) -> None:
        self._store.delete(session_id)

    def touch(
        self,
        session_id: str,
        *,
        now: datetime,
        last_accessed_at: datetime,
        expires_at: datetime,
    ) -> PlanuSessionState:
        try:
            data = self._store.update(
                session_id,
                last_accessed_at=last_accessed_at,
                expires_at=expires_at,
            )
        except StoreSessionNotFoundError as exc:
            raise SessionNotFoundError(session_id) from exc
        return _to_state(data)

    def delete_expired(self, *, now: datetime) -> int:
        return self._store.cleanup_expired(now=now)


def _to_state(data: SessionData) -> PlanuSessionState:
    return PlanuSessionState(
        session_id=data.session_id,
        department=data.department,
        major_catalog_id=data.major_catalog_id,
        elective_catalog_id=data.elective_catalog_id,
        selected_major_course_ids=list(data.selected_major_course_ids),
        hard_constraints=data.hard_constraints,
        soft_preferences=data.soft_preferences,
        selected_timetable=data.selected_timetable,
        selected_timetable_status=data.selected_timetable_status,
        generation_preferences_confirmed_at=data.generation_preferences_confirmed_at,
        generation_preferences_confirmed_version=data.generation_preferences_confirmed_version,
        generation_revision=data.generation_revision,
        created_at=data.created_at,
        updated_at=data.updated_at,
        last_accessed_at=data.last_accessed_at,
        expires_at=data.expires_at or data.updated_at,
        version=data.version,
    )
