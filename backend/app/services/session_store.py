"""Thread-safe, in-memory session storage used by the MVP API."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from threading import RLock
from typing import Any, Callable, Iterable
from uuid import uuid4

from ..models.course import Course


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SessionNotFoundError(KeyError):
    """Raised when a session id is unknown or its TTL has elapsed."""

    def __init__(self, session_id: str) -> None:
        super().__init__(session_id)
        self.session_id = session_id


@dataclass(slots=True)
class SessionData:
    session_id: str
    department: str
    major_candidates: list[Course] = field(default_factory=list)
    elective_candidates: list[Course] = field(default_factory=list)
    fixed_courses: list[Course] = field(default_factory=list)
    latest_major_preview: dict[str, Any] | None = None
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)

    def __post_init__(self) -> None:
        if not self.session_id.strip():
            raise ValueError("session_id must not be empty")
        if not self.department.strip():
            raise ValueError("department must not be empty")
        # Do not retain mutable lists owned by request handlers.
        self.major_candidates = list(self.major_candidates)
        self.elective_candidates = list(self.elective_candidates)
        self.fixed_courses = list(self.fixed_courses)
        if self.latest_major_preview is not None:
            self.latest_major_preview = dict(self.latest_major_preview)


class SessionStore:
    """A small process-local store with sliding, configurable TTL expiration."""

    def __init__(
        self,
        ttl: timedelta | float = timedelta(minutes=30),
        *,
        ttl_seconds: float | None = None,
        clock: Callable[[], datetime] = _utcnow,
    ) -> None:
        if ttl_seconds is not None:
            ttl = ttl_seconds
        self.ttl = ttl if isinstance(ttl, timedelta) else timedelta(seconds=ttl)
        if self.ttl.total_seconds() <= 0:
            raise ValueError("ttl must be positive")
        self._clock = clock
        self._sessions: dict[str, SessionData] = {}
        self._lock = RLock()

    def create(
        self,
        department: str,
        major_candidates: Iterable[Course] = (),
        elective_candidates: Iterable[Course] = (),
        *,
        session_id: str | None = None,
    ) -> SessionData:
        now = self._clock()
        data = SessionData(
            session_id=session_id or str(uuid4()),
            department=department,
            major_candidates=list(major_candidates),
            elective_candidates=list(elective_candidates),
            created_at=now,
            updated_at=now,
        )
        with self._lock:
            self.cleanup_expired(now=now)
            if data.session_id in self._sessions:
                raise ValueError(f"session already exists: {data.session_id}")
            self._sessions[data.session_id] = data
            return self._copy(data)

    # Explicit alias makes route code self-documenting and keeps the common API.
    create_session = create

    def get(self, session_id: str, *, touch: bool = True) -> SessionData:
        with self._lock:
            now = self._clock()
            data = self._sessions.get(session_id)
            if data is None or self._is_expired(data, now):
                self._sessions.pop(session_id, None)
                raise SessionNotFoundError(session_id)
            if touch:
                data.updated_at = now
            return self._copy(data)

    get_session = get

    def update(
        self,
        session_id: str,
        *,
        department: str | None = None,
        major_candidates: Iterable[Course] | None = None,
        elective_candidates: Iterable[Course] | None = None,
        fixed_courses: Iterable[Course] | None = None,
        latest_major_preview: dict[str, Any] | None = None,
    ) -> SessionData:
        with self._lock:
            # get() performs expiry handling; the stored instance is then updated.
            self.get(session_id, touch=False)
            data = self._sessions[session_id]
            if department is not None:
                if not department.strip():
                    raise ValueError("department must not be empty")
                data.department = department
            if major_candidates is not None:
                data.major_candidates = list(major_candidates)
            if elective_candidates is not None:
                data.elective_candidates = list(elective_candidates)
            if fixed_courses is not None:
                data.fixed_courses = list(fixed_courses)
            if latest_major_preview is not None:
                data.latest_major_preview = dict(latest_major_preview)
            data.updated_at = self._clock()
            return self._copy(data)

    update_session = update

    def delete(self, session_id: str) -> bool:
        with self._lock:
            return self._sessions.pop(session_id, None) is not None

    delete_session = delete

    def cleanup_expired(self, *, now: datetime | None = None) -> int:
        with self._lock:
            current = now or self._clock()
            expired = [
                key for key, data in self._sessions.items()
                if self._is_expired(data, current)
            ]
            for key in expired:
                del self._sessions[key]
            return len(expired)

    def __len__(self) -> int:
        self.cleanup_expired()
        with self._lock:
            return len(self._sessions)

    def _is_expired(self, data: SessionData, now: datetime) -> bool:
        return now - data.updated_at >= self.ttl

    @staticmethod
    def _copy(data: SessionData) -> SessionData:
        return replace(
            data,
            major_candidates=list(data.major_candidates),
            elective_candidates=list(data.elective_candidates),
            fixed_courses=list(data.fixed_courses),
            latest_major_preview=(
                dict(data.latest_major_preview)
                if data.latest_major_preview is not None
                else None
            ),
        )


# A single store is sufficient while the application runs in one process.
session_store = SessionStore()
