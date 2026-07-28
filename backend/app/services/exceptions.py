"""Service-layer exceptions for PlaNU session state operations."""

from __future__ import annotations


class SessionServiceError(RuntimeError):
    """Base class for expected session service failures."""


class SessionNotAvailableError(SessionServiceError):
    """Raised when a session is missing, expired, or no longer writable."""

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        super().__init__(f"session is not available: {session_id}")


class InvalidSessionStateValueError(SessionServiceError):
    """Raised when a service input cannot be stored in session state."""

    def __init__(self, field_name: str, value: object) -> None:
        self.field_name = field_name
        self.value = value
        super().__init__(f"invalid session state value for {field_name}: {value!r}")
