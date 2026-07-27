"""Protocol for PlaNU session state persistence."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from ..models.planu_session_state import PlanuSessionState


class SessionRepository(Protocol):
    """Storage boundary for agent session state.

    Repository implementations persist complete session state only. Expired
    sessions are treated as logically absent: reads return ``None``, writes
    fail with ``SessionNotFoundError``, and idempotent deletion remains
    successful. Implementations compare externally supplied timestamps with
    ``expires_at`` but must not calculate TTLs or decide session lifetime.

    Repositories should not mutate domain preferences, select courses, parse
    user text, call timetable generation tools, or create API responses.
    """

    def create(self, state: PlanuSessionState, *, now: datetime) -> PlanuSessionState:
        """Create a new session state.

        If only an expired session exists with the same id, implementations may
        discard it and create ``state``. If a live session with the same id
        exists, creation must fail. Expiration is evaluated as
        ``expires_at <= now`` using the caller's supplied timestamp.

        Raises:
            SessionAlreadyExistsError: If a live ``state.session_id`` exists.
        """

    def get(self, session_id: str, *, now: datetime) -> PlanuSessionState | None:
        """Return a live session, or ``None`` if missing or expired.

        Expiration is evaluated as ``expires_at <= now`` using the caller's
        supplied timestamp.
        """

    def save(self, state: PlanuSessionState, *, now: datetime) -> PlanuSessionState:
        """Persist a replacement state for an existing session.

        Expired sessions are treated as absent, so saving an expired stored
        session must fail rather than revive it. Expiration is evaluated as
        ``expires_at <= now`` using the caller's supplied timestamp.

        Raises:
            SessionNotFoundError: If ``state.session_id`` does not exist or is
                already expired.
        """

    def delete(self, session_id: str) -> None:
        """Delete a session idempotently.

        Missing sessions and already expired sessions do not raise errors.
        """

    def touch(
        self,
        session_id: str,
        *,
        now: datetime,
        last_accessed_at: datetime,
        expires_at: datetime,
    ) -> PlanuSessionState:
        """Update externally calculated access and expiration timestamps.

        Implementations must persist the supplied timestamps as-is after model
        validation. They must not add 30 minutes, calculate sliding TTLs, or
        otherwise decide the expiration policy. Expired sessions are treated as
        absent. Expiration is evaluated as ``expires_at <= now`` using the
        caller's supplied timestamp.

        Raises:
            SessionNotFoundError: If ``session_id`` does not exist or is already
                expired.
        """

    def delete_expired(self, *, now: datetime) -> int:
        """Delete sessions whose ``expires_at <= now`` and return the count."""
