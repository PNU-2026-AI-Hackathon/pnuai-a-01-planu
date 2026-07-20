"""Build general-required/elective candidate pools before timetable generation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re
from collections.abc import Iterable

from ..core.errors import AppError
from ..models.course import Category, Course
from ..models.general_course_pool import (
    ExcludedCourseDiagnostic,
    GeneralCoursePoolResult,
    GeneralCoursePools,
)
from .session_store import SessionNotFoundError, SessionStage, SessionStore, session_store


class EligibilityStatus(str, Enum):
    ELIGIBLE = "eligible"
    NOT_ELIGIBLE = "not_eligible"
    NOT_RESTRICTED = "not_restricted"
    RULE_DATA_MISSING = "rule_data_missing"
    UNKNOWN_DEPARTMENT = "unknown_department"


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
        self.rules_by_course_section = {
            (_normalized(rule.course_code), _normalized(rule.division)): rule
            for rule in rules
        }

    def evaluate(self, course: Course, *, department: str) -> EligibilityDecision:
        department_name = department.strip()
        if not department_name:
            return EligibilityDecision(
                EligibilityStatus.UNKNOWN_DEPARTMENT,
                "사용자 학과 정보가 없습니다.",
            )

        rule = self.rules_by_course_section.get(_course_key(course))
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

        required_candidates = list(general_required_courses)
        if not required_candidates:
            raise AppError(
                "RESTRICTED_COURSE_DATA_NOT_FOUND",
                "교양필수 후보 데이터가 없습니다.",
                status_code=500,
            )

        uploaded = list(uploaded_elective_courses or [])
        fallback = list(fallback_elective_courses or [])
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


class GeneralCoursePreparationService:
    def __init__(
        self,
        *,
        store: SessionStore = session_store,
        pool_service: GeneralCoursePoolService | None = None,
        general_required_courses: Iterable[Course] = (),
        fallback_elective_courses: Iterable[Course] | None = None,
    ) -> None:
        self.store = store
        self.pool_service = pool_service or GeneralCoursePoolService()
        self.general_required_courses = list(general_required_courses)
        self.fallback_elective_courses = (
            None if fallback_elective_courses is None else list(fallback_elective_courses)
        )

    def prepare_for_session(self, session_id: str) -> GeneralCoursePoolResult:
        try:
            session = self.store.get(session_id)
        except SessionNotFoundError as exc:
            raise AppError(
                "SESSION_NOT_FOUND",
                "세션을 찾을 수 없거나 만료되었습니다.",
                status_code=404,
            ) from exc

        if session.session_stage is SessionStage.GENERAL_READY:
            return GeneralCoursePoolResult(
                pools=GeneralCoursePools(
                    required_courses=session.general_required_candidates,
                    elective_courses=session.general_elective_candidates,
                ),
                excluded_courses=session.general_pool_diagnostics,
                warnings=session.general_pool_warnings,
            )

        if session.session_stage is not SessionStage.MAJOR_CONFIRMED:
            raise AppError(
                "INVALID_SESSION_STAGE",
                "전공 시간표 확정 이후에만 교양 후보 풀을 생성할 수 있습니다.",
                status_code=409,
            )
        if not session.department.strip():
            raise AppError("DEPARTMENT_NOT_FOUND", "사용자 학과 정보가 없습니다.", status_code=409)

        result = self.pool_service.build_pools(
            department=session.department,
            general_required_courses=self.general_required_courses,
            uploaded_elective_courses=session.elective_candidates,
            fallback_elective_courses=self.fallback_elective_courses,
        )

        try:
            self.store.update_general_course_pool(session.session_id, result)
        except (TypeError, ValueError) as exc:
            raise AppError(
                "GENERAL_COURSE_POOL_SAVE_FAILED",
                "교양 후보 풀을 세션에 저장하지 못했습니다.",
                status_code=500,
            ) from exc
        return result


def _course_key(course: Course) -> tuple[str, str]:
    if course.course_id:
        code = course.course_id.rsplit("-", 1)[0]
    else:
        code = _normalized(course.course_name)
    return (_normalized(code), _normalized(course.division))


def _normalized(value: str) -> str:
    return re.sub(r"\s+", "", value).casefold()


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
        EligibilityStatus.RULE_DATA_MISSING: "DEPARTMENT_RULE_DATA_MISSING",
        EligibilityStatus.UNKNOWN_DEPARTMENT: "UNKNOWN_DEPARTMENT",
        EligibilityStatus.ELIGIBLE: "ELIGIBLE",
        EligibilityStatus.NOT_RESTRICTED: "NOT_RESTRICTED",
    }[status]
