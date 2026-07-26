"""Common exceptions raised by session repository implementations."""

from __future__ import annotations


class SessionRepositoryError(RuntimeError):
    """Base class for expected session repository failures."""

    def __init__(self, session_id: str, message: str | None = None) -> None:
        self.session_id = session_id
        super().__init__(message or f"session repository error: {session_id}")


class SessionAlreadyExistsError(SessionRepositoryError):
    """Raised when creating a session with an existing session id."""

    def __init__(self, session_id: str) -> None:
        super().__init__(session_id, f"session already exists: {session_id}")


class SessionNotFoundError(SessionRepositoryError):
    """Raised when updating a session id that does not exist."""

    def __init__(self, session_id: str) -> None:
        super().__init__(session_id, f"session not found: {session_id}")
