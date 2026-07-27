"""In-memory implementation of the PlaNU session repository contract."""

from __future__ import annotations

from datetime import datetime
from threading import RLock

from ..models.planu_session_state import PlanuSessionState
from .exceptions import SessionAlreadyExistsError, SessionNotFoundError


class InMemorySessionRepository:
    """Process-local repository for complete PlaNU session state objects.

    State is stored only in process memory, so sessions are lost on server
    restart and are not shared across processes or workers. This implementation
    is intended for development and MVP single-process deployments; production
    can replace it with a SQLite or Redis repository behind the same contract.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, PlanuSessionState] = {}
        self._lock = RLock()

    def create(self, state: PlanuSessionState, *, now: datetime) -> PlanuSessionState:
        """Create a new live session state."""

        self._validate_aware_datetime(now, field_name="now")
        with self._lock:
            existing = self._sessions.get(state.session_id)
            if existing is not None:
                if self._is_expired(existing, now):
                    del self._sessions[state.session_id]
                else:
                    raise SessionAlreadyExistsError(state.session_id)
            self._validate_not_already_expired(state, now)

            stored = self._copy(state)
            self._sessions[state.session_id] = stored
            return self._copy(stored)

    def get(self, session_id: str, *, now: datetime) -> PlanuSessionState | None:
        """Return a live session copy, or ``None`` when missing or expired."""

        self._validate_aware_datetime(now, field_name="now")
        with self._lock:
            state = self._sessions.get(session_id)
            if state is None:
                return None
            if self._is_expired(state, now):
                del self._sessions[session_id]
                return None
            return self._copy(state)

    def save(self, state: PlanuSessionState, *, now: datetime) -> PlanuSessionState:
        """Replace an existing live session state."""

        self._validate_aware_datetime(now, field_name="now")
        with self._lock:
            existing = self._sessions.get(state.session_id)
            if existing is None:
                raise SessionNotFoundError(state.session_id)
            if self._is_expired(existing, now):
                del self._sessions[state.session_id]
                raise SessionNotFoundError(state.session_id)
            self._validate_not_already_expired(state, now)

            stored = self._copy(state)
            self._sessions[state.session_id] = stored
            return self._copy(stored)

    def delete(self, session_id: str) -> None:
        """Delete a session idempotently."""

        with self._lock:
            self._sessions.pop(session_id, None)

    def touch(
        self,
        session_id: str,
        *,
        now: datetime,
        last_accessed_at: datetime,
        expires_at: datetime,
    ) -> PlanuSessionState:
        """Persist caller-supplied access and expiration timestamps.

        ``updated_at`` is intentionally unchanged because simple access and TTL
        extension are not planning-data updates.
        """

        self._validate_aware_datetime(now, field_name="now")
        self._validate_aware_datetime(
            last_accessed_at,
            field_name="last_accessed_at",
        )
        self._validate_aware_datetime(expires_at, field_name="expires_at")
        with self._lock:
            state = self._sessions.get(session_id)
            if state is None:
                raise SessionNotFoundError(session_id)
            if self._is_expired(state, now):
                del self._sessions[session_id]
                raise SessionNotFoundError(session_id)

            touched = PlanuSessionState.model_validate(
                {
                    **state.model_dump(),
                    "last_accessed_at": last_accessed_at,
                    "expires_at": expires_at,
                }
            )
            self._sessions[session_id] = touched
            return self._copy(touched)

    def delete_expired(self, *, now: datetime) -> int:
        """Delete expired sessions and return the number deleted."""

        self._validate_aware_datetime(now, field_name="now")
        with self._lock:
            expired_session_ids = [
                session_id
                for session_id, state in self._sessions.items()
                if self._is_expired(state, now)
            ]
            for session_id in expired_session_ids:
                del self._sessions[session_id]
            return len(expired_session_ids)

    @staticmethod
    def _is_expired(state: PlanuSessionState, now: datetime) -> bool:
        return state.expires_at <= now

    @staticmethod
    def _validate_aware_datetime(value: datetime, *, field_name: str) -> None:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(f"{field_name} must include timezone information")

    @classmethod
    def _validate_not_already_expired(
        cls,
        state: PlanuSessionState,
        now: datetime,
    ) -> None:
        if cls._is_expired(state, now):
            raise ValueError("session state must not already be expired")

    @staticmethod
    def _copy(state: PlanuSessionState) -> PlanuSessionState:
        return state.model_copy(deep=True)
