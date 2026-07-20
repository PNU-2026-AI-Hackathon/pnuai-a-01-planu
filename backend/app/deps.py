"""FastAPI dependency providers."""

from __future__ import annotations

from pathlib import Path

from .core.errors import AppError
from .models.course import Category
from .services.course_loader import CourseCatalogLoadError, load_courses
from .services.general_course_pool_service import (
    CourseRestrictionPolicy,
    GeneralCoursePoolService,
    GeneralCoursePreparationService,
)
from .services.major_confirm_service import MajorConfirmService
from .services.major_preview_service import MajorPreviewService
from .services.major_selection_parser import MajorSelectionParser
from .services.session_store import SessionStore, session_store


_BACKEND_DIR = Path(__file__).resolve().parents[1]
_COURSE_CATALOG_PATH = _BACKEND_DIR / "data" / "course_catalog.json"


def get_session_store() -> SessionStore:
    return session_store


def get_major_selection_parser() -> MajorSelectionParser:
    return MajorSelectionParser()


def get_major_preview_service() -> MajorPreviewService:
    return MajorPreviewService(
        store=get_session_store(),
        parser=get_major_selection_parser(),
    )


def get_major_confirm_service() -> MajorConfirmService:
    return MajorConfirmService(store=get_session_store())


def get_course_restriction_policy() -> CourseRestrictionPolicy:
    # TODO: Inject the real department eligibility/restriction rule data here
    # once that loader is finalized. Keeping construction here prevents routers
    # from reading JSON files or assembling policy objects directly.
    return CourseRestrictionPolicy()


def get_general_course_pool_service() -> GeneralCoursePoolService:
    return GeneralCoursePoolService(
        restriction_policy=get_course_restriction_policy(),
    )


def get_general_course_preparation_service() -> GeneralCoursePreparationService:
    try:
        internal_general_courses = load_courses(_COURSE_CATALOG_PATH)
        fallback_elective_courses = load_courses(
            _COURSE_CATALOG_PATH,
            category=Category.GENERAL_ELECTIVE,
        )
    except CourseCatalogLoadError as exc:
        raise AppError(
            "RESTRICTED_COURSE_LOAD_FAILED",
            "내부 교양 및 제한 과목 데이터를 로딩하지 못했습니다.",
            status_code=500,
        ) from exc

    return GeneralCoursePreparationService(
        store=get_session_store(),
        pool_service=get_general_course_pool_service(),
        internal_general_courses=internal_general_courses,
        fallback_elective_courses=fallback_elective_courses,
    )
