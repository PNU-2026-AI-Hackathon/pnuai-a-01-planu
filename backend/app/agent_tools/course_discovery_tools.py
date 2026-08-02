"""Framework-independent catalog discovery tools for future PlaNU agents."""

from __future__ import annotations

from collections.abc import Mapping

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ..models.course_discovery import (
    CourseDiscoveryRequest,
    CourseDiscoveryResult,
    CourseSectionsResult,
    DiscoveryResolution,
    DiscoveryToolError,
    DiscoveryToolErrorCode,
    SectionDetailsResult,
)
from ..repositories.exceptions import (
    CatalogNotFoundError,
    CourseNotFoundError,
    SectionNotFoundError,
)
from ..services.course_discovery_service import CourseDiscoveryService


class _ToolInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )


class SearchCoursesByNameInput(_ToolInput):
    catalog_id: str = Field(min_length=1)
    query: str = Field(min_length=1)
    limit: int = Field(default=20, ge=1, le=50)


class CourseSectionsInput(_ToolInput):
    catalog_id: str = Field(min_length=1)
    course_id: str = Field(min_length=1)
    section_ids: list[str] | None = Field(
        default=None,
        description="Optional section ids from a prior candidate to return only matching sections.",
    )


class SectionDetailsInput(_ToolInput):
    catalog_id: str = Field(min_length=1)
    section_id: str = Field(min_length=1)


class CourseDiscoveryTools:
    """Thin adapters over ``CourseDiscoveryService`` for agent tool calls."""

    def __init__(self, service: CourseDiscoveryService) -> None:
        self._service = service

    def discover_courses(
        self,
        data: CourseDiscoveryRequest | Mapping[str, object],
    ) -> CourseDiscoveryResult:
        """Find course candidates from structured catalog conditions.

        Use when the user's resolved conditions should be applied to a course
        catalog. Supports both optional name/code search and condition-only
        browsing. Results are grouped by course and include matching section
        ids. This tool does not save results to a session, mutate state, build a
        timetable, or check conflicts against other courses.
        """

        try:
            request = CourseDiscoveryRequest.model_validate(data)
            return self._service.discover(request)
        except ValidationError as exc:
            return _invalid_discovery_result(data, exc)
        except Exception as exc:
            return _discovery_error_result(data, exc)

    def search_courses_by_name(
        self,
        data: SearchCoursesByNameInput | Mapping[str, object],
    ) -> CourseDiscoveryResult:
        """Search explicitly for a course name, course id, or course code.

        Use after an agent has identified a specific course mention such as
        "컴퓨터프로그래밍" or "CSE101". Ambiguous matches are returned as
        multiple course candidates and are not automatically confirmed.
        """

        try:
            request = SearchCoursesByNameInput.model_validate(data)
            return self._service.search_by_name(
                catalog_id=request.catalog_id,
                query=request.query,
                limit=request.limit,
            )
        except ValidationError as exc:
            fallback = CourseDiscoveryRequest(catalog_id=_catalog_id(data), limit=1)
            return CourseDiscoveryResult(
                success=False,
                catalog_id=fallback.catalog_id,
                request=fallback,
                candidates=[],
                resolution=DiscoveryResolution.NOT_FOUND,
                total_scanned_courses=0,
                total_matched_courses=0,
                message=str(exc.errors()[0]["msg"]),
                error=DiscoveryToolError(
                    code=DiscoveryToolErrorCode.INVALID_DISCOVERY_REQUEST,
                    message=str(exc.errors()[0]["msg"]),
                    field=".".join(str(part) for part in exc.errors()[0]["loc"]),
                ),
            )
        except Exception as exc:
            fallback = CourseDiscoveryRequest(
                catalog_id=_catalog_id(data),
                query=_optional_text(data, "query"),
                limit=1,
            )
            return _error_discovery_envelope(fallback, exc)

    def get_course_sections(
        self,
        data: CourseSectionsInput | Mapping[str, object],
    ) -> CourseSectionsResult:
        """Return sections for a course id.

        Pass ``section_ids`` from a previous discovery candidate to inspect only
        the sections that matched that candidate's conditions.
        """

        try:
            request = CourseSectionsInput.model_validate(data)
            sections = self._service.get_course_sections(
                catalog_id=request.catalog_id,
                course_id=request.course_id,
                section_ids=request.section_ids,
            )
            return CourseSectionsResult(
                success=True,
                catalog_id=request.catalog_id,
                course_id=request.course_id,
                sections=sections,
                message=f"{len(sections)}개 분반을 조회했습니다.",
                error=None,
            )
        except ValidationError as exc:
            return _sections_validation_error(data, exc)
        except Exception as exc:
            return _sections_error_result(data, exc)

    def get_section_details(
        self,
        data: SectionDetailsInput | Mapping[str, object],
    ) -> SectionDetailsResult:
        """Return one section's details by concrete section id."""

        try:
            request = SectionDetailsInput.model_validate(data)
            section = self._service.get_section_details(
                catalog_id=request.catalog_id,
                section_id=request.section_id,
            )
            return SectionDetailsResult(
                success=True,
                catalog_id=request.catalog_id,
                section_id=request.section_id,
                section=section,
                message="분반 상세 정보를 조회했습니다.",
                error=None,
            )
        except ValidationError as exc:
            return _section_validation_error(data, exc)
        except Exception as exc:
            return _section_error_result(data, exc)


