"""Build general-required/elective candidate pools before timetable generation."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import Enum
import os
from pathlib import Path
import re
from collections.abc import Iterable
from typing import Protocol

from fastapi import UploadFile

from ..core.errors import AppError
from ..models.course import Category, Course
from ..models.general_course_pool import (
    ExcludedCourseDiagnostic,
    GeneralCoursePoolResult,
    GeneralCoursePools,
)
from ..schemas.general_schema import GeneralPreparationResponse
from .major_catalog_upload_service import write_limited_upload_to_temp
from .exceptions import SessionNotAvailableError
from .session_service import SessionService
from .session_store import SessionNotFoundError, SessionStage, SessionStore, session_store
from .uploaded_catalog_parser import (
    MAX_UPLOAD_SIZE,
    UploadedCatalogError,
    UploadedCatalogParser,
)


FALLBACK_WARNING = "교양선택 수강편람이 업로드되지 않아 서버 기본 데이터를 사용했습니다."


class EligibilityStatus(str, Enum):
    ELIGIBLE = "eligible"
    NOT_ELIGIBLE = "not_eligible"
    NOT_RESTRICTED = "not_restricted"
    UNKNOWN_DEPARTMENT = "unknown_department"
    RULE_NOT_FOUND = "rule_not_found"


@dataclass(frozen=True, slots=True)
class EligibilityDecision:
    status: EligibilityStatus
    reason: str

    @property
    def allows_course(self) -> bool:
        return self.status in {
            EligibilityStatus.ELIGIBLE,
            EligibilityStatus.NOT_RESTRICTED,
        }


@dataclass(frozen=True, slots=True)
class DepartmentRestrictionRule:
    course_code: str
    division: str
    allowed_departments: frozenset[str]
    blocked_departments: frozenset[str]


class CourseRestrictionPolicy:
    """Evaluate department restrictions keyed by course code and division."""

    def __init__(
        self,
        *,
        rules: Iterable[DepartmentRestrictionRule] = (),
    ) -> None:
        rules_by_course_section: dict[tuple[str, str], DepartmentRestrictionRule] = {}
        for rule in rules:
            key = (
                _normalized(rule.course_code),
                _normalized(rule.division),
            )
            if key in rules_by_course_section:
                raise ValueError(f"duplicate restriction rule: {rule.course_code}-{rule.division}")
            rules_by_course_section[key] = rule
        self.rules_by_course_section = rules_by_course_section
        self.known_departments = frozenset(
            department
            for rule in rules_by_course_section.values()
            for department in [*rule.allowed_departments, *rule.blocked_departments]
        )

    def evaluate(self, course: Course, *, department: str) -> EligibilityDecision:
        department_name = department.strip()
        if not department_name:
            return EligibilityDecision(
                EligibilityStatus.UNKNOWN_DEPARTMENT,
                "사용자 학과 정보가 없습니다.",
            )

        if self.known_departments and department_name not in self.known_departments:
            return EligibilityDecision(
                EligibilityStatus.NOT_RESTRICTED,
                "제한 데이터에 없는 학과이므로 학과 제한을 적용하지 않습니다.",
            )

        rule = self.rules_by_course_section.get(_course_key(course))
        if rule is None and course.category is Category.GENERAL_REQUIRED:
            return EligibilityDecision(
                EligibilityStatus.RULE_NOT_FOUND,
                "교양필수 과목의 학과별 수강 제한 규칙을 찾지 못했습니다.",
            )
        if rule is None:
            return EligibilityDecision(
                EligibilityStatus.NOT_RESTRICTED,
                "해당 과목·분반에 제한 규칙이 없습니다.",
            )

        if rule.allowed_departments:
            if department_name in rule.allowed_departments:
                return EligibilityDecision(
                    EligibilityStatus.ELIGIBLE,
                    "현재 학과에서 수강 가능한 분반입니다.",
                )
            return EligibilityDecision(
                EligibilityStatus.NOT_ELIGIBLE,
                "현재 학과는 수강가능 학과 목록에 없습니다.",
            )

        if department_name in rule.blocked_departments:
            return EligibilityDecision(
                EligibilityStatus.NOT_ELIGIBLE,
                "현재 학과에서 수강할 수 없는 분반입니다.",
            )

        return EligibilityDecision(
            EligibilityStatus.ELIGIBLE,
            "현재 학과에서 수강 가능한 분반입니다.",
        )


class GeneralCoursePoolService:
    def __init__(self, *, restriction_policy: CourseRestrictionPolicy | None = None) -> None:
        self.restriction_policy = restriction_policy or CourseRestrictionPolicy()

    def build_pools(
        self,
        *,
        department: str,
        general_required_courses: Iterable[Course],
        uploaded_elective_courses: Iterable[Course] | None = None,
        fallback_elective_courses: Iterable[Course] | None = None,
    ) -> GeneralCoursePoolResult:
        if not department.strip():
            raise AppError("DEPARTMENT_NOT_FOUND", "사용자 학과 정보가 없습니다.", status_code=409)

        required_candidates = [
            course for course in general_required_courses if _is_jangjeon_course(course)
        ]
        if not required_candidates:
            raise AppError(
                "RESTRICTED_COURSE_DATA_NOT_FOUND",
                "교양필수 후보 데이터가 없습니다.",
                status_code=500,
            )

        uploaded = [
            course for course in (uploaded_elective_courses or []) if _is_jangjeon_course(course)
        ]
        fallback = [
            course for course in (fallback_elective_courses or []) if _is_jangjeon_course(course)
        ]
        result = GeneralCoursePoolResult()

        required = self._accept_courses(
            required_candidates,
            department=department,
            result=result,
            source="general_required_courses",
            allowed_categories={Category.GENERAL_REQUIRED},
        )

        if uploaded:
            elective_source = uploaded
            elective_source_name = "uploaded_elective_catalog"
        else:
            elective_source = fallback
            elective_source_name = "fallback_elective_catalog"
            if not fallback:
                result.warnings.append(
                    "업로드된 교양선택 수강편람이 없고 명시적인 fallback 교양선택 데이터도 없어 elective 후보를 비워 둡니다."
                )

        elective = self._accept_courses(
            elective_source,
            department=department,
            result=result,
            source=elective_source_name,
            allowed_categories={Category.GENERAL_ELECTIVE},
        )

        result.pools = GeneralCoursePools(
            required_courses=required,
            elective_courses=elective,
        )
        return result

    def _accept_courses(
        self,
        courses: Iterable[Course],
        *,
        department: str,
        result: GeneralCoursePoolResult,
        source: str,
        allowed_categories: set[Category],
    ) -> list[Course]:
        accepted: list[Course] = []
        seen: set[tuple[str, str]] = set()

        for course in courses:
            key = _course_key(course)
            if key in seen:
                result.excluded_courses.append(
                    _diagnostic(course, "DUPLICATE_COURSE", "동일 과목·분반이 이미 후보에 포함되어 제외했습니다.", source)
                )
                continue

            if course.category not in allowed_categories:
                result.excluded_courses.append(
                    _diagnostic(course, "UNSUPPORTED_CATEGORY", "추천 후보로 지원하지 않는 category입니다.", source)
                )
                continue

            decision = self.restriction_policy.evaluate(
                course,
                department=department,
            )
            if not decision.allows_course:
                result.excluded_courses.append(
                    _diagnostic(
                        course,
                        _reason_code(decision.status),
                        decision.reason,
                        source,
                    )
                )
                continue

            accepted.append(course)
            seen.add(key)

        return accepted


class ElectiveCatalogParserProtocol(Protocol):
    def parse_elective(self, path: str | Path, *, area: int | None = None) -> list[Course]:
        ...


class GeneralCoursePreparationService:
    def __init__(
        self,
        *,
        store: SessionStore = session_store,
        pool_service: GeneralCoursePoolService | None = None,
        general_required_courses: Iterable[Course] = (),
        fallback_elective_courses: Iterable[Course] | None = None,
        elective_parser: ElectiveCatalogParserProtocol | None = None,
        max_upload_size: int = MAX_UPLOAD_SIZE,
        session_service: SessionService | None = None,
    ) -> None:
        self.store = store
        self.pool_service = pool_service or GeneralCoursePoolService()
        self.general_required_courses = list(general_required_courses)
        self.fallback_elective_courses = (
            None if fallback_elective_courses is None else list(fallback_elective_courses)
        )
        self.elective_parser = elective_parser or UploadedCatalogParser()
        self.max_upload_size = max_upload_size
        self.session_service = session_service

    async def prepare_for_session(
        self,
        session_id: str,
        *,
        elective_catalog: UploadFile | None = None,
        elective_area: int | None = None,
    ) -> GeneralPreparationResponse:
        session_id = session_id.strip()
        if not session_id:
            raise AppError("SESSION_ID_REQUIRED", "session_id는 비어 있을 수 없습니다.", status_code=400)
        if elective_area is not None and not 1 <= elective_area <= 9:
            raise AppError(
                "INVALID_ELECTIVE_AREA",
                "교양 영역은 1~9 사이의 정수여야 합니다.",
                status_code=400,
            )

        has_upload = _has_upload(elective_catalog)
        if has_upload:
            self._validate_upload_name(elective_catalog)

        try:
            session = self.store.get(session_id)
        except SessionNotFoundError as exc:
            raise AppError(
                "SESSION_NOT_FOUND",
                "세션을 찾을 수 없거나 만료되었습니다.",
                status_code=404,
            ) from exc

        if (
            session.session_stage is SessionStage.GENERAL_READY
            and not has_upload
            and session.general_pool_elective_area == elective_area
        ):
            return _response_from_session(session)

        if session.session_stage not in {
            SessionStage.MAJOR_CONFIRMED,
            SessionStage.GENERAL_READY,
            SessionStage.CANDIDATES_GENERATED,
            SessionStage.RANKING_COMPLETED,
        }:
            raise AppError(
                "INVALID_SESSION_STAGE",
                "전공 시간표 확정 이후에만 교양 후보 풀을 생성할 수 있습니다.",
                status_code=409,
            )
        if not session.department.strip():
            raise AppError("DEPARTMENT_NOT_FOUND", "사용자 학과 정보가 없습니다.", status_code=409)

        uploaded_elective_courses: list[Course] | None = None
        data_source = "fallback_catalog"
        warnings: list[str] = []
        if has_upload:
            uploaded_elective_courses = await self._parse_uploaded_elective_catalog(
                elective_catalog,
                elective_area=elective_area,
            )
            if elective_area is not None:
                uploaded_elective_courses = _filter_electives_by_area(
                    uploaded_elective_courses,
                    elective_area=elective_area,
                )
            if not uploaded_elective_courses:
                raise AppError(
                    "EMPTY_ELECTIVE_CATALOG",
                    "선택한 교양 영역에 해당하는 업로드 교양선택 과목을 찾지 못했습니다.",
                    status_code=422,
                )
            data_source = "uploaded_catalog"
        else:
            warnings.append(FALLBACK_WARNING)

        fallback_elective_courses = self.fallback_elective_courses
        if not has_upload and fallback_elective_courses is None:
            fallback_elective_courses = session.elective_candidates
        if not has_upload and not fallback_elective_courses:
            raise AppError(
                "FALLBACK_ELECTIVE_DATA_NOT_FOUND",
                "서버 기본 교양선택 데이터가 준비되어 있지 않습니다.",
                status_code=500,
            )
        if not has_upload and elective_area is not None:
            fallback_elective_courses = _filter_electives_by_area(
                fallback_elective_courses,
                elective_area=elective_area,
            )
            if not fallback_elective_courses:
                raise AppError(
                    "FALLBACK_ELECTIVE_AREA_NOT_FOUND",
                    "선택한 교양 영역에 해당하는 서버 기본 교양선택 데이터가 없습니다.",
                    status_code=404,
                    details={"elective_area": elective_area},
                )

        try:
            result = self.pool_service.build_pools(
                department=session.department,
                general_required_courses=self.general_required_courses,
                uploaded_elective_courses=uploaded_elective_courses,
                fallback_elective_courses=fallback_elective_courses,
            )
        except AppError:
            raise
        except Exception as exc:
            raise AppError(
                "GENERAL_COURSE_POOL_BUILD_FAILED",
                "교양 후보 풀을 생성하지 못했습니다.",
                status_code=500,
            ) from exc
        result.warnings = [*warnings, *result.warnings]

        try:
            saved = self.store.update_general_course_pool(
                session.session_id,
                result,
                data_source=data_source,
                elective_area=elective_area,
            )
        except (TypeError, ValueError) as exc:
            raise AppError(
                "GENERAL_COURSE_POOL_SAVE_FAILED",
                "교양 후보 풀을 세션에 저장하지 못했습니다.",
                status_code=500,
            ) from exc
        self._register_general_catalog_id(saved.session_id)
        saved = self.store.get(saved.session_id, touch=False)
        return _response_from_session(saved)

    def _register_general_catalog_id(self, session_id: str) -> None:
        if self.session_service is None:
            return
        try:
            self.session_service.register_elective_catalog(session_id, f"{session_id}:general")
        except SessionNotAvailableError as exc:
            raise AppError(
                "SESSION_NOT_FOUND",
                "세션을 찾을 수 없거나 만료되었습니다.",
                status_code=404,
            ) from exc

    @staticmethod
    def _validate_upload_name(upload_file: UploadFile | None) -> None:
        filename = ((upload_file.filename if upload_file else None) or "").strip()
        if not filename:
            raise AppError(
                "INVALID_EXCEL_FILE",
                "유효한 .xlsx 파일이 아닙니다.",
                status_code=400,
            )
        if Path(filename).suffix.lower() != ".xlsx":
            raise AppError(
                "INVALID_FILE_EXTENSION",
                "교양선택 수강편람은 .xlsx 파일만 업로드할 수 있습니다.",
                status_code=400,
            )

    async def _parse_uploaded_elective_catalog(
        self,
        upload_file: UploadFile,
        *,
        elective_area: int | None,
    ) -> list[Course]:
        temp_path: Path | None = None
        try:
            temp_path = await write_limited_upload_to_temp(
                upload_file,
                suffix=".xlsx",
                prefix="planu-elective-catalog-",
                max_upload_size=self.max_upload_size,
            )
            try:
                courses = await asyncio.to_thread(
                    self.elective_parser.parse_elective,
                    temp_path,
                    area=elective_area,
                )
            except UploadedCatalogError as exc:
                raise _elective_catalog_app_error(exc) from exc
            except Exception as exc:
                raise AppError(
                    "ELECTIVE_CATALOG_PARSE_FAILED",
                    "교양선택 수강편람을 파싱하지 못했습니다.",
                    status_code=422,
                ) from exc
        finally:
            if temp_path is not None:
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass

        if not courses:
            raise AppError(
                "EMPTY_ELECTIVE_CATALOG",
                "시간 정보가 있는 교양선택 과목을 찾지 못했습니다.",
                status_code=422,
            )
        return courses


def _course_key(course: Course) -> tuple[str, str]:
    if course.course_id:
        code = course.course_id.rsplit("-", 1)[0]
    else:
        code = _normalized(course.course_name)
    return (_normalized(code), _normalized(course.division))


def _normalized(value: str) -> str:
    return re.sub(r"\s+", "", value).casefold()


def _is_jangjeon_course(course: Course) -> bool:
    """Return false for sections explicitly marked as Miryang or Yangsan."""
    for meeting in course.class_times:
        classroom = meeting.classroom.strip().lower()
        building = meeting.building_code.strip().lower()
        if classroom.startswith(("밀양", "양산")) or building.startswith(("m", "y")):
            return False
    return True


def _diagnostic(course: Course, reason_code: str, reason: str, source: str) -> ExcludedCourseDiagnostic:
    return ExcludedCourseDiagnostic(
        course_key=course.course_id,
        course_name=course.course_name,
        section=course.division,
        reason_code=reason_code,
        reason=reason,
        source=source,
    )


def _reason_code(status: EligibilityStatus) -> str:
    return {
        EligibilityStatus.NOT_ELIGIBLE: "DEPARTMENT_NOT_ELIGIBLE",
        EligibilityStatus.UNKNOWN_DEPARTMENT: "UNKNOWN_DEPARTMENT",
        EligibilityStatus.RULE_NOT_FOUND: "RESTRICTION_RULE_NOT_FOUND",
        EligibilityStatus.ELIGIBLE: "ELIGIBLE",
        EligibilityStatus.NOT_RESTRICTED: "NOT_RESTRICTED",
    }[status]


def _filter_electives_by_area(
    courses: Iterable[Course],
    *,
    elective_area: int,
) -> list[Course]:
    return [
        course
        for course in courses
        if course.category is Category.GENERAL_ELECTIVE and course.area == elective_area
    ]


def _has_upload(upload_file: UploadFile | None) -> bool:
    return upload_file is not None and bool((upload_file.filename or "").strip())


def _elective_catalog_app_error(exc: UploadedCatalogError) -> AppError:
    message = str(exc) or "교양선택 수강편람을 처리하지 못했습니다."
    if "파일 크기" in message:
        return AppError(
            "FILE_TOO_LARGE",
            "업로드 파일은 5MB 이하여야 합니다.",
            status_code=413,
            details={"max_size_bytes": MAX_UPLOAD_SIZE},
        )
    if "유효한 .xlsx" in message or "엑셀 파일을 열 수 없습니다" in message:
        return AppError(
            "INVALID_EXCEL_FILE",
            "유효한 .xlsx 파일이 아닙니다.",
            status_code=400,
        )
    if ".xlsx" in message:
        return AppError(
            "INVALID_FILE_EXTENSION",
            "교양선택 수강편람은 .xlsx 파일만 업로드할 수 있습니다.",
            status_code=400,
        )
    if "교양 영역" in message:
        return AppError(
            "INVALID_ELECTIVE_AREA",
            "교양 영역은 1~9 사이의 정수여야 합니다.",
            status_code=400,
        )
    if "비어 있습니다" in message or "찾지 못했습니다" in message:
        return AppError("EMPTY_ELECTIVE_CATALOG", message, status_code=422)
    if "필수 열" in message:
        return AppError("INVALID_CATALOG_FORMAT", message, status_code=422)
    return AppError("ELECTIVE_CATALOG_PARSE_FAILED", message, status_code=422)


def _response_from_session(session) -> GeneralPreparationResponse:
    data_source = session.general_pool_data_source or (
        "uploaded_catalog" if session.elective_candidates else "fallback_catalog"
    )
    return GeneralPreparationResponse(
        session_id=session.session_id,
        session_stage=session.session_stage,
        required_course_count=len(session.general_required_candidates),
        elective_course_count=len(session.general_elective_candidates),
        excluded_course_count=len(session.general_pool_diagnostics),
        data_source=data_source,
        elective_area=session.general_pool_elective_area,
        warnings=list(session.general_pool_warnings),
    )

