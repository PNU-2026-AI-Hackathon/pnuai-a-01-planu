"""Thread-safe, in-memory session storage used by the MVP API."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from enum import Enum
from threading import RLock
from typing import Any, Callable, Iterable
from uuid import uuid4

from ..models.course import Course
from ..models.course_load import CourseLoadTarget
from ..models.general_course_pool import (
    ExcludedCourseDiagnostic,
    GeneralCoursePoolResult,
)
from ..models.preference import PreferenceRules
from ..models.timetable import (
    GenerationDiagnostic,
    TimetableCandidate,
    TimetableGenerationCandidate,
    TimetableRankingResult,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SessionNotFoundError(KeyError):
    """Raised when a session id is unknown or its TTL has elapsed."""

    def __init__(self, session_id: str) -> None:
        super().__init__(session_id)
        self.session_id = session_id


class MajorConfirmStoreError(RuntimeError):
    """Base class for expected major preview confirmation failures."""


class MajorPreviewNotFoundError(MajorConfirmStoreError):
    pass


class InvalidPreviewSessionError(MajorConfirmStoreError):
    pass


class StaleMajorPreviewError(MajorConfirmStoreError):
    pass


class InvalidMajorConfirmStageError(MajorConfirmStoreError):
    pass


class MajorAlreadyConfirmedError(MajorConfirmStoreError):
    pass


class MajorCourseReferenceMismatchError(MajorConfirmStoreError):
    pass


class SessionStage(str, Enum):
    CATALOG_PARSED = "catalog_parsed"
    MAJOR_PREVIEW_CREATED = "major_preview_created"
    MAJOR_CONFIRMED = "major_confirmed"
    GENERAL_READY = "general_ready"
    CANDIDATES_GENERATED = "candidates_generated"
    RANKING_COMPLETED = "ranking_completed"


@dataclass(slots=True)
class SessionData:
    session_id: str
    department: str
    major_candidates: list[Course] = field(default_factory=list)
    elective_candidates: list[Course] = field(default_factory=list)
    fixed_courses: list[Course] = field(default_factory=list)
    general_required_candidates: list[Course] = field(default_factory=list)
    general_elective_candidates: list[Course] = field(default_factory=list)
    general_pool_diagnostics: list[ExcludedCourseDiagnostic] = field(default_factory=list)
    general_pool_warnings: list[str] = field(default_factory=list)
    generated_candidates: list[TimetableCandidate] = field(default_factory=list)
    ranking_preferences: PreferenceRules = field(default_factory=PreferenceRules)
    latest_ranking_result: TimetableRankingResult | None = None
    generated_timetable_candidates: list[TimetableGenerationCandidate] = field(default_factory=list)
    generation_diagnostics: list[GenerationDiagnostic] = field(default_factory=list)
    generation_course_load_target: CourseLoadTarget | None = None
    generation_hard_conditions: PreferenceRules | None = None
    generation_truncated: bool = False
    generated_at: datetime | None = None
    confirmed_major_credits: float = 0
    session_stage: SessionStage = SessionStage.CATALOG_PARSED
    confirmed_major_preview_id: str | None = None
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
        self.general_required_candidates = list(self.general_required_candidates)
        self.general_elective_candidates = list(self.general_elective_candidates)
        self.general_pool_diagnostics = list(self.general_pool_diagnostics)
        self.general_pool_warnings = list(self.general_pool_warnings)
        self.generated_candidates = list(self.generated_candidates)
        if not isinstance(self.ranking_preferences, PreferenceRules):
            self.ranking_preferences = PreferenceRules.model_validate(
                self.ranking_preferences
            )
        if (
            self.latest_ranking_result is not None
            and not isinstance(self.latest_ranking_result, TimetableRankingResult)
        ):
            self.latest_ranking_result = TimetableRankingResult.model_validate(
                self.latest_ranking_result
            )
        self.generated_timetable_candidates = list(self.generated_timetable_candidates)
        self.generation_diagnostics = list(self.generation_diagnostics)
        if (
            self.generation_hard_conditions is not None
            and not isinstance(self.generation_hard_conditions, PreferenceRules)
        ):
            self.generation_hard_conditions = PreferenceRules.model_validate(
                self.generation_hard_conditions
            )
        if not isinstance(self.session_stage, SessionStage):
            self.session_stage = SessionStage(self.session_stage)
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
            data = self._get_live_locked(session_id, touch=touch)
            return self._copy(data)

    get_session = get

    def confirm_major_preview(
        self,
        session_id: str,
        *,
        preview_id: str,
        fixed_courses: Iterable[Course],
        confirmed_major_credits: float,
        confirmed_preview: dict[str, Any],
    ) -> SessionData:
        """Atomically confirm the latest major preview for one in-memory session."""

        with self._lock:
            data = self._get_live_locked(session_id, touch=False)

            if data.fixed_courses:
                if data.confirmed_major_preview_id == preview_id:
                    data.updated_at = self._clock()
                    return self._copy(data)
                raise MajorAlreadyConfirmedError("session already confirmed with another preview")

            if data.session_stage is not SessionStage.MAJOR_PREVIEW_CREATED:
                raise InvalidMajorConfirmStageError("major preview stage is required")

            preview = data.latest_major_preview
            if preview is None:
                raise MajorPreviewNotFoundError("major preview not found")
            if preview.get("session_id") not in (None, data.session_id):
                raise InvalidPreviewSessionError("preview belongs to another session")
            if preview.get("preview_id") != preview_id:
                raise StaleMajorPreviewError("latest preview id does not match")

            courses = list(fixed_courses)
            preview_course_ids = list(preview.get("matched_course_ids") or [])
            fixed_course_ids = [course.course_id for course in courses]
            if preview_course_ids != fixed_course_ids:
                raise MajorCourseReferenceMismatchError(
                    "fixed courses do not match latest preview references"
                )

            data.fixed_courses = courses
            data.confirmed_major_credits = confirmed_major_credits
            data.session_stage = SessionStage.MAJOR_CONFIRMED
            data.confirmed_major_preview_id = preview_id
            data.latest_major_preview = dict(confirmed_preview)
            data.updated_at = self._clock()
            return self._copy(data)

    def update(
        self,
        session_id: str,
        *,
        department: str | None = None,
        major_candidates: Iterable[Course] | None = None,
        elective_candidates: Iterable[Course] | None = None,
        fixed_courses: Iterable[Course] | None = None,
        confirmed_major_credits: float | None = None,
        session_stage: SessionStage | str | None = None,
        confirmed_major_preview_id: str | None = None,
        latest_major_preview: dict[str, Any] | None = None,
        generated_candidates: Iterable[TimetableCandidate] | None = None,
        ranking_preferences: PreferenceRules | None = None,
        latest_ranking_result: TimetableRankingResult | None = None,
        generated_timetable_candidates: Iterable[TimetableGenerationCandidate] | None = None,
        generation_diagnostics: Iterable[GenerationDiagnostic] | None = None,
        generation_course_load_target: CourseLoadTarget | None = None,
        generation_hard_conditions: PreferenceRules | None = None,
        generation_truncated: bool | None = None,
        generated_at: datetime | None = None,
    ) -> SessionData:
        with self._lock:
            # get() performs expiry handling; the stored instance is then updated.
            data = self._get_live_locked(session_id, touch=False)
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
            if confirmed_major_credits is not None:
                data.confirmed_major_credits = confirmed_major_credits
            if session_stage is not None:
                data.session_stage = (
                    session_stage
                    if isinstance(session_stage, SessionStage)
                    else SessionStage(session_stage)
                )
            if confirmed_major_preview_id is not None:
                data.confirmed_major_preview_id = confirmed_major_preview_id
            if latest_major_preview is not None:
                data.latest_major_preview = dict(latest_major_preview)
            if generated_candidates is not None:
                data.generated_candidates = list(generated_candidates)
            if ranking_preferences is not None:
                data.ranking_preferences = ranking_preferences
            if latest_ranking_result is not None:
                data.latest_ranking_result = latest_ranking_result
            if generated_timetable_candidates is not None:
                data.generated_timetable_candidates = list(generated_timetable_candidates)
            if generation_diagnostics is not None:
                data.generation_diagnostics = list(generation_diagnostics)
            if generation_course_load_target is not None:
                data.generation_course_load_target = generation_course_load_target
            if generation_hard_conditions is not None:
                data.generation_hard_conditions = generation_hard_conditions
            if generation_truncated is not None:
                data.generation_truncated = generation_truncated
            if generated_at is not None:
                data.generated_at = generated_at
            data.updated_at = self._clock()
            return self._copy(data)

    update_session = update

    def update_general_course_pool(
        self,
        session_id: str,
        result: GeneralCoursePoolResult,
    ) -> SessionData:
        with self._lock:
            data = self._get_live_locked(session_id, touch=False)
            data.general_required_candidates = list(result.pools.required_courses)
            data.general_elective_candidates = list(result.pools.elective_courses)
            data.general_pool_diagnostics = list(result.excluded_courses)
            data.general_pool_warnings = list(result.warnings)
            data.session_stage = SessionStage.GENERAL_READY
            data.updated_at = self._clock()
            return self._copy(data)

    def update_generated_candidates(
        self,
        session_id: str,
        *,
        candidates: Iterable[TimetableCandidate],
        preferences: PreferenceRules | None = None,
    ) -> SessionData:
        with self._lock:
            data = self._get_live_locked(session_id, touch=False)
            data.generated_candidates = list(candidates)
            if preferences is not None:
                data.ranking_preferences = preferences
            data.session_stage = SessionStage.CANDIDATES_GENERATED
            data.latest_ranking_result = None
            data.updated_at = self._clock()
            return self._copy(data)

    def update_ranking_result(
        self,
        session_id: str,
        result: TimetableRankingResult,
    ) -> SessionData:
        with self._lock:
            data = self._get_live_locked(session_id, touch=False)
            data.latest_ranking_result = result
            data.session_stage = SessionStage.RANKING_COMPLETED
            data.updated_at = self._clock()
            return self._copy(data)

    def update_timetable_generation(
        self,
        session_id: str,
        *,
        candidates: Iterable[TimetableGenerationCandidate],
        diagnostics: Iterable[GenerationDiagnostic],
        course_load_target: CourseLoadTarget,
        hard_conditions: PreferenceRules | None,
        truncated: bool,
    ) -> SessionData:
        with self._lock:
            data = self._get_live_locked(session_id, touch=False)
            now = self._clock()
            data.generated_timetable_candidates = list(candidates)
            data.generation_diagnostics = list(diagnostics)
            data.generation_course_load_target = course_load_target
            data.generation_hard_conditions = hard_conditions
            data.generation_truncated = truncated
            data.generated_candidates = [
                candidate.timetable.model_copy(
                    update={"load_satisfaction": candidate.load_satisfaction}
                )
                for candidate in data.generated_timetable_candidates
            ]
            data.ranking_preferences = hard_conditions or PreferenceRules()
            data.latest_ranking_result = None
            data.generated_at = now
            data.updated_at = now
            return self._copy(data)

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

    def _get_live_locked(self, session_id: str, *, touch: bool) -> SessionData:
        now = self._clock()
        data = self._sessions.get(session_id)
        if data is None or self._is_expired(data, now):
            self._sessions.pop(session_id, None)
            raise SessionNotFoundError(session_id)
        if touch:
            data.updated_at = now
        return data

    @staticmethod
    def _copy(data: SessionData) -> SessionData:
        return replace(
            data,
            major_candidates=list(data.major_candidates),
            elective_candidates=list(data.elective_candidates),
            fixed_courses=list(data.fixed_courses),
            general_required_candidates=list(data.general_required_candidates),
            general_elective_candidates=list(data.general_elective_candidates),
            general_pool_diagnostics=list(data.general_pool_diagnostics),
            general_pool_warnings=list(data.general_pool_warnings),
            generated_candidates=list(data.generated_candidates),
            ranking_preferences=data.ranking_preferences.model_copy(deep=True),
            latest_ranking_result=(
                data.latest_ranking_result.model_copy(deep=True)
                if data.latest_ranking_result is not None
                else None
            ),
            generated_timetable_candidates=list(data.generated_timetable_candidates),
            generation_diagnostics=list(data.generation_diagnostics),
            generation_course_load_target=data.generation_course_load_target,
            generation_hard_conditions=(
                data.generation_hard_conditions.model_copy(deep=True)
                if data.generation_hard_conditions is not None
                else None
            ),
            generation_truncated=data.generation_truncated,
            generated_at=data.generated_at,
            session_stage=data.session_stage,
            latest_major_preview=(
                dict(data.latest_major_preview)
                if data.latest_major_preview is not None
                else None
            ),
        )


# A single store is sufficient while the application runs in one process.
session_store = SessionStore()
