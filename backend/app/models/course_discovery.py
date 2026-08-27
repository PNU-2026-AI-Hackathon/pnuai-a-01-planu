"""Models for catalog registration and course discovery results."""

from __future__ import annotations

import re
import unicodedata
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .course import Category, ClassTime, Course, Day, time_to_minutes


class CatalogKind(str, Enum):
    """Catalog ownership/source buckets known to the discovery layer."""

    MAJOR = "MAJOR"
    ELECTIVE = "ELECTIVE"
    DEFAULT_ELECTIVE = "DEFAULT_ELECTIVE"


class DiscoveryResolution(str, Enum):
    """How a discovery request resolved."""

    EXACT = "EXACT"
    CANDIDATES = "CANDIDATES"
    AMBIGUOUS = "AMBIGUOUS"
    NOT_FOUND = "NOT_FOUND"


class CourseMatchType(str, Enum):
    """Stable match buckets used for sorting and agent explanations."""

    COURSE_ID_EXACT = "COURSE_ID_EXACT"
    COURSE_CODE_EXACT = "COURSE_CODE_EXACT"
    NAME_EXACT = "NAME_EXACT"
    NAME_PREFIX = "NAME_PREFIX"
    NAME_CONTAINS = "NAME_CONTAINS"
    NAME_SIMILAR = "NAME_SIMILAR"
    CONDITION = "CONDITION"


class DiscoveryToolErrorCode(str, Enum):
    """Stable errors returned by course discovery tools."""

    CATALOG_NOT_FOUND = "CATALOG_NOT_FOUND"
    COURSE_NOT_FOUND = "COURSE_NOT_FOUND"
    SECTION_NOT_FOUND = "SECTION_NOT_FOUND"
    INVALID_DISCOVERY_REQUEST = "INVALID_DISCOVERY_REQUEST"
    INTERNAL_DISCOVERY_ERROR = "INTERNAL_DISCOVERY_ERROR"


class _DiscoveryModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )


class CourseSection(_DiscoveryModel):
    """A schedulable section with explicit course-level and section-level ids."""

    section_id: str = Field(min_length=1)
    course_id: str = Field(min_length=1)
    course_code: str = Field(min_length=1)
    course_name: str = Field(min_length=1)
    category: Category
    area: int | None = Field(default=None, ge=1, le=9)
    department: str | None = None
    credit: float = Field(gt=0)
    division: str = Field(min_length=1)
    professor: str = Field(min_length=1)
    class_times: list[ClassTime] = Field(min_length=1)

    @classmethod
    def from_course(cls, course: Course, *, department: str | None = None) -> "CourseSection":
        """Create a discovery section without mutating the source ``Course``."""

        section_id = course.course_id
        course_code = derive_course_code(course)
        return cls(
            section_id=section_id,
            course_id=course_code,
            course_code=course_code,
            course_name=course.course_name,
            category=course.category,
            area=course.area,
            department=department,
            credit=course.credit,
            division=course.division,
            professor=course.professor,
            class_times=course.class_times,
        )


class CatalogRecord(_DiscoveryModel):
    """Parsed catalog data stored behind a catalog id."""

    catalog_id: str = Field(min_length=1)
    kind: CatalogKind
    sections: list[CourseSection]


class CourseDiscoveryRequest(_DiscoveryModel):
    """Structured criteria an agent can pass to the discovery service.

    ``query`` is optional, so the same model supports direct name/code search
    and condition-only catalog browsing. Empty criteria are allowed as a
    bounded browse request, capped by ``limit``.
    """

    catalog_id: str = Field(min_length=1)
    query: str | None = Field(default=None, min_length=1)
    category: Category | None = None
    area: int | None = Field(default=None, ge=1, le=9)
    department: str | None = Field(default=None, min_length=1)
    allowed_days: list[Day] = Field(default_factory=list)
    excluded_days: list[Day] = Field(default_factory=list)
    earliest_start_time: str | None = None
    latest_end_time: str | None = None
    included_course_ids: list[str] = Field(default_factory=list)
    excluded_course_ids: list[str] = Field(default_factory=list)
    limit: int = Field(default=20, ge=1, le=50)

    @field_validator("earliest_start_time", "latest_end_time")
    @classmethod
    def validate_time(cls, value: str | None) -> str | None:
        if value is not None:
            time_to_minutes(value)
        return value

    @field_validator("allowed_days", "excluded_days", "included_course_ids", "excluded_course_ids")
    @classmethod
    def dedupe_lists(cls, values: list[object]) -> list[object]:
        return list(dict.fromkeys(values))

    @model_validator(mode="after")
    def validate_time_window(self) -> "CourseDiscoveryRequest":
        if (
            self.earliest_start_time is not None
            and self.latest_end_time is not None
            and time_to_minutes(self.earliest_start_time) >= time_to_minutes(self.latest_end_time)
        ):
            raise ValueError("earliest_start_time must be earlier than latest_end_time")
        return self


class CourseCandidate(_DiscoveryModel):
    """Course-level candidate grouped from one or more matching sections."""

    course_id: str
    course_code: str
    course_name: str
    category: Category
    area: int | None = None
    department: str | None = None
    total_section_count: int
    matching_section_count: int
    matching_section_ids: list[str]
    match_reasons: list[str]
    match_type: CourseMatchType
    rank_score: int


class DiscoveryToolError(_DiscoveryModel):
    code: DiscoveryToolErrorCode
    message: str = Field(min_length=1)
    field: str | None = None
    value: str | None = None


class CourseDiscoveryResult(_DiscoveryModel):
    success: bool
    catalog_id: str
    request: CourseDiscoveryRequest
    candidates: list[CourseCandidate] = Field(default_factory=list)
    resolution: DiscoveryResolution
    total_scanned_courses: int
    total_matched_courses: int
    message: str
    error: DiscoveryToolError | None = None


class CourseSectionsResult(_DiscoveryModel):
    success: bool
    catalog_id: str
    course_id: str | None = None
    sections: list[CourseSection] = Field(default_factory=list)
    message: str
    error: DiscoveryToolError | None = None


class SectionDetailsResult(_DiscoveryModel):
    success: bool
    catalog_id: str
    section_id: str | None = None
    section: CourseSection | None = None
    message: str
    error: DiscoveryToolError | None = None


SectionFilterMode = Literal["all", "matching"]


def derive_course_code(course: Course) -> str:
    """Derive a stable course-level code from the existing section-shaped id."""

    raw_id = course.course_id.strip()
    division = course.division.strip()
    if division and raw_id.endswith(f"-{division}"):
        code = raw_id[: -(len(division) + 1)].strip()
        if code:
            return code
    if "-" in raw_id:
        code = raw_id.rsplit("-", 1)[0].strip()
        if code:
            return code
    return raw_id


def normalize_course_search_text(value: str) -> str:
    """Normalize course search text without erasing meaningful symbols."""

    text = unicodedata.normalize("NFKC", value).strip().casefold()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s*([()（）])\s*", r"\1", text)
    return text
