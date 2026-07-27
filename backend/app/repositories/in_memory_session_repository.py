"""In-memory implementation of the PlaNU session repository contract."""

from __future__ import annotations

from datetime import datetime

from ..models.planu_session_state import PlanuSessionState
from .exceptions import SessionAlreadyExistsError, SessionNotFoundError


class InMemorySessionRepository:
    """Process-local repository for complete PlaNU session state objects."""

    def __init__(self) -> None:
        self._sessions: dict[str, PlanuSessionState] = {}

    def create(self, state: PlanuSessionState, *, now: datetime) -> PlanuSessionState:
        """Create a new live session state."""

        existing = self._sessions.get(state.session_id)
        if existing is not None:
            if self._is_expired(existing, now):
                del self._sessions[state.session_id]
            else:
                raise SessionAlreadyExistsError(state.session_id)

        stored = self._copy(state)
        self._sessions[state.session_id] = stored
        return self._copy(stored)

    def get(self, session_id: str, *, now: datetime) -> PlanuSessionState | None:
        """Return a live session copy, or ``None`` when missing or expired."""

        state = self._sessions.get(session_id)
        if state is None:
            return None
        if self._is_expired(state, now):
            del self._sessions[session_id]
            return None
        return self._copy(state)

    def save(self, state: PlanuSessionState, *, now: datetime) -> PlanuSessionState:
        """Replace an existing live session state."""

        existing = self._sessions.get(state.session_id)
        if existing is None:
            raise SessionNotFoundError(state.session_id)
        if self._is_expired(existing, now):
            del self._sessions[state.session_id]
            raise SessionNotFoundError(state.session_id)

        stored = self._copy(state)
        self._sessions[state.session_id] = stored
        return self._copy(stored)

    def delete(self, session_id: str) -> None:
        """Delete a session idempotently."""

        self._sessions.pop(session_id, None)

    def touch(
        self,
        session_id: str,
        *,
        now: datetime,
        last_accessed_at: datetime,
        expires_at: datetime,
    ) -> PlanuSessionState:
        """Persist caller-supplied access and expiration timestamps."""

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
    def _copy(state: PlanuSessionState) -> PlanuSessionState:
        return state.model_copy(deep=True)
