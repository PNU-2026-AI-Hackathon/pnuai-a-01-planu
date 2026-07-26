"""Protocol for PlaNU session state persistence."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from ..models.planu_session_state import PlanuSessionState


class SessionRepository(Protocol):
    """Storage boundary for agent session state.

    Repository implementations persist complete session state and compare
    externally supplied timestamps with ``expires_at``. They should not decide
    session lifetime, mutate domain preferences, parse user text, or call
    timetable generation tools.
    """

    def create(self, state: PlanuSessionState) -> PlanuSessionState:
        """Create a new session state.

        Raises:
            SessionAlreadyExistsError: If ``state.session_id`` already exists.
        """

    def get(self, session_id: str, *, now: datetime) -> PlanuSessionState | None:
        """Return the state for a live session, or ``None`` if missing or expired."""

    def save(self, state: PlanuSessionState) -> PlanuSessionState:
        """Persist a replacement state for an existing session.

        Raises:
            SessionNotFoundError: If ``state.session_id`` does not exist.
        """

    def delete(self, session_id: str) -> None:
        """Delete a session idempotently."""

    def touch(
        self,
        session_id: str,
        *,
        last_accessed_at: datetime,
        expires_at: datetime,
    ) -> PlanuSessionState:
        """Update externally calculated access and expiration timestamps.

        Raises:
            SessionNotFoundError: If ``session_id`` does not exist.
        """

    def delete_expired(self, *, now: datetime) -> int:
        """Delete sessions whose ``expires_at`` is not later than ``now``."""
