"""FastAPI dependency providers backed by the application container."""

from __future__ import annotations

import logging

from fastapi import Request

from .agent_tools import (
    CourseDiscoveryTools,
    SessionCommandTools,
    SessionQueryTools,
    TimetableGenerationTools,
    TimetableScoringTools,
    TimetableSelectionTools,
)
from .agents import SessionStateAgent, SessionStateToolset
from .container import PlanuContainer, build_container
from .services.course_restriction_loader import load_department_restriction_rules
from .repositories import SessionRepository, SessionStoreCatalogRepository
from .repositories.recent_timetable_candidate_repository import RecentTimetableCandidateRepository
from .services.course_discovery_service import CourseDiscoveryService
from .services.general_course_pool_service import (
    CourseRestrictionPolicy,
    GeneralCoursePoolService,
    GeneralCoursePreparationService,
)
from .services.major_catalog_upload_service import MajorCatalogUploadService
from .services.major_confirm_service import MajorConfirmService
from .services.major_preview_service import MajorPreviewService
from .services.major_selection_parser import MajorSelectionParser
from .services.ranking_template_service import RankingTemplateService
from .services.session_service import SessionService
from .services.session_store import SessionStore
from .services.timetable_candidate_generation_service import TimetableCandidateGenerationService
from .services.timetable_candidate_validation_service import TimetableCandidateValidationService
from .services.timetable_generation_service import TimetableGenerationService
from .services.timetable_ranking_service import TimetableRankingService
from .services.timetable_revision_preparation_service import TimetableRevisionPreparationService
from .services.timetable_scoring_service import TimetableScoringService
from .services.timetable_soft_ranking_service import TimetableRankingService as SoftTimetableRankingService
from .services.timetable_validation_service import TimetableValidationService


_DEFAULT_CONTAINER: PlanuContainer | None = None
logger = logging.getLogger(__name__)


def get_container(request: Request = None) -> PlanuContainer:
    """Return the process-lifetime PlaNU container for the running app."""

    if request is not None and hasattr(request.app.state, "container"):
        container = request.app.state.container
        if _needs_container_rewire(container):
            logger.warning(
                "planu_container_rewire_required reason=missing_preference_course_search"
            )
            container = build_container(session_store=container.session_store)
            request.app.state.container = container
        return container
    global _DEFAULT_CONTAINER
    if _DEFAULT_CONTAINER is None or _needs_container_rewire(_DEFAULT_CONTAINER):
        if _DEFAULT_CONTAINER is not None:
            logger.warning(
                "planu_default_container_rewire_required reason=missing_preference_course_search"
            )
        _DEFAULT_CONTAINER = build_container(
            session_store=None if _DEFAULT_CONTAINER is None else _DEFAULT_CONTAINER.session_store
        )
    return _DEFAULT_CONTAINER


def _needs_container_rewire(container: PlanuContainer) -> bool:
    try:
        preference_tools = {spec.name for spec in container.preference_toolset.specs()}
        preference_agent_tools = set(container.preference_agent.tool_names)
    except Exception:
        return True
    return (
        "search_courses_by_name" not in preference_tools
        or "search_courses_by_name" not in preference_agent_tools
    )


def get_session_store(request: Request = None) -> SessionStore:
    return get_container(request).session_store


def get_session_repository(request: Request = None) -> SessionRepository:
    return get_container(request).session_repository


def get_catalog_repository(request: Request = None) -> SessionStoreCatalogRepository:
    return get_container(request).catalog_repository


def get_session_service(request: Request = None) -> SessionService:
    return get_container(request).session_service


def get_session_query_tools(request: Request = None) -> SessionQueryTools:
    return SessionQueryTools(get_session_service(request))


def get_session_command_tools(request: Request = None) -> SessionCommandTools:
    return SessionCommandTools(get_session_service(request))


def get_course_discovery_service(request: Request = None) -> CourseDiscoveryService:
    return get_container(request).course_discovery_service


def get_course_discovery_tools(request: Request = None) -> CourseDiscoveryTools:
    return get_container(request).course_discovery_tools


def get_recent_timetable_candidate_repository(request: Request = None) -> RecentTimetableCandidateRepository:
    return get_container(request).recent_timetable_candidate_repository


def get_timetable_revision_preparation_service(request: Request = None) -> TimetableRevisionPreparationService:
    return get_container(request).timetable_revision_preparation_service


def get_timetable_selection_tools(request: Request = None) -> TimetableSelectionTools:
    return get_container(request).timetable_selection_tools


def get_course_restriction_policy(request: Request = None) -> CourseRestrictionPolicy:
    return get_container(request).general_course_pool_service.restriction_policy


def get_timetable_validation_service(request: Request = None) -> TimetableValidationService:
    return get_container(request).timetable_validation_service


def get_timetable_candidate_validation_service(request: Request = None) -> TimetableCandidateValidationService:
    return get_container(request).timetable_candidate_validation_service


def get_timetable_candidate_generation_service(request: Request = None) -> TimetableCandidateGenerationService:
    return get_container(request).timetable_candidate_generation_service


def get_timetable_generation_tools(request: Request = None) -> TimetableGenerationTools:
    return get_container(request).timetable_generation_tools


def get_timetable_scoring_service(request: Request = None) -> TimetableScoringService:
    return get_container(request).timetable_scoring_service


def get_timetable_soft_ranking_service(request: Request = None) -> SoftTimetableRankingService:
    return get_container(request).timetable_ranking_service_for_agent


def get_timetable_scoring_tools(request: Request = None) -> TimetableScoringTools:
    return get_container(request).timetable_scoring_tools


def get_session_state_toolset(request: Request = None) -> SessionStateToolset:
    return get_container(request).session_state_toolset


def get_session_state_agent(request: Request = None) -> SessionStateAgent:
    return get_container(request).legacy_session_state_agent


def clear_dependency_caches() -> None:
    global _DEFAULT_CONTAINER
    _DEFAULT_CONTAINER = None


def get_major_selection_parser() -> MajorSelectionParser:
    return MajorSelectionParser()


def get_major_preview_service(request: Request = None) -> MajorPreviewService:
    return get_container(request).major_preview_service


def get_major_confirm_service(request: Request = None) -> MajorConfirmService:
    return get_container(request).major_confirm_service


def get_major_catalog_upload_service(request: Request = None) -> MajorCatalogUploadService:
    return get_container(request).major_catalog_upload_service


def get_timetable_generation_service(request: Request = None) -> TimetableGenerationService:
    return get_container(request).legacy_timetable_generation_service


def get_ranking_template_service(request: Request = None) -> RankingTemplateService:
    return get_container(request).legacy_timetable_ranking_service.template_service


def get_timetable_ranking_service(request: Request = None) -> TimetableRankingService:
    return get_container(request).legacy_timetable_ranking_service


def get_general_course_pool_service(request: Request = None) -> GeneralCoursePoolService:
    return get_container(request).general_course_pool_service


def get_general_course_preparation_service(request: Request = None) -> GeneralCoursePreparationService:
    return get_container(request).general_course_preparation_service


def get_agent_runtime(request: Request = None):
    from .runtime import AgentRuntime

    container = get_container(request)
    return AgentRuntime(
        session_service=container.session_service,
        agent=container.supervisor_agent,
        selection_tools=container.timetable_selection_tools,
        condition_summary_service=container.condition_summary_service,
        general_course_preparation_service=container.general_course_preparation_service,
    )


def get_condition_summary_service(request: Request = None):
    return get_container(request).condition_summary_service
