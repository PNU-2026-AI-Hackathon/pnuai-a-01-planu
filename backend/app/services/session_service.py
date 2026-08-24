"""Service boundary for future PlaNU agent session state tools."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from pydantic import ValidationError

from ..models.timetable_generation import GeneratedTimetableCandidate
from ..models import (
    Day,
    SelectedTimetable,
    SelectedTimetableStatus,
    HardConstraints,
    PlanuSessionState,
    SoftPreferences,
    time_to_minutes,
)
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
from .session_update_models import (
    HardConstraintsUpdate,
    SelectedMajorCourseMode,
    SessionProfileUpdate,
    SoftPreferencesUpdate,
)


DEFAULT_SESSION_TTL = timedelta(minutes=30)


def utc_now() -> datetime:
    """Return the default timezone-aware current time for session services."""

    return datetime.now(timezone.utc)


class SessionInputNormalizer:
    """Normalize public service inputs before they are applied to state."""

    @staticmethod
    def require_non_empty(field_name: str, value: str) -> str:
        normalized_value = value.strip()
        if not normalized_value:
            raise InvalidSessionStateValueError(field_name, value)
        return normalized_value

    @classmethod
    def course_ids(
        cls,
        course_ids: Iterable[str],
        *,
        field_name: str,
    ) -> list[str]:
        normalized_course_ids: list[str] = []
        seen: set[str] = set()
        for course_id in course_ids:
            normalized_course_id = cls.require_non_empty(field_name, course_id)
            if normalized_course_id in seen:
                continue
            normalized_course_ids.append(normalized_course_id)
            seen.add(normalized_course_id)
        return normalized_course_ids

    @staticmethod
    def day(field_name: str, day: Day | str) -> Day:
        try:
            return day if isinstance(day, Day) else Day(day)
        except ValueError as exc:
            raise InvalidSessionStateValueError(
                field_name,
                day,
                "day must be one of MON, TUE, WED, THU, FRI, SAT, SUN",
            ) from exc

    @classmethod
    def days(
        cls,
        field_name: str,
        days: Iterable[Day | str],
    ) -> list[Day]:
        normalized_days: list[Day] = []
        seen: set[Day] = set()
        for day in days:
            normalized_day = cls.day(field_name, day)
            if normalized_day in seen:
                continue
            normalized_days.append(normalized_day)
            seen.add(normalized_day)
        return normalized_days

    @staticmethod
    def time(field_name: str, time_value: str) -> str:
        normalized_time = time_value.strip()
        try:
            time_to_minutes(normalized_time)
        except ValueError as exc:
            raise InvalidSessionStateValueError(field_name, time_value, str(exc)) from exc
        return normalized_time


class SessionStateBuilder:
    """Build validated session preference models and map validation failures."""

    @staticmethod
    def hard_constraints(
        hard_constraints: HardConstraints,
        **update: object,
    ) -> HardConstraints:
        try:
            return HardConstraints.model_validate(
                {
                    **hard_constraints.model_dump(),
                    **update,
                }
            )
        except ValidationError as exc:
            raise InvalidSessionStateValueError(
                next(iter(update), "hard_constraints"),
                update,
                str(exc.errors()[0]["msg"]),
            ) from exc

    @staticmethod
    def soft_preferences(
        soft_preferences: SoftPreferences,
        **update: object,
    ) -> SoftPreferences:
        try:
            return SoftPreferences.model_validate(
                {
                    **soft_preferences.model_dump(),
                    **update,
                }
            )
        except ValidationError as exc:
            raise InvalidSessionStateValueError(
                next(iter(update), "soft_preferences"),
                update,
                str(exc.errors()[0]["msg"]),
            ) from exc


class PreferenceConflictValidator:
    """Validate rules that require both hard constraints and soft preferences."""

    @staticmethod
    def validate(
        hard_constraints: HardConstraints,
        soft_preferences: SoftPreferences,
    ) -> None:
        duplicated_days = set(hard_constraints.required_free_days) & set(
            soft_preferences.preferred_free_days
        )
        if duplicated_days:
            raise InvalidSessionStateValueError(
                "preferred_free_days",
                sorted(day.value for day in duplicated_days),
                "day is already hard-required as free",
            )

        if (
            hard_constraints.earliest_start_time is not None
            and soft_preferences.preferred_earliest_start_time is not None
            and time_to_minutes(soft_preferences.preferred_earliest_start_time)
            < time_to_minutes(hard_constraints.earliest_start_time)
        ):
            raise InvalidSessionStateValueError(
                "preferred_earliest_start_time",
                soft_preferences.preferred_earliest_start_time,
                "preference is earlier than the hard earliest_start_time",
            )

        if (
            hard_constraints.latest_end_time is not None
            and soft_preferences.preferred_latest_end_time is not None
            and time_to_minutes(soft_preferences.preferred_latest_end_time)
            > time_to_minutes(hard_constraints.latest_end_time)
        ):
            raise InvalidSessionStateValueError(
                "preferred_latest_end_time",
                soft_preferences.preferred_latest_end_time,
                "preference is later than the hard latest_end_time",
            )

        required = set(hard_constraints.required_course_ids)
        excluded = set(hard_constraints.excluded_course_ids)
        preferred = set(soft_preferences.preferred_course_ids)
        disliked = set(soft_preferences.disliked_course_ids)

        hard_preferred_overlap = excluded & preferred
        if hard_preferred_overlap:
            raise InvalidSessionStateValueError(
                "preferred_course_ids",
                sorted(hard_preferred_overlap),
                "course is hard-excluded",
            )

        hard_disliked_overlap = required & disliked
        if hard_disliked_overlap:
            raise InvalidSessionStateValueError(
                "disliked_course_ids",
                sorted(hard_disliked_overlap),
                "course is hard-required",
            )

        redundant_soft = (required & preferred) | (excluded & disliked)
        if redundant_soft:
            raise InvalidSessionStateValueError(
                "soft_preferences",
                sorted(redundant_soft),
                "course is already covered by hard constraints",
            )


class SessionService:
    """Owns session lifecycle rules while delegating persistence to a repository.

    Preference mutation methods accept resolved domain values. In particular,
    course preference methods require concrete ``course_id`` values; LLM output
    that names courses must first pass through a resolver that checks the active
    catalog and handles ambiguous divisions.

    The fine-grained methods here are service commands, not the final agent Tool
    surface. A future Tool layer may batch several changes into one request while
    still delegating the actual state mutation rules to this service.

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

    def update_profile(
        self,
        session_id: str,
        update: SessionProfileUpdate,
    ) -> PlanuSessionState:
        """Apply a profile patch in one session save.

        Fields set to ``None`` are left unchanged unless explicitly listed in
        ``clear_fields``.
        """

        state = self.get_session(session_id)
        changed_fields: dict[str, object] = {}
        values = {
            "department": update.department,
            "major_catalog_id": update.major_catalog_id,
            "elective_catalog_id": update.elective_catalog_id,
        }
        for field_name in update.clear_fields:
            changed_fields[field_name] = None
        for field_name, value in values.items():
            if value is not None:
                changed_fields[field_name] = self._require_non_empty(field_name, value)
        return self._save_state_update_if_changed(state, changed_fields)

    def update_selected_major_courses(
        self,
        session_id: str,
        course_ids: Iterable[str],
        *,
        mode: SelectedMajorCourseMode = "replace",
    ) -> PlanuSessionState:
        """Update selected major course ids in one session save."""

        normalized_course_ids = self._normalize_course_ids(course_ids)
        state = self.get_session(session_id)
        if mode == "replace":
            next_course_ids = normalized_course_ids
        elif mode == "add":
            next_course_ids = [
                *state.selected_major_course_ids,
                *[
                    course_id
                    for course_id in normalized_course_ids
                    if course_id not in state.selected_major_course_ids
                ],
            ]
        elif mode == "remove":
            removed = set(normalized_course_ids)
            next_course_ids = [
                course_id
                for course_id in state.selected_major_course_ids
                if course_id not in removed
            ]
        else:
            raise InvalidSessionStateValueError(
                "mode",
                mode,
                "mode must be one of replace, add, remove",
            )
        return self._save_state_with_courses_if_changed(state, next_course_ids)

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

    def add_required_free_day(
        self,
        session_id: str,
        day: Day | str,
    ) -> PlanuSessionState:
        normalized_day = self._normalize_day("required_free_days", day)

        def mutate(
            hard: HardConstraints,
            soft: SoftPreferences,
        ) -> tuple[HardConstraints, SoftPreferences]:
            return (
                self._build_hard_constraints(
                    hard,
                    required_free_days=[*hard.required_free_days, normalized_day],
                ),
                self._build_soft_preferences(
                    soft,
                    preferred_free_days=[
                        free_day
                        for free_day in soft.preferred_free_days
                        if free_day != normalized_day
                    ],
                ),
            )

        return self._save_constraints(session_id, mutate)

    def remove_required_free_day(
        self,
        session_id: str,
        day: Day | str,
    ) -> PlanuSessionState:
        normalized_day = self._normalize_day("required_free_days", day)

        def mutate(
            hard: HardConstraints,
            soft: SoftPreferences,
        ) -> tuple[HardConstraints, SoftPreferences]:
            return (
                self._build_hard_constraints(
                    hard,
                    required_free_days=[
                        free_day
                        for free_day in hard.required_free_days
                        if free_day != normalized_day
                    ],
                ),
                soft,
            )

        return self._save_constraints(session_id, mutate)

    def replace_required_free_days(
        self,
        session_id: str,
        days: Iterable[Day | str],
    ) -> PlanuSessionState:
        normalized_days = self._normalize_days("required_free_days", days)

        def mutate(
            hard: HardConstraints,
            soft: SoftPreferences,
        ) -> tuple[HardConstraints, SoftPreferences]:
            return (
                self._build_hard_constraints(
                    hard,
                    required_free_days=normalized_days,
                ),
                self._build_soft_preferences(
                    soft,
                    preferred_free_days=[
                        day
                        for day in soft.preferred_free_days
                        if day not in normalized_days
                    ],
                ),
            )

        return self._save_constraints(session_id, mutate)

    def set_earliest_start_time(
        self,
        session_id: str,
        time_value: str,
    ) -> PlanuSessionState:
        normalized_time = self._normalize_time("earliest_start_time", time_value)
        return self._set_hard_time(session_id, "earliest_start_time", normalized_time)

    def clear_earliest_start_time(self, session_id: str) -> PlanuSessionState:
        return self._set_hard_time(session_id, "earliest_start_time", None)

    def set_latest_end_time(
        self,
        session_id: str,
        time_value: str,
    ) -> PlanuSessionState:
        normalized_time = self._normalize_time("latest_end_time", time_value)
        return self._set_hard_time(session_id, "latest_end_time", normalized_time)

    def clear_latest_end_time(self, session_id: str) -> PlanuSessionState:
        return self._set_hard_time(session_id, "latest_end_time", None)

    def add_required_course(
        self,
        session_id: str,
        course_id: str,
    ) -> PlanuSessionState:
        normalized_course_id = self._require_non_empty("required_course_ids", course_id)

        def mutate(
            hard: HardConstraints,
            soft: SoftPreferences,
        ) -> tuple[HardConstraints, SoftPreferences]:
            return (
                self._build_hard_constraints(
                    hard,
                    required_course_ids=[
                        *hard.required_course_ids,
                        normalized_course_id,
                    ],
                    excluded_course_ids=[
                        item
                        for item in hard.excluded_course_ids
                        if item != normalized_course_id
                    ],
                ),
                self._build_soft_preferences(
                    soft,
                    preferred_course_ids=[
                        item
                        for item in soft.preferred_course_ids
                        if item != normalized_course_id
                    ],
                    disliked_course_ids=[
                        item
                        for item in soft.disliked_course_ids
                        if item != normalized_course_id
                    ],
                ),
            )

        return self._save_constraints(session_id, mutate)

    def remove_required_course(
        self,
        session_id: str,
        course_id: str,
    ) -> PlanuSessionState:
        normalized_course_id = course_id.strip()

        def mutate(
            hard: HardConstraints,
            soft: SoftPreferences,
        ) -> tuple[HardConstraints, SoftPreferences]:
            return (
                self._build_hard_constraints(
                    hard,
                    required_course_ids=[
                        item
                        for item in hard.required_course_ids
                        if item != normalized_course_id
                    ],
                ),
                soft,
            )

        return self._save_constraints(session_id, mutate)

    def add_excluded_course(
        self,
        session_id: str,
        course_id: str,
    ) -> PlanuSessionState:
        normalized_course_id = self._require_non_empty("excluded_course_ids", course_id)

        def mutate(
            hard: HardConstraints,
            soft: SoftPreferences,
        ) -> tuple[HardConstraints, SoftPreferences]:
            return (
                self._build_hard_constraints(
                    hard,
                    required_course_ids=[
                        item
                        for item in hard.required_course_ids
                        if item != normalized_course_id
                    ],
                    excluded_course_ids=[
                        *hard.excluded_course_ids,
                        normalized_course_id,
                    ],
                ),
                self._build_soft_preferences(
                    soft,
                    preferred_course_ids=[
                        item
                        for item in soft.preferred_course_ids
                        if item != normalized_course_id
                    ],
                    disliked_course_ids=[
                        item
                        for item in soft.disliked_course_ids
                        if item != normalized_course_id
                    ],
                ),
            )

        return self._save_constraints(session_id, mutate)

    def remove_excluded_course(
        self,
        session_id: str,
        course_id: str,
    ) -> PlanuSessionState:
        normalized_course_id = course_id.strip()

        def mutate(
            hard: HardConstraints,
            soft: SoftPreferences,
        ) -> tuple[HardConstraints, SoftPreferences]:
            return (
                self._build_hard_constraints(
                    hard,
                    excluded_course_ids=[
                        item
                        for item in hard.excluded_course_ids
                        if item != normalized_course_id
                    ],
                ),
                soft,
            )

        return self._save_constraints(session_id, mutate)

    def replace_required_courses(
        self,
        session_id: str,
        course_ids: Iterable[str],
    ) -> PlanuSessionState:
        normalized_course_ids = self._normalize_course_ids(
            course_ids,
            field_name="required_course_ids",
        )

        def mutate(
            hard: HardConstraints,
            soft: SoftPreferences,
        ) -> tuple[HardConstraints, SoftPreferences]:
            required = set(normalized_course_ids)
            return (
                self._build_hard_constraints(
                    hard,
                    required_course_ids=normalized_course_ids,
                    excluded_course_ids=[
                        item for item in hard.excluded_course_ids if item not in required
                    ],
                ),
                self._build_soft_preferences(
                    soft,
                    preferred_course_ids=[
                        item for item in soft.preferred_course_ids if item not in required
                    ],
                    disliked_course_ids=[
                        item for item in soft.disliked_course_ids if item not in required
                    ],
                ),
            )

        return self._save_constraints(session_id, mutate)

    def replace_excluded_courses(
        self,
        session_id: str,
        course_ids: Iterable[str],
    ) -> PlanuSessionState:
        normalized_course_ids = self._normalize_course_ids(
            course_ids,
            field_name="excluded_course_ids",
        )

        def mutate(
            hard: HardConstraints,
            soft: SoftPreferences,
        ) -> tuple[HardConstraints, SoftPreferences]:
            excluded = set(normalized_course_ids)
            return (
                self._build_hard_constraints(
                    hard,
                    required_course_ids=[
                        item for item in hard.required_course_ids if item not in excluded
                    ],
                    excluded_course_ids=normalized_course_ids,
                ),
                self._build_soft_preferences(
                    soft,
                    preferred_course_ids=[
                        item for item in soft.preferred_course_ids if item not in excluded
                    ],
                    disliked_course_ids=[
                        item for item in soft.disliked_course_ids if item not in excluded
                    ],
                ),
            )

        return self._save_constraints(session_id, mutate)

    def add_preferred_free_day(
        self,
        session_id: str,
        day: Day | str,
    ) -> PlanuSessionState:
        normalized_day = self._normalize_day("preferred_free_days", day)

        def mutate(
            hard: HardConstraints,
            soft: SoftPreferences,
        ) -> tuple[HardConstraints, SoftPreferences]:
            if normalized_day in hard.required_free_days:
                return hard, soft
            return (
                hard,
                self._build_soft_preferences(
                    soft,
                    preferred_free_days=[*soft.preferred_free_days, normalized_day],
                ),
            )

        return self._save_constraints(session_id, mutate)

    def remove_preferred_free_day(
        self,
        session_id: str,
        day: Day | str,
    ) -> PlanuSessionState:
        normalized_day = self._normalize_day("preferred_free_days", day)

        def mutate(
            hard: HardConstraints,
            soft: SoftPreferences,
        ) -> tuple[HardConstraints, SoftPreferences]:
            return (
                hard,
                self._build_soft_preferences(
                    soft,
                    preferred_free_days=[
                        free_day
                        for free_day in soft.preferred_free_days
                        if free_day != normalized_day
                    ],
                ),
            )

        return self._save_constraints(session_id, mutate)

    def replace_preferred_free_days(
        self,
        session_id: str,
        days: Iterable[Day | str],
    ) -> PlanuSessionState:
        normalized_days = self._normalize_days("preferred_free_days", days)

        def mutate(
            hard: HardConstraints,
            soft: SoftPreferences,
        ) -> tuple[HardConstraints, SoftPreferences]:
            required = set(hard.required_free_days)
            return (
                hard,
                self._build_soft_preferences(
                    soft,
                    preferred_free_days=[
                        day for day in normalized_days if day not in required
                    ],
                ),
            )

        return self._save_constraints(session_id, mutate)

    def set_preferred_earliest_start_time(
        self,
        session_id: str,
        time_value: str,
    ) -> PlanuSessionState:
        normalized_time = self._normalize_time(
            "preferred_earliest_start_time",
            time_value,
        )
        return self._set_soft_time(
            session_id,
            "preferred_earliest_start_time",
            normalized_time,
        )

    def clear_preferred_earliest_start_time(self, session_id: str) -> PlanuSessionState:
        return self._set_soft_time(session_id, "preferred_earliest_start_time", None)

    def set_preferred_latest_end_time(
        self,
        session_id: str,
        time_value: str,
    ) -> PlanuSessionState:
        normalized_time = self._normalize_time(
            "preferred_latest_end_time",
            time_value,
        )
        return self._set_soft_time(
            session_id,
            "preferred_latest_end_time",
            normalized_time,
        )

    def clear_preferred_latest_end_time(self, session_id: str) -> PlanuSessionState:
        return self._set_soft_time(session_id, "preferred_latest_end_time", None)

    def add_preferred_course(
        self,
        session_id: str,
        course_id: str,
    ) -> PlanuSessionState:
        normalized_course_id = self._require_non_empty("preferred_course_ids", course_id)

        def mutate(
            hard: HardConstraints,
            soft: SoftPreferences,
        ) -> tuple[HardConstraints, SoftPreferences]:
            if normalized_course_id in hard.excluded_course_ids:
                raise InvalidSessionStateValueError(
                    "preferred_course_ids",
                    normalized_course_id,
                    "course is hard-excluded",
                )
            if normalized_course_id in hard.required_course_ids:
                return hard, soft
            return (
                hard,
                self._build_soft_preferences(
                    soft,
                    preferred_course_ids=[
                        *soft.preferred_course_ids,
                        normalized_course_id,
                    ],
                    disliked_course_ids=[
                        item
                        for item in soft.disliked_course_ids
                        if item != normalized_course_id
                    ],
                ),
            )

        return self._save_constraints(session_id, mutate)

    def remove_preferred_course(
        self,
        session_id: str,
        course_id: str,
    ) -> PlanuSessionState:
        normalized_course_id = course_id.strip()

        def mutate(
            hard: HardConstraints,
            soft: SoftPreferences,
        ) -> tuple[HardConstraints, SoftPreferences]:
            return (
                hard,
                self._build_soft_preferences(
                    soft,
                    preferred_course_ids=[
                        item
                        for item in soft.preferred_course_ids
                        if item != normalized_course_id
                    ],
                ),
            )

        return self._save_constraints(session_id, mutate)

    def add_disliked_course(
        self,
        session_id: str,
        course_id: str,
    ) -> PlanuSessionState:
        normalized_course_id = self._require_non_empty("disliked_course_ids", course_id)

        def mutate(
            hard: HardConstraints,
            soft: SoftPreferences,
        ) -> tuple[HardConstraints, SoftPreferences]:
            if normalized_course_id in hard.required_course_ids:
                raise InvalidSessionStateValueError(
                    "disliked_course_ids",
                    normalized_course_id,
                    "course is hard-required",
                )
            if normalized_course_id in hard.excluded_course_ids:
                return hard, soft
            return (
                hard,
                self._build_soft_preferences(
                    soft,
                    preferred_course_ids=[
                        item
                        for item in soft.preferred_course_ids
                        if item != normalized_course_id
                    ],
                    disliked_course_ids=[
                        *soft.disliked_course_ids,
                        normalized_course_id,
                    ],
                ),
            )

        return self._save_constraints(session_id, mutate)

    def remove_disliked_course(
        self,
        session_id: str,
        course_id: str,
    ) -> PlanuSessionState:
        normalized_course_id = course_id.strip()

        def mutate(
            hard: HardConstraints,
            soft: SoftPreferences,
        ) -> tuple[HardConstraints, SoftPreferences]:
            return (
                hard,
                self._build_soft_preferences(
                    soft,
                    disliked_course_ids=[
                        item
                        for item in soft.disliked_course_ids
                        if item != normalized_course_id
                    ],
                ),
            )

        return self._save_constraints(session_id, mutate)

    def set_compact_schedule_preference(
        self,
        session_id: str,
        value: bool,
    ) -> PlanuSessionState:
        return self._save_constraints(
            session_id,
            lambda hard, soft: (
                hard,
                self._build_soft_preferences(soft, compact_schedule=value),
            ),
        )

    def clear_compact_schedule_preference(self, session_id: str) -> PlanuSessionState:
        return self._save_constraints(
            session_id,
            lambda hard, soft: (
                hard,
                self._build_soft_preferences(soft, compact_schedule=None),
            ),
        )

    def clear_hard_constraints(self, session_id: str) -> PlanuSessionState:
        return self._save_constraints(
            session_id,
            lambda _hard, soft: (HardConstraints(), soft),
        )

    def clear_soft_preferences(self, session_id: str) -> PlanuSessionState:
        return self._save_constraints(
            session_id,
            lambda hard, _soft: (hard, SoftPreferences()),
        )

    def clear_all_preferences(self, session_id: str) -> PlanuSessionState:
        return self._save_constraints(
            session_id,
            lambda _hard, _soft: (HardConstraints(), SoftPreferences()),
        )

    def update_preferences(
        self,
        session_id: str,
        *,
        hard_patch: HardConstraintsUpdate | None = None,
        soft_patch: SoftPreferencesUpdate | None = None,
    ) -> PlanuSessionState:
        """Apply Hard and Soft preference patches in one session save.

        Hard constraints have priority over Soft preferences when both are
        supplied in the same patch. Final cross-constraint validation still runs
        before persistence.
        """

        state = self.get_session(session_id)
        hard_constraints = state.hard_constraints
        soft_preferences = state.soft_preferences

        if hard_patch is not None:
            hard_constraints = self._apply_hard_patch(hard_constraints, hard_patch)
        if soft_patch is not None:
            soft_preferences = self._apply_soft_patch(soft_preferences, soft_patch)
        soft_preferences = self._apply_hard_priority(hard_constraints, soft_preferences)
        self._validate_cross_constraints(hard_constraints, soft_preferences)
        if (
            hard_constraints == state.hard_constraints
            and soft_preferences == state.soft_preferences
        ):
            return self._refresh_unchanged_state(state)
        return self._save_changed_state(
            state,
            {
                "hard_constraints": hard_constraints,
                "soft_preferences": soft_preferences,
            },
        )

    def select_timetable_candidate(
        self,
        session_id: str,
        candidate: GeneratedTimetableCandidate,
    ) -> PlanuSessionState:
        """Persist an explicitly selected generated timetable candidate."""

        if not candidate.candidate_id.strip():
            raise InvalidSessionStateValueError("candidate_id", candidate.candidate_id)
        if not candidate.section_ids:
            raise InvalidSessionStateValueError(
                "section_ids",
                candidate.section_ids,
                "selected timetable must contain at least one section",
            )
        if not candidate.validation.valid:
            raise InvalidSessionStateValueError(
                "candidate",
                candidate.candidate_id,
                "candidate must pass hard validation before selection",
            )
        if candidate.section_sources:
            expected_candidate_id = GeneratedTimetableCandidate.build_source_id(
                candidate.section_sources
            )
        else:
            expected_candidate_id = GeneratedTimetableCandidate.build_id(candidate.section_ids)
        if expected_candidate_id != candidate.candidate_id:
            raise InvalidSessionStateValueError(
                "candidate_id",
                candidate.candidate_id,
                "candidate_id does not match the supplied section combination",
            )

        state = self.get_session(session_id)
        current = state.selected_timetable
        if (
            current is not None
            and current.candidate_id == candidate.candidate_id
            and current.section_ids == candidate.section_ids
        ):
            return self._refresh_unchanged_state(state)

        now = self._now()
        selected = SelectedTimetable(
            candidate_id=candidate.candidate_id,
            section_ids=list(candidate.section_ids),
            fixed_section_ids=list(candidate.fixed_section_ids),
            added_section_ids=list(candidate.added_section_ids),
            course_ids=list(candidate.course_ids),
            section_sources=list(candidate.section_sources),
            fixed_section_sources=list(candidate.fixed_section_sources),
            added_section_sources=list(candidate.added_section_sources),
            total_credits=candidate.total_credits,
            selected_at=now,
        )
        return self._save_changed_state(
            state,
            {
                "selected_timetable": selected,
                "selected_timetable_status": SelectedTimetableStatus.CURRENT,
            },
        )

    def get_selected_timetable(self, session_id: str) -> SelectedTimetable:
        """Return the current selected timetable or raise a clear service error."""

        state = self.get_session(session_id)
        if state.selected_timetable is None:
            raise InvalidSessionStateValueError(
                "selected_timetable",
                None,
                "no timetable candidate has been selected",
            )
        return state.selected_timetable.model_copy(deep=True)

    def confirm_generation_preferences(self, session_id: str) -> PlanuSessionState:
        """Persist confirmation that the current condition revision may generate timetables."""

        state = self.get_session(session_id)
        if (
            state.generation_preferences_confirmed_at is not None
            and state.generation_preferences_confirmed_version == state.version
        ):
            return self._refresh_unchanged_state(state)
        now = self._now()
        return self._save_changed_state(
            state,
            {
                "generation_preferences_confirmed_at": now,
                "generation_preferences_confirmed_version": state.version,
            },
        )

    def clear_selected_timetable(self, session_id: str) -> PlanuSessionState:
        """Clear selected timetable state without touching preferences or catalogs."""

        state = self.get_session(session_id)
        if state.selected_timetable is None and state.selected_timetable_status is None:
            return self._refresh_unchanged_state(state)
        return self._save_changed_state(
            state,
            {
                "selected_timetable": None,
                "selected_timetable_status": None,
            },
        )

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
        update = self._mark_selected_timetable_stale_if_needed(state, dict(update))
        update = self._invalidate_generation_confirmation_if_needed(state, update)
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

    @staticmethod
    def _mark_selected_timetable_stale_if_needed(
        state: PlanuSessionState,
        update: dict[str, object],
    ) -> dict[str, object]:
        if state.selected_timetable is None or "selected_timetable" in update:
            return update
        stale_fields = {
            "department",
            "major_catalog_id",
            "elective_catalog_id",
            "selected_major_course_ids",
        }
        should_stale = any(
            field_name in update and update[field_name] != getattr(state, field_name)
            for field_name in stale_fields
        )
        if "hard_constraints" in update and update["hard_constraints"] != state.hard_constraints:
            should_stale = True
        if should_stale:
            update["selected_timetable_status"] = SelectedTimetableStatus.STALE
        return update

    @staticmethod
    def _invalidate_generation_confirmation_if_needed(
        state: PlanuSessionState,
        update: dict[str, object],
    ) -> dict[str, object]:
        if state.generation_preferences_confirmed_at is None:
            return update
        if "generation_preferences_confirmed_at" in update:
            return update
        confirmation_fields = {
            "department",
            "major_catalog_id",
            "elective_catalog_id",
            "selected_major_course_ids",
            "hard_constraints",
            "soft_preferences",
        }
        should_invalidate = any(
            field_name in update and update[field_name] != getattr(state, field_name)
            for field_name in confirmation_fields
        )
        if should_invalidate:
            update["generation_preferences_confirmed_at"] = None
            update["generation_preferences_confirmed_version"] = None
        return update

    def _save_state_with_courses(
        self,
        state: PlanuSessionState,
        selected_major_course_ids: list[str],
    ) -> PlanuSessionState:
        return self._save_changed_state(
            state,
            {"selected_major_course_ids": selected_major_course_ids},
        )

    def _save_state_with_courses_if_changed(
        self,
        state: PlanuSessionState,
        selected_major_course_ids: list[str],
    ) -> PlanuSessionState:
        if selected_major_course_ids == state.selected_major_course_ids:
            return self._refresh_unchanged_state(state)
        return self._save_state_with_courses(state, selected_major_course_ids)

    def _save_state_update_if_changed(
        self,
        state: PlanuSessionState,
        update: dict[str, object],
    ) -> PlanuSessionState:
        changed = {
            field_name: value
            for field_name, value in update.items()
            if getattr(state, field_name) != value
        }
        if not changed:
            return self._refresh_unchanged_state(state)
        return self._save_changed_state(state, changed)

    def _save_constraints(
        self,
        session_id: str,
        mutate: Callable[
            [HardConstraints, SoftPreferences],
            tuple[HardConstraints, SoftPreferences],
        ],
    ) -> PlanuSessionState:
        state = self.get_session(session_id)
        hard_constraints, soft_preferences = mutate(
            state.hard_constraints,
            state.soft_preferences,
        )
        self._validate_cross_constraints(hard_constraints, soft_preferences)
        if (
            hard_constraints == state.hard_constraints
            and soft_preferences == state.soft_preferences
        ):
            return self._refresh_unchanged_state(state)
        return self._save_changed_state(
            state,
            {
                "hard_constraints": hard_constraints,
                "soft_preferences": soft_preferences,
            },
        )

    def _set_hard_time(
        self,
        session_id: str,
        field_name: str,
        value: str | None,
    ) -> PlanuSessionState:
        return self._save_constraints(
            session_id,
            lambda hard, soft: (
                self._build_hard_constraints(hard, **{field_name: value}),
                soft,
            ),
        )

    def _set_soft_time(
        self,
        session_id: str,
        field_name: str,
        value: str | None,
    ) -> PlanuSessionState:
        return self._save_constraints(
            session_id,
            lambda hard, soft: (
                hard,
                self._build_soft_preferences(soft, **{field_name: value}),
            ),
        )

    def _apply_hard_patch(
        self,
        hard_constraints: HardConstraints,
        patch: HardConstraintsUpdate,
    ) -> HardConstraints:
        update: dict[str, object] = {}
        for field_name in patch.clear_fields:
            update[field_name] = self._cleared_preference_value(field_name)
        if patch.required_free_days is not None:
            update["required_free_days"] = self._normalize_days(
                "required_free_days",
                patch.required_free_days,
            )
        if patch.earliest_start_time is not None:
            update["earliest_start_time"] = self._normalize_time(
                "earliest_start_time",
                patch.earliest_start_time,
            )
        if patch.latest_end_time is not None:
            update["latest_end_time"] = self._normalize_time(
                "latest_end_time",
                patch.latest_end_time,
            )
        if patch.required_course_ids is not None:
            update["required_course_ids"] = self._normalize_course_ids(
                patch.required_course_ids,
                field_name="required_course_ids",
            )
        if patch.excluded_course_ids is not None:
            update["excluded_course_ids"] = self._normalize_course_ids(
                patch.excluded_course_ids,
                field_name="excluded_course_ids",
            )
        excluded_elective_areas = getattr(patch, "excluded_elective_areas", None)
        if excluded_elective_areas is not None:
            update["excluded_elective_areas"] = self._normalize_elective_areas(
                "excluded_elective_areas",
                excluded_elective_areas,
            )
        min_credit = getattr(patch, "min_credit", None)
        min_credit_inclusive = getattr(patch, "min_credit_inclusive", None)
        max_credit = getattr(patch, "max_credit", None)
        max_credit_inclusive = getattr(patch, "max_credit_inclusive", None)
        if min_credit is not None:
            update["min_credit"] = min_credit
            update["min_credit_inclusive"] = True if min_credit_inclusive is None else min_credit_inclusive
        elif min_credit_inclusive is not None and hard_constraints.min_credit is not None:
            update["min_credit_inclusive"] = min_credit_inclusive
        if max_credit is not None:
            update["max_credit"] = max_credit
            update["max_credit_inclusive"] = True if max_credit_inclusive is None else max_credit_inclusive
        elif max_credit_inclusive is not None and hard_constraints.max_credit is not None:
            update["max_credit_inclusive"] = max_credit_inclusive
        if "required_course_ids" in update and "excluded_course_ids" not in update:
            required = set(update["required_course_ids"])
            update["excluded_course_ids"] = [
                course_id
                for course_id in hard_constraints.excluded_course_ids
                if course_id not in required
            ]
        if "excluded_course_ids" in update and "required_course_ids" not in update:
            excluded = set(update["excluded_course_ids"])
            update["required_course_ids"] = [
                course_id
                for course_id in hard_constraints.required_course_ids
                if course_id not in excluded
            ]
        return self._build_hard_constraints(hard_constraints, **update)

    def _apply_soft_patch(
        self,
        soft_preferences: SoftPreferences,
        patch: SoftPreferencesUpdate,
    ) -> SoftPreferences:
        update: dict[str, object] = {}
        for field_name in patch.clear_fields:
            update[field_name] = self._cleared_preference_value(field_name)
        if patch.preferred_free_days is not None:
            update["preferred_free_days"] = self._normalize_days(
                "preferred_free_days",
                patch.preferred_free_days,
            )
        if patch.preferred_earliest_start_time is not None:
            update["preferred_earliest_start_time"] = self._normalize_time(
                "preferred_earliest_start_time",
                patch.preferred_earliest_start_time,
            )
        if patch.preferred_latest_end_time is not None:
            update["preferred_latest_end_time"] = self._normalize_time(
                "preferred_latest_end_time",
                patch.preferred_latest_end_time,
            )
        if patch.preferred_course_ids is not None:
            update["preferred_course_ids"] = self._normalize_course_ids(
                patch.preferred_course_ids,
                field_name="preferred_course_ids",
            )
        if patch.disliked_course_ids is not None:
            update["disliked_course_ids"] = self._normalize_course_ids(
                patch.disliked_course_ids,
                field_name="disliked_course_ids",
            )
        if patch.compact_schedule is not None:
            update["compact_schedule"] = patch.compact_schedule
        return self._build_soft_preferences(soft_preferences, **update)

    def _apply_hard_priority(
        self,
        hard_constraints: HardConstraints,
        soft_preferences: SoftPreferences,
    ) -> SoftPreferences:
        required_days = set(hard_constraints.required_free_days)
        required_courses = set(hard_constraints.required_course_ids)
        excluded_courses = set(hard_constraints.excluded_course_ids)
        hard_courses = required_courses | excluded_courses
        return self._build_soft_preferences(
            soft_preferences,
            preferred_free_days=[
                day
                for day in soft_preferences.preferred_free_days
                if day not in required_days
            ],
            preferred_course_ids=[
                course_id
                for course_id in soft_preferences.preferred_course_ids
                if course_id not in hard_courses
            ],
            disliked_course_ids=[
                course_id
                for course_id in soft_preferences.disliked_course_ids
                if course_id not in hard_courses
            ],
        )

    @staticmethod
    def _cleared_preference_value(field_name: str) -> object:
        if field_name.endswith("_ids") or field_name.endswith("_days") or field_name.endswith("_areas"):
            return []
        if field_name.endswith("_inclusive"):
            return True
        return None

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

    @staticmethod
    def _build_hard_constraints(
        hard_constraints: HardConstraints,
        **update: object,
    ) -> HardConstraints:
        return SessionStateBuilder.hard_constraints(hard_constraints, **update)

    @staticmethod
    def _build_soft_preferences(
        soft_preferences: SoftPreferences,
        **update: object,
    ) -> SoftPreferences:
        return SessionStateBuilder.soft_preferences(soft_preferences, **update)

    @staticmethod
    def _validate_cross_constraints(
        hard_constraints: HardConstraints,
        soft_preferences: SoftPreferences,
    ) -> None:
        PreferenceConflictValidator.validate(hard_constraints, soft_preferences)

    def _now(self) -> datetime:
        now = self._now_provider()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("now_provider must return timezone-aware datetime")
        return now

    @staticmethod
    def _require_non_empty(field_name: str, value: str) -> str:
        return SessionInputNormalizer.require_non_empty(field_name, value)

    @classmethod
    def _normalize_course_ids(
        cls,
        course_ids: Iterable[str],
        *,
        field_name: str = "selected_major_course_ids",
    ) -> list[str]:
        return SessionInputNormalizer.course_ids(course_ids, field_name=field_name)

    @staticmethod
    def _normalize_day(field_name: str, day: Day | str) -> Day:
        return SessionInputNormalizer.day(field_name, day)

    @classmethod
    def _normalize_days(
        cls,
        field_name: str,
        days: Iterable[Day | str],
    ) -> list[Day]:
        return SessionInputNormalizer.days(field_name, days)

    @staticmethod
    def _normalize_time(field_name: str, time_value: str) -> str:
        return SessionInputNormalizer.time(field_name, time_value)

    @staticmethod
    def _normalize_elective_areas(field_name: str, areas: Iterable[int]) -> list[int]:
        values: list[int] = []
        for area in areas:
            if not isinstance(area, int):
                raise SessionValidationError(field_name, area, "elective area must be an integer")
            if not 1 <= area <= 9:
                raise SessionValidationError(field_name, str(area), "elective areas must be between 1 and 9")
            values.append(area)
        return list(dict.fromkeys(values))



