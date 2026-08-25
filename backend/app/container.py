"""Application composition root for the PlaNU backend."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .agent_tools import (
    CourseDiscoveryTools,
    SessionAgentTools,
    TimetableGenerationTools,
    TimetableScoringTools,
    TimetableSelectionTools,
)
from .agents import (
    AgentDomain,
    DomainAgent,
    PlanuSupervisorAgent,
    SessionStateAgent,
    SessionStateToolset,
    major_responsibility,
    preference_responsibility,
    timetable_responsibility,
)
from .agents.simple_session_model import (
    LlmSessionStateModel,
    SessionStateModel,
    SimpleSessionStateModel,
)
from .core.errors import AppError
from .models.course import Category
from .repositories import SessionStoreCatalogRepository, SessionStoreRepository
from .repositories.recent_timetable_candidate_repository import RecentTimetableCandidateRepository
from .services.condition_summary_service import ConditionSummaryService
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
from .services.timetable_ranker import TimetableRanker
from .services.timetable_ranking_service import TimetableRankingService
from .services.timetable_revision_preparation_service import TimetableRevisionPreparationService
from .services.timetable_scoring_service import TimetableScoringService
from .services.timetable_soft_ranking_service import TimetableRankingService as SoftTimetableRankingService
from .services.timetable_validation_service import TimetableValidationService
from .services.uploaded_catalog_parser import UploadedCatalogParser


logger = logging.getLogger(__name__)
_BACKEND_DIR = Path(__file__).resolve().parents[1]
_COURSE_CATALOG_PATH = _BACKEND_DIR / "data" / "course_catalog.json"
_COURSE_RESTRICTIONS_PATH = _BACKEND_DIR / "data" / "course_restrictions.json"


@dataclass(slots=True)
class PlanuContainer:
    """Owns process-lifetime repositories, services, tools, and agent runtime."""

    session_store: SessionStore
    session_repository: SessionStoreRepository
    catalog_repository: SessionStoreCatalogRepository
    session_service: SessionService
    condition_summary_service: ConditionSummaryService
    session_agent_tools: SessionAgentTools
    course_discovery_service: CourseDiscoveryService
    course_discovery_tools: CourseDiscoveryTools
    timetable_validation_service: TimetableValidationService
    timetable_candidate_validation_service: TimetableCandidateValidationService
    timetable_candidate_generation_service: TimetableCandidateGenerationService
    timetable_generation_tools: TimetableGenerationTools
    timetable_scoring_service: TimetableScoringService
    timetable_ranking_service_for_agent: SoftTimetableRankingService
    timetable_scoring_tools: TimetableScoringTools
    timetable_revision_preparation_service: TimetableRevisionPreparationService
    timetable_selection_tools: TimetableSelectionTools
    recent_timetable_candidate_repository: RecentTimetableCandidateRepository
    major_toolset: SessionStateToolset
    preference_toolset: SessionStateToolset
    timetable_toolset: SessionStateToolset
    session_state_toolset: SessionStateToolset
    major_agent: DomainAgent
    preference_agent: DomainAgent
    timetable_agent: DomainAgent
    legacy_session_state_agent: SessionStateAgent
    supervisor_agent: PlanuSupervisorAgent
    major_catalog_upload_service: MajorCatalogUploadService
    major_preview_service: MajorPreviewService
    major_confirm_service: MajorConfirmService
    legacy_timetable_generation_service: TimetableGenerationService
    legacy_timetable_ranking_service: TimetableRankingService
    general_course_pool_service: GeneralCoursePoolService
    general_course_preparation_service: GeneralCoursePreparationService


def build_container(
    *,
    session_store: SessionStore | None = None,
    model: SessionStateModel | None = None,
    model_factory: Callable[[], SessionStateModel] | None = None,
) -> PlanuContainer:
    """Build the real application object graph once per FastAPI app instance."""

    store = session_store if session_store is not None else SessionStore()
    session_repository = SessionStoreRepository(store)
    catalog_repository = SessionStoreCatalogRepository(store)
    session_service = SessionService(session_repository, session_ttl=store.ttl, now_provider=store._clock)
    condition_summary_service = ConditionSummaryService(catalog_repository)

    restriction_policy = _load_restriction_policy()
    validation_service = TimetableValidationService(restriction_policy=restriction_policy)
    recent_candidates = RecentTimetableCandidateRepository()
    candidate_validation_service = TimetableCandidateValidationService(
        catalog_repository=catalog_repository,
        validation_service=validation_service,
    )
    candidate_generation_service = TimetableCandidateGenerationService(
        catalog_repository=catalog_repository,
        validation_service=validation_service,
    )
    generation_tools = TimetableGenerationTools(
        generation_service=candidate_generation_service,
        validation_service=candidate_validation_service,
        recent_candidate_repository=recent_candidates,
        session_service=session_service,
        condition_summary_service=condition_summary_service,
    )

    scoring_service = TimetableScoringService()
    soft_ranking_service = SoftTimetableRankingService(scoring_service=scoring_service)
    scoring_tools = TimetableScoringTools(
        scoring_service=scoring_service,
        ranking_service=soft_ranking_service,
    )

    session_agent_tools = SessionAgentTools(session_service, condition_summary_service)
    discovery_service = CourseDiscoveryService(catalog_repository)
    discovery_tools = CourseDiscoveryTools(discovery_service)
    revision_service = TimetableRevisionPreparationService(
        session_service=session_service,
        catalog_repository=catalog_repository,
    )
    selection_tools = TimetableSelectionTools(
        session_service=session_service,
        revision_preparation_service=revision_service,
        recent_candidate_repository=recent_candidates,
    )
    major_toolset = _build_major_toolset(session_agent_tools, discovery_tools)
    preference_toolset = _build_preference_toolset(session_agent_tools)
    timetable_toolset = _build_timetable_toolset(
        session_agent_tools,
        discovery_tools,
        generation_tools,
        scoring_tools,
        selection_tools,
    )
    toolset = SessionStateToolset.from_agent_and_discovery_tools(
        session_agent_tools,
        discovery_tools,
        generation_tools,
        scoring_tools=scoring_tools,
        selection_tools=selection_tools,
    )
    model_instance = model or (model_factory or _build_session_state_model)()
    major_agent = DomainAgent(
        domain=AgentDomain.MAJOR,
        agent=SessionStateAgent(
            model=model_instance,
            tools=major_toolset,
            system_prompt=_load_agent_prompt("major_agent_system.txt"),
        ),
        can_handle=major_responsibility,
    )
    preference_agent = DomainAgent(
        domain=AgentDomain.PREFERENCE,
        agent=SessionStateAgent(
            model=model_instance,
            tools=preference_toolset,
            system_prompt=_load_agent_prompt("preference_agent_system.txt"),
        ),
        can_handle=preference_responsibility,
    )
    timetable_agent = DomainAgent(
        domain=AgentDomain.TIMETABLE,
        agent=SessionStateAgent(
            model=model_instance,
            tools=timetable_toolset,
            system_prompt=_load_agent_prompt("timetable_agent_system.txt"),
        ),
        can_handle=timetable_responsibility,
    )
    legacy_agent = SessionStateAgent(model=model_instance, tools=toolset)
    supervisor_agent = PlanuSupervisorAgent(
        major_agent=major_agent,
        preference_agent=preference_agent,
        timetable_agent=timetable_agent,
    )

    general_pool_service = GeneralCoursePoolService(restriction_policy=restriction_policy)
    general_required, fallback_electives = _load_default_general_courses()
    template_service = RankingTemplateService()
    return PlanuContainer(
        session_store=store,
        session_repository=session_repository,
        catalog_repository=catalog_repository,
        session_service=session_service,
        condition_summary_service=condition_summary_service,
        session_agent_tools=session_agent_tools,
        course_discovery_service=discovery_service,
        course_discovery_tools=discovery_tools,
        timetable_validation_service=validation_service,
        timetable_candidate_validation_service=candidate_validation_service,
        timetable_candidate_generation_service=candidate_generation_service,
        timetable_generation_tools=generation_tools,
        timetable_scoring_service=scoring_service,
        timetable_ranking_service_for_agent=soft_ranking_service,
        timetable_scoring_tools=scoring_tools,
        timetable_revision_preparation_service=revision_service,
        timetable_selection_tools=selection_tools,
        recent_timetable_candidate_repository=recent_candidates,
        major_toolset=major_toolset,
        preference_toolset=preference_toolset,
        timetable_toolset=timetable_toolset,
        session_state_toolset=toolset,
        major_agent=major_agent,
        preference_agent=preference_agent,
        timetable_agent=timetable_agent,
        legacy_session_state_agent=legacy_agent,
        supervisor_agent=supervisor_agent,
        major_catalog_upload_service=MajorCatalogUploadService(
            store=store,
            session_service=session_service,
            catalog_repository=catalog_repository,
        ),
        major_preview_service=MajorPreviewService(
            store=store,
            parser=MajorSelectionParser(),
        ),
        major_confirm_service=MajorConfirmService(store=store),
        legacy_timetable_generation_service=TimetableGenerationService(
            store=store,
            recent_candidate_repository=recent_candidates,
        ),
        legacy_timetable_ranking_service=TimetableRankingService(
            store=store,
            template_service=template_service,
            ranker=TimetableRanker(template_service=template_service),
        ),
        general_course_pool_service=general_pool_service,
        general_course_preparation_service=GeneralCoursePreparationService(
            store=store,
            pool_service=general_pool_service,
            general_required_courses=general_required,
            fallback_elective_courses=fallback_electives,
            elective_parser=UploadedCatalogParser(),
            session_service=session_service,
        ),
    )



def _load_agent_prompt(filename: str) -> str:
    return (_BACKEND_DIR / "app" / "agents" / "prompts" / filename).read_text(encoding="utf-8")

def _build_major_toolset(
    session_tools: SessionAgentTools,
    discovery_tools: CourseDiscoveryTools,
) -> SessionStateToolset:
    return SessionStateToolset(
        {
            "get_session_summary": session_tools.get_session_summary,
            "update_selected_major_courses": session_tools.update_selected_major_courses,
            "search_courses_by_name": discovery_tools.search_courses_by_name,
            "discover_courses": discovery_tools.discover_courses,
            "get_course_sections": discovery_tools.get_course_sections,
            "get_section_details": discovery_tools.get_section_details,
        }
    )


def _build_preference_toolset(session_tools: SessionAgentTools) -> SessionStateToolset:
    return SessionStateToolset(
        {
            "get_session_summary": session_tools.get_session_summary,
            "update_timetable_preferences": session_tools.update_timetable_preferences,
            "reset_session_preferences": session_tools.reset_session_preferences,
        }
    )


def _build_timetable_toolset(
    session_tools: SessionAgentTools,
    discovery_tools: CourseDiscoveryTools,
    generation_tools: TimetableGenerationTools,
    scoring_tools: TimetableScoringTools,
    selection_tools: TimetableSelectionTools,
) -> SessionStateToolset:
    return SessionStateToolset(
        {
            "get_session_summary": session_tools.get_session_summary,
            "search_courses_by_name": discovery_tools.search_courses_by_name,
            "discover_courses": discovery_tools.discover_courses,
            "get_course_sections": discovery_tools.get_course_sections,
            "get_section_details": discovery_tools.get_section_details,
            "confirm_timetable_conditions": session_tools.confirm_timetable_conditions,
            "generate_timetable_candidates": generation_tools.generate_timetable_candidates,
            "validate_timetable_candidate": generation_tools.validate_timetable_candidate,
            "score_timetable_candidate": scoring_tools.score_timetable_candidate,
            "rank_timetable_candidates": scoring_tools.rank_timetable_candidates,
            "select_timetable_candidate": selection_tools.select_timetable_candidate,
            "get_selected_timetable": selection_tools.get_selected_timetable,
            "clear_selected_timetable": selection_tools.clear_selected_timetable,
            "prepare_timetable_revision": selection_tools.prepare_timetable_revision,
        }
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


def _load_restriction_policy() -> CourseRestrictionPolicy:
    try:
        rules = load_department_restriction_rules(_COURSE_RESTRICTIONS_PATH)
    except CourseRestrictionLoadError as exc:
        raise AppError(
            "COURSE_RESTRICTION_LOAD_FAILED",
            "교양 수강 제한 데이터를 로딩하지 못했습니다.",
            status_code=500,
        ) from exc
    return CourseRestrictionPolicy(rules=rules)


def _load_default_general_courses() -> tuple[list, list]:
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
    return general_required_courses, fallback_elective_courses









