"""Structured models for agent-callable timetable generation tools."""

from __future__ import annotations

from enum import Enum
from hashlib import sha256

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .course import Day, time_to_minutes
from .course_discovery import CourseSection


class GenerationFailureCode(str, Enum):
    FIXED_TIMETABLE_CONFLICT = "FIXED_TIMETABLE_CONFLICT"
    REQUIRED_COURSE_UNAVAILABLE = "REQUIRED_COURSE_UNAVAILABLE"
    TIME_CONFLICT = "TIME_CONFLICT"
    DUPLICATE_COURSE = "DUPLICATE_COURSE"
    REQUIRED_FREE_DAY_VIOLATION = "REQUIRED_FREE_DAY_VIOLATION"
    EARLIEST_START_VIOLATION = "EARLIEST_START_VIOLATION"
    LATEST_END_VIOLATION = "LATEST_END_VIOLATION"
    DEPARTMENT_INELIGIBLE = "DEPARTMENT_INELIGIBLE"
    CAMPUS_MOVEMENT_VIOLATION = "CAMPUS_MOVEMENT_VIOLATION"
    INSUFFICIENT_CANDIDATE_COURSES = "INSUFFICIENT_CANDIDATE_COURSES"
    TARGET_COURSE_COUNT_UNREACHABLE = "TARGET_COURSE_COUNT_UNREACHABLE"
    TARGET_CREDITS_UNREACHABLE = "TARGET_CREDITS_UNREACHABLE"
    SEARCH_LIMIT_REACHED = "SEARCH_LIMIT_REACHED"
    INVALID_GENERATION_REQUEST = "INVALID_GENERATION_REQUEST"
    TIMETABLE_GENERATION_NOT_READY = "TIMETABLE_GENERATION_NOT_READY"
    TIMETABLE_CONDITIONS_NOT_CONFIRMED = "TIMETABLE_CONDITIONS_NOT_CONFIRMED"


class TimetableViolationCode(str, Enum):
    INVALID_VALIDATION_REQUEST = "INVALID_VALIDATION_REQUEST"
    TIME_CONFLICT = "TIME_CONFLICT"
    DUPLICATE_COURSE = "DUPLICATE_COURSE"
    MISSING_REQUIRED_COURSE = "MISSING_REQUIRED_COURSE"
    EXCLUDED_COURSE_INCLUDED = "EXCLUDED_COURSE_INCLUDED"
    REQUIRED_FREE_DAY_VIOLATION = "REQUIRED_FREE_DAY_VIOLATION"
    EARLIEST_START_VIOLATION = "EARLIEST_START_VIOLATION"
    LATEST_END_VIOLATION = "LATEST_END_VIOLATION"
    DEPARTMENT_INELIGIBLE = "DEPARTMENT_INELIGIBLE"
    CAMPUS_MOVEMENT_VIOLATION = "CAMPUS_MOVEMENT_VIOLATION"


class SearchTerminationReason(str, Enum):
    SEARCH_EXHAUSTED = "SEARCH_EXHAUSTED"
    MAX_RESULTS_REACHED = "MAX_RESULTS_REACHED"
    MAX_SEARCH_NODES_REACHED = "MAX_SEARCH_NODES_REACHED"


class _Model(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )


class SectionSource(_Model):
    """A concrete schedulable section and the catalog that owns it."""

    catalog_id: str = Field(min_length=1)
    section_id: str = Field(min_length=1)

    @property
    def key(self) -> str:
        return f"{self.catalog_id}:{self.section_id}"


class ResolvedSection(_Model):
    """A schedulable section resolved from a catalog-aware source."""

    catalog_id: str = Field(min_length=1)
    section: CourseSection

    @property
    def source(self) -> SectionSource:
        return SectionSource(
            catalog_id=self.catalog_id,
            section_id=self.section.section_id,
        )

    @property
    def source_key(self) -> str:
        return self.source.key