def _invalid_discovery_result(
    data: CourseDiscoveryRequest | Mapping[str, object],
    exc: ValidationError,
) -> CourseDiscoveryResult:
    fallback = CourseDiscoveryRequest(catalog_id=_catalog_id(data), limit=1)
    return CourseDiscoveryResult(
        success=False,
        catalog_id=fallback.catalog_id,
        request=fallback,
        candidates=[],
        resolution=DiscoveryResolution.NOT_FOUND,
        total_scanned_courses=0,
        total_matched_courses=0,
        message=str(exc.errors()[0]["msg"]),
        error=DiscoveryToolError(
            code=DiscoveryToolErrorCode.INVALID_DISCOVERY_REQUEST,
            message=str(exc.errors()[0]["msg"]),
            field=".".join(str(part) for part in exc.errors()[0]["loc"]),
        ),
    )


def _discovery_error_result(
    data: CourseDiscoveryRequest | Mapping[str, object],
    exc: Exception,
) -> CourseDiscoveryResult:
    if isinstance(data, CourseDiscoveryRequest):
        request = data
    else:
        request = CourseDiscoveryRequest.model_validate(
            {**dict(data), "limit": min(int(dict(data).get("limit", 1) or 1), 50)}
        )
    return _error_discovery_envelope(request, exc)


def _error_discovery_envelope(
    request: CourseDiscoveryRequest,
    exc: Exception,
) -> CourseDiscoveryResult:
    error = _tool_error(exc)
    return CourseDiscoveryResult(
        success=False,
        catalog_id=request.catalog_id,
        request=request,
        candidates=[],
        resolution=DiscoveryResolution.NOT_FOUND,
        total_scanned_courses=0,
        total_matched_courses=0,
        message=error.message,
        error=error,
    )


def _sections_validation_error(
    data: CourseSectionsInput | Mapping[str, object],
    exc: ValidationError,
) -> CourseSectionsResult:
    error = DiscoveryToolError(
        code=DiscoveryToolErrorCode.INVALID_DISCOVERY_REQUEST,
        message=str(exc.errors()[0]["msg"]),
        field=".".join(str(part) for part in exc.errors()[0]["loc"]),
    )
    return CourseSectionsResult(
        success=False,
        catalog_id=_catalog_id(data),
        course_id=_optional_text(data, "course_id"),
        sections=[],
        message=error.message,
        error=error,
    )


def _sections_error_result(
    data: CourseSectionsInput | Mapping[str, object],
    exc: Exception,
) -> CourseSectionsResult:
    error = _tool_error(exc)
    return CourseSectionsResult(
        success=False,
        catalog_id=_catalog_id(data),
        course_id=_optional_text(data, "course_id"),
        sections=[],
        message=error.message,
        error=error,
    )


def _section_validation_error(
    data: SectionDetailsInput | Mapping[str, object],
    exc: ValidationError,
) -> SectionDetailsResult:
    error = DiscoveryToolError(
        code=DiscoveryToolErrorCode.INVALID_DISCOVERY_REQUEST,
        message=str(exc.errors()[0]["msg"]),
        field=".".join(str(part) for part in exc.errors()[0]["loc"]),
    )
    return SectionDetailsResult(
        success=False,
        catalog_id=_catalog_id(data),
        section_id=_optional_text(data, "section_id"),
        section=None,
        message=error.message,
        error=error,
    )


def _section_error_result(
    data: SectionDetailsInput | Mapping[str, object],
    exc: Exception,
) -> SectionDetailsResult:
    error = _tool_error(exc)
    return SectionDetailsResult(
        success=False,
        catalog_id=_catalog_id(data),
        section_id=_optional_text(data, "section_id"),
        section=None,
        message=error.message,
        error=error,
    )


def _tool_error(exc: Exception) -> DiscoveryToolError:
    if isinstance(exc, CatalogNotFoundError):
        return DiscoveryToolError(
            code=DiscoveryToolErrorCode.CATALOG_NOT_FOUND,
            message=str(exc),
            value=exc.catalog_id,
        )
    if isinstance(exc, CourseNotFoundError):
        return DiscoveryToolError(
            code=DiscoveryToolErrorCode.COURSE_NOT_FOUND,
            message=str(exc),
            value=exc.course_id,
        )
    if isinstance(exc, SectionNotFoundError):
        return DiscoveryToolError(
            code=DiscoveryToolErrorCode.SECTION_NOT_FOUND,
            message=str(exc),
            value=exc.section_id,
        )
    return DiscoveryToolError(
        code=DiscoveryToolErrorCode.INTERNAL_DISCOVERY_ERROR,
        message=str(exc),
    )


def _catalog_id(data: object) -> str:
    value = _optional_text(data, "catalog_id")
    return value or "unknown"


def _optional_text(data: object, field: str) -> str | None:
    if isinstance(data, BaseModel):
        value = getattr(data, field, None)
    elif isinstance(data, Mapping):
        value = data.get(field)
    else:
        value = None
    if value is None:
        return None
    return str(value)
