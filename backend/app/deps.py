"""FastAPI dependency providers."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from .core.errors import AppError
from .agent_tools import (
    CourseDiscoveryTools,
    SessionAgentTools,
    SessionCommandTools,
    SessionQueryTools,
    TimetableGenerationTools,
)
from .agents import SessionStateAgent, SessionStateToolset
from .agents.simple_session_model import LlmSessionStateModel, SimpleSessionStateModel, SessionStateModel
from .models.course import Category
from .repositories import SessionRepository, SessionStoreCatalogRepository, SessionStoreRepository
from .services.course_discovery_service import CourseDiscoveryService
from .services.course_loader import CourseCatalogLoadError, load_courses
from .services.course_restriction_loader import (
    CourseRestrictionLoadError,
    load_department_restriction_rules,
)
from .services.general_course_pool_service import (
    CourseRestrictionPolicy,
    GeneralCoursePoolService,
    GeneralCoursePreparationService,
)
from .services.major_confirm_service import MajorConfirmService
from .services.major_catalog_upload_service import MajorCatalogUploadService
from .services.uploaded_catalog_parser import UploadedCatalogParser
from .services.major_preview_service import MajorPreviewService
from .services.major_selection_parser import MajorSelectionParser
from .services.session_store import SessionStore, session_store
from .services.session_service import SessionService
from .services.timetable_generation_service import TimetableGenerationService
from .services.timetable_candidate_generation_service import TimetableCandidateGenerationService
from .services.timetable_candidate_validation_service import TimetableCandidateValidationService
from .services.ranking_template_service import RankingTemplateService
from .services.timetable_ranker import TimetableRanker
from .services.timetable_ranking_service import TimetableRankingService


_BACKEND_DIR = Path(__file__).resolve().parents[1]
_COURSE_CATALOG_PATH = _BACKEND_DIR / "data" / "course_catalog.json"
_COURSE_RESTRICTIONS_PATH = _BACKEND_DIR / "data" / "course_restrictions.json"
logger = logging.getLogger(__name__)
_SESSION_REPOSITORY = SessionStoreRepository(session_store)
_CATALOG_REPOSITORY = SessionStoreCatalogRepository(session_store)
_SESSION_SERVICE = SessionService(_SESSION_REPOSITORY)
_SESSION_AGENT_TOOLS = SessionAgentTools(_SESSION_SERVICE)
_SESSION_QUERY_TOOLS = SessionQueryTools(_SESSION_SERVICE)
_SESSION_COMMAND_TOOLS = SessionCommandTools(_SESSION_SERVICE)
_COURSE_DISCOVERY_SERVICE = CourseDiscoveryService(_CATALOG_REPOSITORY)
_COURSE_DISCOVERY_TOOLS = CourseDiscoveryTools(_COURSE_DISCOVERY_SERVICE)
_TIMETABLE_CANDIDATE_VALIDATION_SERVICE = TimetableCandidateValidationService(
    catalog_repository=_CATALOG_REPOSITORY,
)
_TIMETABLE_CANDIDATE_GENERATION_SERVICE = TimetableCandidateGenerationService(
    catalog_repository=_CATALOG_REPOSITORY,
)
_TIMETABLE_GENERATION_TOOLS = TimetableGenerationTools(
    generation_service=_TIMETABLE_CANDIDATE_GENERATION_SERVICE,
    validation_service=_TIMETABLE_CANDIDATE_VALIDATION_SERVICE,
)
_SESSION_STATE_TOOLSET = SessionStateToolset.from_agent_and_discovery_tools(
    _SESSION_AGENT_TOOLS,
    _COURSE_DISCOVERY_TOOLS,
    _TIMETABLE_GENERATION_TOOLS,
)
def _build_session_state_model() -> SessionStateModel:
    provider = os.getenv("SESSION_STATE_MODEL_PROVIDER", "simple").strip().lower()
    environment = os.getenv("APP_ENV", "development").strip().lower()
    if provider in {"llm", "openai"}:
        return LlmSessionStateModel()
    if environment in {"production", "prod"} and provider == "simple":
        raise RuntimeError(
            "SESSION_STATE_MODEL_PROVIDER must be configured in production; "
            "the simple fallback is for local development and tests only."
        )
    logger.warning(
        "Using SimpleSessionStateModel fallback; configure SESSION_STATE_MODEL_PROVIDER=llm for production."
    )
    return SimpleSessionStateModel()


_SESSION_STATE_AGENT = SessionStateAgent(
    model=_build_session_state_model(),
    tools=_SESSION_STATE_TOOLSET,
)


def get_session_store() -> SessionStore:
    return session_store


def get_session_repository() -> SessionRepository:
    return _SESSION_REPOSITORY


def get_session_service() -> SessionService:
    return _SESSION_SERVICE


def get_session_query_tools() -> SessionQueryTools:
    return _SESSION_QUERY_TOOLS


def get_session_command_tools() -> SessionCommandTools:
    return _SESSION_COMMAND_TOOLS


def get_course_discovery_service() -> CourseDiscoveryService:
    return _COURSE_DISCOVERY_SERVICE


def get_course_discovery_tools() -> CourseDiscoveryTools:
    return _COURSE_DISCOVERY_TOOLS


def get_session_state_toolset() -> SessionStateToolset:
    return _SESSION_STATE_TOOLSET


def get_session_state_agent() -> SessionStateAgent:
    return _SESSION_STATE_AGENT


def get_major_selection_parser() -> MajorSelectionParser:
    return MajorSelectionParser()


def get_major_preview_service() -> MajorPreviewService:
    return MajorPreviewService(
        store=get_session_store(),
        parser=get_major_selection_parser(),
    )


def get_major_confirm_service() -> MajorConfirmService:
    return MajorConfirmService(store=get_session_store())


def get_major_catalog_upload_service() -> MajorCatalogUploadService:
    return MajorCatalogUploadService(store=get_session_store())


def get_timetable_generation_service() -> TimetableGenerationService:
    return TimetableGenerationService(store=get_session_store())


def get_ranking_template_service() -> RankingTemplateService:
    return RankingTemplateService()


def get_timetable_ranking_service() -> TimetableRankingService:
    template_service = get_ranking_template_service()
    return TimetableRankingService(
        store=get_session_store(),
        template_service=template_service,
        ranker=TimetableRanker(template_service=template_service),
    )


def get_course_restriction_policy() -> CourseRestrictionPolicy:
    try:
        rules = load_department_restriction_rules(_COURSE_RESTRICTIONS_PATH)
    except CourseRestrictionLoadError as exc:
        raise AppError(
            "COURSE_RESTRICTION_LOAD_FAILED",
            "교양 수강 제한 데이터를 로딩하지 못했습니다.",
            status_code=500,
        ) from exc
    return CourseRestrictionPolicy(rules=rules)


def get_general_course_pool_service() -> GeneralCoursePoolService:
    return GeneralCoursePoolService(
        restriction_policy=get_course_restriction_policy(),
    )


def get_general_course_preparation_service() -> GeneralCoursePreparationService:
    try:
        general_required_courses = load_courses(
            _COURSE_CATALOG_PATH,
            category=Category.GENERAL_REQUIRED,
        )
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
        general_required_courses=general_required_courses,
        fallback_elective_courses=fallback_elective_courses,
        elective_parser=UploadedCatalogParser(),
    )