class TimetableGenerationRequest(_Model):
    """Prepared, deterministic request for timetable candidate generation.

    ``target_additional_course_count`` and ``target_additional_credits`` are
    both hard targets when supplied: a returned candidate must satisfy both.
    """

    session_id: str | None = Field(default=None, min_length=1)
    fixed_section_sources: list[SectionSource] = Field(default_factory=list)
    candidate_course_ids: list[str] = Field(default_factory=list)
    candidate_section_sources_by_course: dict[str, list[SectionSource]] = Field(
        default_factory=dict
    )
    required_course_ids: list[str] = Field(default_factory=list)
    excluded_course_ids: list[str] = Field(default_factory=list)
    required_free_days: list[Day] = Field(default_factory=list)
    earliest_start_time: str | None = None
    latest_end_time: str | None = None
    department: str | None = None
    target_additional_course_count: int | None = Field(default=1, ge=0)
    target_additional_credits: float | None = Field(default=None, ge=0)
    max_results: int = Field(default=3, ge=1)
    max_search_nodes: int = Field(default=5000, ge=1)

    @field_validator(
        "candidate_course_ids",
        "required_course_ids",
        "excluded_course_ids",
    )
    @classmethod
    def dedupe_non_empty_text(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("id lists must not contain empty values")
        return list(dict.fromkeys(values))

    @field_validator("fixed_section_sources")
    @classmethod
    def dedupe_fixed_sources(cls, values: list[SectionSource]) -> list[SectionSource]:
        deduped: list[SectionSource] = []
        seen: set[tuple[str, str]] = set()
        for value in values:
            key = (value.catalog_id, value.section_id)
            if key not in seen:
                deduped.append(value)
                seen.add(key)
        return deduped

    @field_validator("earliest_start_time", "latest_end_time")
    @classmethod
    def validate_time(cls, value: str | None) -> str | None:
        if value is not None:
            time_to_minutes(value)
        return value

    @model_validator(mode="after")
    def validate_request_shape(self) -> "TimetableGenerationRequest":
        if (
            self.earliest_start_time is not None
            and self.latest_end_time is not None
            and time_to_minutes(self.earliest_start_time)
            > time_to_minutes(self.latest_end_time)
        ):
            raise ValueError("earliest_start_time must be <= latest_end_time")

        course_ids = self.candidate_course_ids or sorted(
            self.candidate_section_sources_by_course
        )
        if self.candidate_course_ids and set(course_ids) != set(
            self.candidate_section_sources_by_course
        ):
            missing = set(course_ids) ^ set(self.candidate_section_sources_by_course)
            raise ValueError(
                "candidate_course_ids must match candidate_section_sources_by_course: "
                + ", ".join(sorted(missing))
            )

        section_owners: dict[tuple[str, str], str] = {}
        for course_id, sources in self.candidate_section_sources_by_course.items():
            if not course_id.strip():
                raise ValueError("candidate course id must not be empty")
            if not sources:
                raise ValueError("candidate course section lists must not be empty")
            for source in sources:
                key = (source.catalog_id, source.section_id)
                owner = section_owners.get(key)
                if owner is not None and owner != course_id:
                    raise ValueError("one section source cannot appear under multiple courses")
                section_owners[key] = course_id

        overlap = set(self.required_course_ids) & set(self.excluded_course_ids)
        if overlap:
            raise ValueError(
                "course ids cannot be both required and excluded: "
                + ", ".join(sorted(overlap))
            )
        return self

    @property
    def candidate_course_ids_for_search(self) -> list[str]:
        """Return a stable search order seed, not the caller's input order."""

        if self.candidate_course_ids:
            return sorted(self.candidate_course_ids)
        return sorted(self.candidate_section_sources_by_course)

    @property
    def ordered_candidate_course_ids(self) -> list[str]:
        """Deprecated alias; this does not preserve caller input order."""

        return self.candidate_course_ids_for_search


class TimetableValidationRequest(_Model):
    section_sources: list[SectionSource] = Field(min_length=1)
    required_course_ids: list[str] = Field(default_factory=list)
    excluded_course_ids: list[str] = Field(default_factory=list)
    required_free_days: list[Day] = Field(default_factory=list)
    earliest_start_time: str | None = None
    latest_end_time: str | None = None
    department: str | None = None

    @field_validator("required_course_ids", "excluded_course_ids")
    @classmethod
    def dedupe_ids(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("course id lists must not contain empty values")
        return list(dict.fromkeys(values))

    @field_validator("section_sources")
    @classmethod
    def dedupe_sources(cls, values: list[SectionSource]) -> list[SectionSource]:
        deduped: list[SectionSource] = []
        seen: set[tuple[str, str]] = set()
        for value in values:
            key = (value.catalog_id, value.section_id)
            if key not in seen:
                deduped.append(value)
                seen.add(key)
        return deduped

    @field_validator("earliest_start_time", "latest_end_time")
    @classmethod
    def validate_time(cls, value: str | None) -> str | None:
        if value is not None:
            time_to_minutes(value)
        return value

    @model_validator(mode="after")
    def validate_time_window(self) -> "TimetableValidationRequest":
        if (
            self.earliest_start_time is not None
            and self.latest_end_time is not None
            and time_to_minutes(self.earliest_start_time)
            > time_to_minutes(self.latest_end_time)
        ):
            raise ValueError("earliest_start_time must be <= latest_end_time")
        return self


class TimetableViolation(_Model):
    code: TimetableViolationCode
    message: str = Field(min_length=1)
    course_id: str | None = None
    section_id: str | None = None
    conflicting_section_ids: list[str] = Field(default_factory=list)
    constraint: str | None = None


class TimetableValidationResult(_Model):
    valid: bool
    violations: list[TimetableViolation] = Field(default_factory=list)
    checked_section_ids: list[str] = Field(default_factory=list)
    checked_section_sources: list[SectionSource] = Field(default_factory=list)


class GenerationFailureReason(_Model):
    code: GenerationFailureCode
    message: str = Field(min_length=1)
    course_id: str | None = None
    section_id: str | None = None
    conflicting_section_ids: list[str] = Field(default_factory=list)
    constraint: str | None = None
    count: int = Field(default=1, ge=1)


class GeneratedTimetableCandidate(_Model):
    candidate_id: str = Field(min_length=1)
    section_ids: list[str]
    section_sources: list[SectionSource] = Field(default_factory=list)
    fixed_section_ids: list[str]
    session_id: str | None = Field(default=None, min_length=1)
    fixed_section_sources: list[SectionSource] = Field(default_factory=list)
    added_section_ids: list[str]
    added_section_sources: list[SectionSource] = Field(default_factory=list)
    course_ids: list[str]
    total_credits: float = Field(ge=0)
    validation: TimetableValidationResult
    generation_order: int = Field(ge=1)

    @classmethod
    def build_id(cls, section_ids: list[str]) -> str:
        digest = sha256("\n".join(sorted(section_ids)).encode("utf-8")).hexdigest()
        return f"tt-{digest[:16]}"

    @classmethod
    def build_source_id(cls, section_sources: list[SectionSource]) -> str:
        digest = sha256(
            "\n".join(sorted(source.key for source in section_sources)).encode("utf-8")
        ).hexdigest()
        return f"tt-{digest[:16]}"


class TimetableGenerationError(_Model):
    code: GenerationFailureCode
    message: str = Field(min_length=1)


class TimetableGenerationResult(_Model):
    success: bool
    candidates: list[GeneratedTimetableCandidate] = Field(default_factory=list)
    total_candidates_found: int = Field(default=0, ge=0)
    search_nodes_visited: int = Field(default=0, ge=0)
    search_truncated: bool = False
    termination_reason: SearchTerminationReason = SearchTerminationReason.SEARCH_EXHAUSTED
    failure_reasons: list[GenerationFailureReason] = Field(default_factory=list)
    search_diagnostics: list[GenerationFailureReason] = Field(default_factory=list)
    message: str
    error: TimetableGenerationError | None = None
