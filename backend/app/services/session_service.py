"""Service boundary for future PlaNU agent session state tools."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from ..models import PlanuSessionState
from ..repositories import (
    SessionAlreadyExistsError,
    SessionNotFoundError,
    SessionRepository,
)
from .exceptions import (
    InvalidSessionStateValueError,
    SessionNotAvailableError,
    SessionServiceError,
)


DEFAULT_SESSION_TTL = timedelta(minutes=30)


def utc_now() -> datetime:
    """Return the default timezone-aware current time for session services."""

    return datetime.now(timezone.utc)


class SessionService:
    """Owns session lifecycle rules while delegating persistence to a repository.

    The MVP assumes agent tools mutate a single session sequentially. Concurrent
    state changes for the same session can still lose updates; multi-worker or
    parallel tool execution will need version-based optimistic locking or an
    atomic repository update operation.
    """

    def __init__(
        self,
        repository: SessionRepository,
        *,
        session_ttl: timedelta = DEFAULT_SESSION_TTL,
        now_provider: Callable[[], datetime] = utc_now,
        session_id_provider: Callable[[], str] | None = None,
    ) -> None:
        if session_ttl.total_seconds() <= 0:
            raise ValueError("session_ttl must be positive")
        self._repository = repository
        self._session_ttl = session_ttl
        self._now_provider = now_provider
        self._session_id_provider = session_id_provider or (lambda: str(uuid4()))

    def create_session(self) -> PlanuSessionState:
        """Create and persist a new empty session state."""

        now = self._now()
        session_id = self._session_id_provider()
        state = PlanuSessionState(
            session_id=session_id,
            created_at=now,
            updated_at=now,
            last_accessed_at=now,
            expires_at=now + self._session_ttl,
        )
        try:
            return self._repository.create(state, now=now)
        except SessionAlreadyExistsError as exc:
            raise SessionServiceError(f"session already exists: {session_id}") from exc

    def get_session(self, session_id: str) -> PlanuSessionState:
        """Return a live session without extending its TTL."""

        now = self._now()
        state = self._repository.get(session_id, now=now)
        if state is None:
            raise SessionNotAvailableError(session_id)
        return state

    def refresh_session(self, session_id: str) -> PlanuSessionState:
        """Extend access and expiration timestamps for a live session."""

        now = self._now()
        try:
            return self._repository.touch(
                session_id,
                now=now,
                last_accessed_at=now,
                expires_at=now + self._session_ttl,
            )
        except SessionNotFoundError as exc:
            raise SessionNotAvailableError(session_id) from exc

    def delete_session(self, session_id: str) -> None:
        """Delete a session idempotently."""

        self._repository.delete(session_id)

    def set_department(self, session_id: str, department: str) -> PlanuSessionState:
        """Set or replace the department name for a live session."""

        normalized_department = self._require_non_empty("department", department)
        return self._save_state_field(
            session_id,
            field_name="department",
            value=normalized_department,
        )

    def register_major_catalog(
        self,
        session_id: str,
        catalog_id: str,
    ) -> PlanuSessionState:
        """Store the identifier for a parsed major catalog."""

        normalized_catalog_id = self._require_non_empty("major_catalog_id", catalog_id)
        return self._save_state_field(
            session_id,
            field_name="major_catalog_id",
            value=normalized_catalog_id,
        )

    def register_elective_catalog(
        self,
        session_id: str,
        catalog_id: str,
    ) -> PlanuSessionState:
        """Store the identifier for a parsed elective catalog."""

        normalized_catalog_id = self._require_non_empty("elective_catalog_id", catalog_id)
        return self._save_state_field(
            session_id,
            field_name="elective_catalog_id",
            value=normalized_catalog_id,
        )

    def add_selected_major_course(
        self,
        session_id: str,
        course_id: str,
    ) -> PlanuSessionState:
        """Add one selected major course id, preserving insertion order."""

        normalized_course_id = self._require_non_empty(
            "selected_major_course_ids",
            course_id,
        )
        state = self.get_session(session_id)
        if normalized_course_id in state.selected_major_course_ids:
            return self._refresh_unchanged_state(state)
        return self._save_state_with_courses(
            state,
            [*state.selected_major_course_ids, normalized_course_id],
        )

    def remove_selected_major_course(
        self,
        session_id: str,
        course_id: str,
    ) -> PlanuSessionState:
        """Remove one selected major course id idempotently."""

        normalized_course_id = course_id.strip()
        state = self.get_session(session_id)
        if normalized_course_id not in state.selected_major_course_ids:
            return self._refresh_unchanged_state(state)
        return self._save_state_with_courses(
            state,
            [
                selected_course_id
                for selected_course_id in state.selected_major_course_ids
                if selected_course_id != normalized_course_id
            ],
        )

    def replace_selected_major_courses(
        self,
        session_id: str,
        course_ids: Iterable[str],
    ) -> PlanuSessionState:
        """Replace selected major course ids after trimming and de-duplicating."""

        normalized_course_ids = self._normalize_course_ids(course_ids)
        state = self.get_session(session_id)
        if normalized_course_ids == state.selected_major_course_ids:
            return self._refresh_unchanged_state(state)
        return self._save_state_with_courses(state, normalized_course_ids)

    def _save_state_field(
        self,
        session_id: str,
        *,
        field_name: str,
        value: str,
    ) -> PlanuSessionState:
        state = self.get_session(session_id)
        if getattr(state, field_name) == value:
            return self._refresh_unchanged_state(state)
        return self._save_changed_state(state, {field_name: value})

    def _save_changed_state(
        self,
        state: PlanuSessionState,
        update: dict[str, object],
    ) -> PlanuSessionState:
        now = self._now()
        changed = self._build_validated_state(
            state,
            {
                **update,
                "updated_at": now,
                "last_accessed_at": now,
                "expires_at": now + self._session_ttl,
            },
        )
        try:
            return self._repository.save(changed, now=now)
        except SessionNotFoundError as exc:
            raise SessionNotAvailableError(state.session_id) from exc

    def _save_state_with_courses(
        self,
        state: PlanuSessionState,
        selected_major_course_ids: list[str],
    ) -> PlanuSessionState:
        return self._save_changed_state(
            state,
            {"selected_major_course_ids": selected_major_course_ids},
        )

    def _refresh_unchanged_state(
        self,
        state: PlanuSessionState,
    ) -> PlanuSessionState:
        now = self._now()
        try:
            return self._repository.touch(
                state.session_id,
                now=now,
                last_accessed_at=now,
                expires_at=now + self._session_ttl,
            )
        except SessionNotFoundError as exc:
            raise SessionNotAvailableError(state.session_id) from exc

    @staticmethod
    def _build_validated_state(
        state: PlanuSessionState,
        update: dict[str, object],
    ) -> PlanuSessionState:
        return PlanuSessionState.model_validate(
            {
                **state.model_dump(),
                **update,
            }
        )

    def _now(self) -> datetime:
        now = self._now_provider()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("now_provider must return timezone-aware datetime")
        return now

    @staticmethod
    def _require_non_empty(field_name: str, value: str) -> str:
        normalized_value = value.strip()
        if not normalized_value:
            raise InvalidSessionStateValueError(field_name, value)
        return normalized_value

    @classmethod
    def _normalize_course_ids(cls, course_ids: Iterable[str]) -> list[str]:
        normalized_course_ids: list[str] = []
        seen: set[str] = set()
        for course_id in course_ids:
            normalized_course_id = cls._require_non_empty(
                "selected_major_course_ids",
                course_id,
            )
            if normalized_course_id in seen:
                continue
            normalized_course_ids.append(normalized_course_id)
            seen.add(normalized_course_id)
        return normalized_course_ids
