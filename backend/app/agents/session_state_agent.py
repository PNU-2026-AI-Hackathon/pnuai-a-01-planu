"""Single-agent execution loop for PlaNU session-state management."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Mapping
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from ..agent_tools import (
    BoolPreferenceInput,
    CatalogInput,
    CourseIdInput,
    CourseIdsInput,
    CourseSectionsInput,
    DepartmentInput,
    DayInput,
    DaysInput,
    SearchCoursesByNameInput,
    SectionDetailsInput,
    SessionIdInput,
    SessionStateSummary,
    SessionToolResult,
    TimeInput,
    ScoreTimetableCandidateRequest,
    SelectTimetableCandidateInput,
    ResetSessionPreferencesInput,
    UpdateSelectedMajorCoursesInput,
    UpdateSessionProfileInput,
    UpdateTimetablePreferencesInput,
)
from ..models.course_discovery import CourseDiscoveryRequest
from ..models.course_discovery import (
    CourseCandidate,
    CourseDiscoveryResult,
    DiscoveryResolution,
)
from ..models.timetable_generation import (
    GeneratedTimetableCandidate,
    ResolvedSection,
    GenerationFailureCode,
    GenerationFailureReason,
    TimetableGenerationRequest,
    TimetableGenerationResult,
    TimetableValidationRequest,
    TimetableValidationResult,
)
from ..models.timetable_revision import TimetableRevisionRequest
from ..models.timetable_scoring import (
    PreferenceEvidence,
    ScoredTimetableCandidate,
    ScoreComponent,
    ScoringTradeOff,
    TimetableRankingResult,
    TimetableScoringError,
    TimetableScoringRequest,
)

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_PATH = Path(__file__).with_name("prompts") / "session_state_agent_system.txt"
DEFAULT_MAX_TOOL_CALLS = 10
DEFAULT_MAX_MUTATION_TOOL_CALLS = DEFAULT_MAX_TOOL_CALLS
DEFAULT_MAX_TOTAL_TOOL_CALLS = 40
READ_ONLY_TOOL_NAMES = {
    "get_session_summary",
    "search_courses_by_name",
    "discover_courses",
    "get_course_sections",
    "get_section_details",
    "generate_timetable_candidates",
    "validate_timetable_candidate",
    "score_timetable_candidate",
    "rank_timetable_candidates",
    "get_selected_timetable",
    "prepare_timetable_revision",
}


class SessionStateAgentErrorCode(str, Enum):
    """Stable error codes returned by the session-state agent."""

    INVALID_INPUT = "INVALID_INPUT"
    NOT_MY_RESPONSIBILITY = "NOT_MY_RESPONSIBILITY"
    SESSION_NOT_AVAILABLE = "SESSION_NOT_AVAILABLE"
    TOOL_ERROR = "TOOL_ERROR"
    MODEL_CALL_FAILED = "MODEL_CALL_FAILED"
    UNKNOWN_TOOL = "UNKNOWN_TOOL"
    INVALID_TOOL_ARGUMENTS = "INVALID_TOOL_ARGUMENTS"
    TOOL_CALL_LIMIT_EXCEEDED = "TOOL_CALL_LIMIT_EXCEEDED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class SessionStateAgentError(BaseModel):
    """Structured error for failures of the agent execution itself."""

    model_config = ConfigDict(extra="forbid")

    code: SessionStateAgentErrorCode
    message: str = Field(min_length=1)
    tool_name: str | None = None
    field: str | None = None
    value: str | None = None


class SessionStateAgentInput(BaseModel):
    """Input for one PlaNU session-state agent run."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    session_id: str = Field(min_length=1)
    user_message: str = Field(min_length=1)
    request_id: str | None = Field(default=None, min_length=1)
    locale: str | None = Field(default=None, min_length=1)

    @field_validator("session_id", "user_message")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be empty")
        return value


class ExecutedSessionTool(BaseModel):
    """Safe summary of one tool execution."""

    model_config = ConfigDict(extra="forbid")

    name: str
    success: bool
    changed: bool = False
    error_code: str | None = None
    message: str | None = None
    error_message: str | None = None
    error_field: str | None = None
    error_value: str | None = None


class UnresolvedCourseCandidate(BaseModel):
    """A candidate the user may need to choose from."""

    model_config = ConfigDict(extra="forbid")

    catalog_id: str | None = None
    catalog_type: str | None = None
    course_id: str | None = None
    course_name: str | None = None
    matching_section_ids: list[str] = Field(default_factory=list)
    resolution: str | None = None


class UnresolvedSessionRequest(BaseModel):
    """A user request the current session-state tools cannot safely apply."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    source_text: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    needed_information: str | None = None
    requires_user_confirmation: bool = False
    candidates: list[UnresolvedCourseCandidate] = Field(default_factory=list)


class AgentCourseCandidate(BaseModel):
    """A compact course candidate safe to return from an agent run."""

    model_config = ConfigDict(extra="forbid")

    course_id: str
    course_code: str
    course_name: str
    category: str
    area: int | None = None
    department: str | None = None
    matching_section_count: int
    total_section_count: int
    matching_section_ids: list[str] = Field(default_factory=list)
    match_reasons: list[str] = Field(default_factory=list)


class AgentDiscoveryResult(BaseModel):
    """Compact summary of one discovery/search tool result."""

    model_config = ConfigDict(extra="forbid")

    tool_name: str
    catalog_id: str
    resolution: str
    total_matched_courses: int
    returned_candidate_count: int
    message: str
    candidate_courses: list[AgentCourseCandidate] = Field(default_factory=list)


class ConfirmationRequest(BaseModel):
    """A user-facing request to choose among stable course candidates."""

    model_config = ConfigDict(extra="forbid")

    reason: str
    question: str
    candidates: list[AgentCourseCandidate] = Field(default_factory=list)


class AgentTimetableGenerationSummary(BaseModel):
    """Compact, user-safe summary of a timetable generation result."""

    model_config = ConfigDict(extra="forbid")

    generated_candidate_count: int
    total_candidates_found: int
    search_nodes_visited: int
    search_truncated: bool
    termination_reason: str
    applied_hard_constraints: dict[str, Any] = Field(default_factory=dict)
    target_additional_course_count: int | None = None
    target_additional_credits: float | None = None


class AgentTimetableCandidate(BaseModel):
    """A generated timetable candidate safe to return from an agent run."""

    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    section_ids: list[str]
    section_sources: list[dict[str, str]] = Field(default_factory=list)
    fixed_section_ids: list[str]
    fixed_section_sources: list[dict[str, str]] = Field(default_factory=list)
    added_section_ids: list[str]
    added_section_sources: list[dict[str, str]] = Field(default_factory=list)
    course_ids: list[str]
    total_credits: float
    valid: bool
    generation_order: int


class AgentTimetableSection(BaseModel):
    """User-safe course and section detail for a ranked candidate."""

    model_config = ConfigDict(extra="forbid")

    catalog_id: str
    section_id: str
    course_id: str
    course_code: str
    course_name: str
    division: str
    professor: str
    credit: float
    class_times: list[dict[str, Any]] = Field(default_factory=list)


class AgentScoredPreferenceEvidence(BaseModel):
    """Compact scoring evidence safe for user explanation."""

    model_config = ConfigDict(extra="forbid")

    code: str
    component_code: str | None = None
    values: dict[str, Any] = Field(default_factory=dict)


class AgentScoreComponent(BaseModel):
    """Compact score component safe for user explanation."""

    model_config = ConfigDict(extra="forbid")

    code: str
    label: str
    score: float
    satisfied: bool
    details: dict[str, Any] = Field(default_factory=dict)


class AgentTimetableTradeOff(BaseModel):
    """Compact trade-off evidence safe for user explanation."""

    model_config = ConfigDict(extra="forbid")

    code: str
    values: dict[str, Any] = Field(default_factory=dict)


class AgentRankedTimetableCandidate(BaseModel):
    """A ranked timetable candidate preserving ranking tool order."""

    model_config = ConfigDict(extra="forbid")

    rank: int
    candidate_id: str
    comparison_score: float
    total_credits: float
    section_ids: list[str]
    sections: list[AgentTimetableSection] = Field(default_factory=list)
    score_components: list[AgentScoreComponent] = Field(default_factory=list)
    satisfied_preferences: list[AgentScoredPreferenceEvidence] = Field(default_factory=list)
    unsatisfied_preferences: list[AgentScoredPreferenceEvidence] = Field(default_factory=list)
    trade_offs: list[AgentTimetableTradeOff] = Field(default_factory=list)
    tie_breaker: dict[str, Any] = Field(default_factory=dict)


class AgentRankingSummary(BaseModel):
    """Compact summary of a timetable ranking run."""

    model_config = ConfigDict(extra="forbid")

    ranking_applied: bool = False
    evaluated_candidate_count: int = 0
    returned_candidate_count: int = 0
    soft_preferences_present: bool = False
    scoring_policy_id: str | None = None
    highest_score: float | None = None
    lowest_score: float | None = None
    has_tied_scores: bool = False
    message: str | None = None


class AgentRankingError(BaseModel):
    """Structured ranking failure preserved separately from generation."""

    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    candidate_id: str | None = None

class AgentGenerationFailureReason(BaseModel):
    """User-facing generation failure reason capped for agent output."""

    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    course_id: str | None = None
    section_id: str | None = None
    constraint: str | None = None
    count: int = 1


class AgentValidationResult(BaseModel):
    """Compact validation result returned when validation is requested."""

    model_config = ConfigDict(extra="forbid")

    valid: bool
    checked_section_ids: list[str]
    violation_codes: list[str] = Field(default_factory=list)
    violation_messages: list[str] = Field(default_factory=list)


class SessionStateAgentResult(BaseModel):
    """Final structured result of a session-state agent run."""

    model_config = ConfigDict(extra="forbid")

    success: bool
    session_id: str | None = None
    request_id: str | None = None
    message: str
    changed: bool = False
    partially_applied: bool = False
    state_summary: SessionStateSummary | None = None
    executed_tools: list[ExecutedSessionTool] = Field(default_factory=list)
    failed_tools: list[ExecutedSessionTool] = Field(default_factory=list)
    unresolved_requests: list[UnresolvedSessionRequest] = Field(default_factory=list)
    discovery_results: list[AgentDiscoveryResult] = Field(default_factory=list)
    candidate_courses: list[AgentCourseCandidate] = Field(default_factory=list)
    timetable_candidates: list[AgentTimetableCandidate] = Field(default_factory=list)
    ranked_timetable_candidates: list[AgentRankedTimetableCandidate] = Field(default_factory=list)
    ranking_summary: AgentRankingSummary | None = None
    ranking_applied: bool = False
    effective_soft_preferences: dict[str, Any] | None = None
    ranking_error: AgentRankingError | None = None
    generation_summary: AgentTimetableGenerationSummary | None = None
    generation_failure_reasons: list[AgentGenerationFailureReason] = Field(default_factory=list)
    generation_truncated: bool = False
    validation_results: list[AgentValidationResult] = Field(default_factory=list)
    needs_confirmation: bool = False
    confirmation_request: ConfirmationRequest | None = None
    error: SessionStateAgentError | None = None


class SessionStateToolCall(BaseModel):
    """Tool call requested by the injected model."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)


class SessionStateModelResponse(BaseModel):
    """Normalized response from a tool-calling model."""

    model_config = ConfigDict(extra="forbid")

    tool_calls: list[SessionStateToolCall] = Field(default_factory=list)
    message: str | None = None
    unresolved_requests: list[UnresolvedSessionRequest] = Field(default_factory=list)


class SessionStateToolSpec(BaseModel):
    """Description passed to native or fake tool-calling models."""

    model_config = ConfigDict(extra="forbid")

    name: str
    description: str
    parameters: dict[str, Any]


class SessionStateToolset:
    """Registry of the session-state tools available to the agent."""

    def __init__(self, tools: Mapping[str, Callable[[Mapping[str, object]], Any]]) -> None:
        self._tools = dict(tools)

    @classmethod
    def from_query_and_command_tools(cls, queries: object, commands: object) -> "SessionStateToolset":
        return cls(
            {
                "get_session_summary": queries.get_session_summary,
                "set_department": commands.set_department,
                "register_major_catalog": commands.register_major_catalog,
                "register_elective_catalog": commands.register_elective_catalog,
                "add_selected_major_course": commands.add_selected_major_course,
                "remove_selected_major_course": commands.remove_selected_major_course,
                "replace_selected_major_courses": commands.replace_selected_major_courses,
                "add_required_free_day": commands.add_required_free_day,
                "remove_required_free_day": commands.remove_required_free_day,
                "replace_required_free_days": commands.replace_required_free_days,
                "set_earliest_start_time": commands.set_earliest_start_time,
                "clear_earliest_start_time": commands.clear_earliest_start_time,
                "set_latest_end_time": commands.set_latest_end_time,
                "clear_latest_end_time": commands.clear_latest_end_time,
                "add_required_course": commands.add_required_course,
                "remove_required_course": commands.remove_required_course,
                "add_excluded_course": commands.add_excluded_course,
                "remove_excluded_course": commands.remove_excluded_course,
                "clear_hard_constraints": commands.clear_hard_constraints,
                "add_preferred_free_day": commands.add_preferred_free_day,
                "remove_preferred_free_day": commands.remove_preferred_free_day,
                "replace_preferred_free_days": commands.replace_preferred_free_days,
                "set_preferred_earliest_start_time": commands.set_preferred_earliest_start_time,
                "clear_preferred_earliest_start_time": commands.clear_preferred_earliest_start_time,
                "set_preferred_latest_end_time": commands.set_preferred_latest_end_time,
                "clear_preferred_latest_end_time": commands.clear_preferred_latest_end_time,
                "add_preferred_course": commands.add_preferred_course,
                "remove_preferred_course": commands.remove_preferred_course,
                "add_disliked_course": commands.add_disliked_course,
                "remove_disliked_course": commands.remove_disliked_course,
                "set_compact_schedule_preference": commands.set_compact_schedule_preference,
                "clear_compact_schedule_preference": commands.clear_compact_schedule_preference,
                "clear_soft_preferences": commands.clear_soft_preferences,
                "clear_all_preferences": commands.clear_all_preferences,
            }
        )

    @classmethod
    def from_agent_and_discovery_tools(
        cls,
        session_tools: object,
        discovery_tools: object,
        timetable_tools: object | None = None,
        scoring_tools: object | None = None,
        selection_tools: object | None = None,
    ) -> "SessionStateToolset":
        tools = {
            "get_session_summary": session_tools.get_session_summary,
            "update_session_profile": session_tools.update_session_profile,
            "update_selected_major_courses": session_tools.update_selected_major_courses,
            "update_timetable_preferences": session_tools.update_timetable_preferences,
            "reset_session_preferences": session_tools.reset_session_preferences,
            "search_courses_by_name": discovery_tools.search_courses_by_name,
            "discover_courses": discovery_tools.discover_courses,
            "get_course_sections": discovery_tools.get_course_sections,
            "get_section_details": discovery_tools.get_section_details,
        }
        if timetable_tools is not None:
            tools.update(
                {
                    "confirm_timetable_conditions": session_tools.confirm_timetable_conditions,
                    "generate_timetable_candidates": timetable_tools.generate_timetable_candidates,
                    "validate_timetable_candidate": timetable_tools.validate_timetable_candidate,
                }
            )
        if selection_tools is not None:
            tools.update(
                {
                    "select_timetable_candidate": selection_tools.select_timetable_candidate,
                    "get_selected_timetable": selection_tools.get_selected_timetable,
                    "clear_selected_timetable": selection_tools.clear_selected_timetable,
                    "prepare_timetable_revision": selection_tools.prepare_timetable_revision,
                }
            )
        if scoring_tools is not None:
            tools.update(
                {
                    "score_timetable_candidate": scoring_tools.score_timetable_candidate,
                    "rank_timetable_candidates": scoring_tools.rank_timetable_candidates,
                }
            )
        return cls(tools)

    def has_tool(self, name: str) -> bool:
        return name in self._tools

    def run(self, name: str, arguments: Mapping[str, object]) -> SessionToolResult:
        return self._tools[name](arguments)

    def specs(self) -> list[SessionStateToolSpec]:
        return [
            SessionStateToolSpec(
                name=name,
                description=_TOOL_DESCRIPTIONS[name],
                parameters=_TOOL_INPUT_MODELS[name].model_json_schema(),
            )
            for name in self._tools
        ]


_TOOL_INPUT_MODELS: dict[str, type[BaseModel]] = {
    "get_session_summary": SessionIdInput,
    "update_session_profile": UpdateSessionProfileInput,
    "update_selected_major_courses": UpdateSelectedMajorCoursesInput,
    "update_timetable_preferences": UpdateTimetablePreferencesInput,
    "reset_session_preferences": ResetSessionPreferencesInput,
    "search_courses_by_name": SearchCoursesByNameInput,
    "discover_courses": CourseDiscoveryRequest,
    "get_course_sections": CourseSectionsInput,
    "get_section_details": SectionDetailsInput,
    "confirm_timetable_conditions": SessionIdInput,
    "generate_timetable_candidates": TimetableGenerationRequest,
    "validate_timetable_candidate": TimetableValidationRequest,
    "score_timetable_candidate": ScoreTimetableCandidateRequest,
    "rank_timetable_candidates": TimetableScoringRequest,
    "select_timetable_candidate": SelectTimetableCandidateInput,
    "get_selected_timetable": SessionIdInput,
    "clear_selected_timetable": SessionIdInput,
    "prepare_timetable_revision": TimetableRevisionRequest,
    "set_department": DepartmentInput,
    "register_major_catalog": CatalogInput,
    "register_elective_catalog": CatalogInput,
    "add_selected_major_course": CourseIdInput,
    "remove_selected_major_course": CourseIdInput,
    "replace_selected_major_courses": CourseIdsInput,
    "add_required_free_day": DayInput,
    "remove_required_free_day": DayInput,
    "replace_required_free_days": DaysInput,
    "set_earliest_start_time": TimeInput,
    "clear_earliest_start_time": SessionIdInput,
    "set_latest_end_time": TimeInput,
    "clear_latest_end_time": SessionIdInput,
    "add_required_course": CourseIdInput,
    "remove_required_course": CourseIdInput,
    "add_excluded_course": CourseIdInput,
    "remove_excluded_course": CourseIdInput,
    "clear_hard_constraints": SessionIdInput,
    "add_preferred_free_day": DayInput,
    "remove_preferred_free_day": DayInput,
    "replace_preferred_free_days": DaysInput,
    "set_preferred_earliest_start_time": TimeInput,
    "clear_preferred_earliest_start_time": SessionIdInput,
    "set_preferred_latest_end_time": TimeInput,
    "clear_preferred_latest_end_time": SessionIdInput,
    "add_preferred_course": CourseIdInput,
    "remove_preferred_course": CourseIdInput,
    "add_disliked_course": CourseIdInput,
    "remove_disliked_course": CourseIdInput,
    "set_compact_schedule_preference": BoolPreferenceInput,
    "clear_compact_schedule_preference": SessionIdInput,
    "clear_soft_preferences": SessionIdInput,
    "clear_all_preferences": SessionIdInput,
}

_TOOL_DESCRIPTIONS: dict[str, str] = {
    "get_session_summary": "Fetch the compact current session state. Required before and after mutations.",
    "update_session_profile": "Update explicit department or catalog id profile fields without replacing the whole session.",
    "update_selected_major_courses": "Add, remove, or replace resolved selected major course ids.",
    "update_timetable_preferences": "Apply one batched Hard/Soft timetable preference patch with service validation.",
    "reset_session_preferences": "Reset hard, soft, or all timetable preferences.",
    "search_courses_by_name": "Read-only search for a specific course name, course id, or course code in a catalog.",
    "discover_courses": "Read-only structured catalog discovery by optional query and filters.",
    "get_course_sections": "Read-only lookup of sections for one course id.",
    "get_section_details": "Read-only lookup of one concrete section id.",
    "confirm_timetable_conditions": "Confirm the current saved condition revision before timetable generation. Fails if required generation inputs are missing.",
    "generate_timetable_candidates": (
        "Generate timetable candidates from structured section sources. Use this only after concrete "
        "fixed_section_sources and candidate_section_sources_by_course are prepared. Do not pass the full "
        "natural-language message. Hard constraints filter candidates; Soft preferences are not scored or used "
        "as final ranking. The result is not saved to session state."
    ),
    "validate_timetable_candidate": (
        "Validate one concrete section combination against Hard rules. This read-only tool does not mutate "
        "session or catalog state, and Soft preference mismatches are not validation errors."
    ),
    "score_timetable_candidate": (
        "Structurally evaluate one Hard-valid timetable candidate against Soft preferences. This read-only "
        "tool does not replace Hard validation, does not mutate state, and returns comparison-only scores."
    ),
    "rank_timetable_candidates": (
        "Rank multiple Hard-valid timetable candidates by Soft preferences using only the scoring service. "
        "This read-only tool does not relax Hard constraints, does not choose a candidate, and does not save results."
    ),
    "select_timetable_candidate": (
        "???? ??? ??? ??? ?? ? ??? ????? ?? ???? ?? ????. "
        "ranking 1??? ????? ?? ???? ? ??. candidate_id? ????, "
        "Agent? candidate ?? ??? validation ??? ????? ? ??. ??? ???? "
        "Hard/Soft ??? ??? ?? ??? ????."
    ),
    "get_selected_timetable": "?? ??? ???? ????. ?? ?? ? ??? ?? ????.",
    "clear_selected_timetable": "???? ????? ?? ??? ???? ?? ?? ??? ??? ???. Hard/Soft ??? ??? ???.",
    "prepare_timetable_revision": (
        "?? ??? ???? ???? ?? ?? ?????? ???? ?? ???? ?? ????. "
        "??? Hard/Soft preference ???? ?? ??? ???? ???? ???. "
        "?? section? ???? ?? section? ???? ?????? ????. "
        "?? ??? ?? ??? scoring? ???? ??? ?? generate_timetable_candidates? "
        "rank_timetable_candidates? ???? ??."
    ),
    "set_department": "Set the user's department when the department text is explicit.",
    "register_major_catalog": "Store an already parsed major catalog id.",
    "register_elective_catalog": "Store an already parsed elective catalog id.",
    "add_selected_major_course": "Add one resolved selected major course id.",
    "remove_selected_major_course": "Remove one resolved selected major course id.",
    "replace_selected_major_courses": "Replace selected major course ids with resolved ids.",
    "add_required_free_day": "Add a Hard required free weekday.",
    "remove_required_free_day": "Remove a Hard required free weekday.",
    "replace_required_free_days": "Replace all Hard required free weekdays.",
    "set_earliest_start_time": "Set the Hard earliest allowed class start time.",
    "clear_earliest_start_time": "Clear the Hard earliest-start constraint.",
    "set_latest_end_time": "Set the Hard latest allowed class end time.",
    "clear_latest_end_time": "Clear the Hard latest-end constraint.",
    "add_required_course": "Add one resolved course id as a Hard required course.",
    "remove_required_course": "Remove one Hard required course id.",
    "add_excluded_course": "Add one resolved course id as a Hard excluded course.",
    "remove_excluded_course": "Remove one Hard excluded course id.",
    "clear_hard_constraints": "Clear all Hard constraints only.",
    "add_preferred_free_day": "Add a Soft preferred free weekday.",
    "remove_preferred_free_day": "Remove a Soft preferred free weekday.",
    "replace_preferred_free_days": "Replace all Soft preferred free weekdays.",
    "set_preferred_earliest_start_time": "Set the Soft preferred earliest class start time.",
    "clear_preferred_earliest_start_time": "Clear the Soft preferred earliest-start time.",
    "set_preferred_latest_end_time": "Set the Soft preferred latest class end time.",
    "clear_preferred_latest_end_time": "Clear the Soft preferred latest-end time.",
    "add_preferred_course": "Add one resolved course id as a Soft preferred course.",
    "remove_preferred_course": "Remove one Soft preferred course id.",
    "add_disliked_course": "Add one resolved course id as a Soft disliked course.",
    "remove_disliked_course": "Remove one Soft disliked course id.",
    "set_compact_schedule_preference": "Set whether compact schedules are softly preferred.",
    "clear_compact_schedule_preference": "Clear compact-schedule Soft preference.",
    "clear_soft_preferences": "Clear all Soft preferences only.",
    "clear_all_preferences": "Clear both Hard constraints and Soft preferences.",
}


class SessionStateAgent:
    """Run one tool-calling session-state agent turn."""

    def __init__(
        self,
        *,
        model: Any,
        tools: SessionStateToolset,
        max_mutation_tool_calls: int | None = None,
        max_tool_calls: int | None = None,
        system_prompt: str | None = None,
    ) -> None:
        if max_mutation_tool_calls is None:
            max_mutation_tool_calls = (
                DEFAULT_MAX_MUTATION_TOOL_CALLS
                if max_tool_calls is None
                else max_tool_calls
            )
        if max_tool_calls is None:
            max_tool_calls = DEFAULT_MAX_TOTAL_TOOL_CALLS
        if max_tool_calls < 1:
            raise ValueError("max_tool_calls must be at least 1")
        if max_mutation_tool_calls < 0:
            raise ValueError("max_mutation_tool_calls must not be negative")
        if max_mutation_tool_calls > max_tool_calls:
            raise ValueError("max_mutation_tool_calls must not exceed max_tool_calls")
        self.model = model
        self.tools = tools
        self.max_total_tool_calls = max_tool_calls
        self.max_mutation_tool_calls = max_mutation_tool_calls
        self.system_prompt = system_prompt or load_session_state_agent_prompt()

    def run(self, data: SessionStateAgentInput | Mapping[str, object]) -> SessionStateAgentResult:
        try:
            request = SessionStateAgentInput.model_validate(data)
        except ValidationError as exc:
            return self._input_error(exc)

        logger.info(
            "session_state_agent_started",
            extra={
                "session_id": request.session_id,
                "request_id": request.request_id,
            },
        )
        executed: list[ExecutedSessionTool] = []
        transcript: list[dict[str, Any]] = []
        unresolved_requests: list[UnresolvedSessionRequest] = []
        discovery_results: list[AgentDiscoveryResult] = []
        generation_results: list[tuple[TimetableGenerationRequest, TimetableGenerationResult]] = []
        validation_results: list[AgentValidationResult] = []
        ranking_results: list[tuple[TimetableScoringRequest | None, TimetableRankingResult]] = []
        changed = False
        mutation_tool_call_count = 0
        last_summary: SessionStateSummary | None = None

        try:
            initial = self._execute_tool(
                "get_session_summary",
                {"session_id": request.session_id},
                executed,
                request_id=request.request_id,
            )
        except Exception:
            return self._internal_tool_error(
                request,
                "get_session_summary",
                executed,
                last_summary,
                changed,
            )
        if not initial.result.success:
            return self._session_error(request, initial.result, executed)
        last_summary = initial.result.state_summary
        transcript.append(self._tool_transcript("get_session_summary", initial.result))

        while True:
            try:
                model_response = self._call_model(request, transcript, last_summary)
            except Exception:
                logger.exception(
                    "session_state_agent_model_failed",
                    extra={
                        "session_id": request.session_id,
                        "request_id": request.request_id,
                        "mutation_tool_call_count": mutation_tool_call_count,
                    },
                )
                return self._failure(
                    request,
                    "요청을 해석하는 중 오류가 발생했습니다.",
                    SessionStateAgentErrorCode.MODEL_CALL_FAILED,
                    executed,
                    last_summary,
                    changed,
                )

            unresolved_requests.extend(model_response.unresolved_requests)
            if not model_response.tool_calls:
                try:
                    final = self._execute_tool(
                        "get_session_summary",
                        {"session_id": request.session_id},
                        executed,
                        request_id=request.request_id,
                    )
                except Exception:
                    return self._internal_tool_error(
                        request,
                        "get_session_summary",
                        executed,
                        last_summary,
                        changed,
                    )
                if not final.result.success:
                    return self._tool_failure(request, final.result, executed, last_summary, changed)
                failed_tools = _failed_tools(executed)
                unresolved_requests.extend(
                    _unresolved_requests_from_failed_tools(failed_tools)
                )
                candidate_courses = _candidate_courses_from_discovery(discovery_results)
                generation_request, generation_result = (
                    generation_results[-1] if generation_results else (None, None)
                )
                ranking_request, ranking_result = (
                    ranking_results[-1] if ranking_results else (None, None)
                )
                confirmation_request = _confirmation_request_from_discovery(
                    discovery_results
                )
                generation_failure_reasons = (
                    _agent_generation_failure_reasons(generation_result.failure_reasons)
                    if generation_result is not None
                    else []
                )
                needs_confirmation = bool(
                    confirmation_request
                    or any(item.requires_user_confirmation for item in unresolved_requests)
                )
                message = self._final_message(
                    changed,
                    unresolved_requests,
                    failed_tools,
                    model_response.message,
                )
                partially_applied = bool(changed and (failed_tools or unresolved_requests))
                return SessionStateAgentResult(
                    success=not failed_tools,
                    session_id=request.session_id,
                    request_id=request.request_id,
                    message=message,
                    changed=changed,
                    partially_applied=partially_applied,
                    state_summary=final.result.state_summary,
                    executed_tools=executed,
                    failed_tools=failed_tools,
                    unresolved_requests=unresolved_requests,
                    discovery_results=discovery_results,
                    candidate_courses=candidate_courses,
                    timetable_candidates=(
                        _agent_timetable_candidates(generation_result.candidates)
                        if generation_result is not None
                        else []
                    ),
                    ranked_timetable_candidates=(
                        _agent_ranked_timetable_candidates(ranking_request, ranking_result)
                        if ranking_result is not None and ranking_result.success
                        else []
                    ),
                    ranking_summary=(
                        _agent_ranking_summary(ranking_request, ranking_result)
                        if ranking_result is not None
                        else None
                    ),
                    ranking_applied=ranking_result is not None and ranking_result.success,
                    effective_soft_preferences=(
                        ranking_request.soft_preferences.model_dump(mode="json")
                        if ranking_request is not None
                        else None
                    ),
                    ranking_error=(
                        _agent_ranking_error(ranking_result.error)
                        if ranking_result is not None and ranking_result.error is not None
                        else None
                    ),
                    generation_summary=(
                        _agent_generation_summary(generation_request, generation_result)
                        if generation_request is not None and generation_result is not None
                        else None
                    ),
                    generation_failure_reasons=generation_failure_reasons,
                    generation_truncated=(
                        False
                        if generation_result is None
                        else generation_result.search_truncated
                    ),
                    validation_results=validation_results,
                    needs_confirmation=needs_confirmation,
                    confirmation_request=confirmation_request,
                    error=(
                        None
                        if not failed_tools
                        else SessionStateAgentError(
                            code=SessionStateAgentErrorCode.TOOL_ERROR,
                            message="하나 이상의 도구 실행이 실패했습니다.",
                        )
                    ),
                )

            for tool_call in model_response.tool_calls:
                if not self.tools.has_tool(tool_call.name):
                    logger.warning(
                        "session_state_agent_unknown_tool",
                        extra={
                            "session_id": request.session_id,
                            "request_id": request.request_id,
                            "tool_name": tool_call.name,
                        },
                    )
                    return self._failure(
                        request,
                        f"모델이 등록되지 않은 도구를 요청했습니다: {tool_call.name}",
                        SessionStateAgentErrorCode.UNKNOWN_TOOL,
                        executed,
                        last_summary,
                        changed,
                        tool_name=tool_call.name,
                )

                arguments = {**tool_call.arguments}
                if (
                    tool_call.name == "rank_timetable_candidates"
                    and "soft_preferences" not in arguments
                    and last_summary is not None
                ):
                    arguments["soft_preferences"] = last_summary.soft_preferences.model_dump(mode="json")
                if "session_id" in _TOOL_INPUT_MODELS[tool_call.name].model_fields:
                    # Tool calls must operate on the URL session, never on a model-supplied session id.
                    arguments["session_id"] = request.session_id
                validation_error = self._validate_tool_arguments(tool_call.name, arguments)
                if validation_error is not None:
                    return self._invalid_tool_arguments(
                        request,
                        tool_call.name,
                        validation_error,
                        executed,
                        last_summary,
                        changed,
                    )

                if (
                    not self._is_read_only_tool(tool_call.name)
                    and mutation_tool_call_count >= self.max_mutation_tool_calls
                ):
                    return self._limit_error(request, executed, last_summary)
                if len(executed) >= self.max_total_tool_calls:
                    return self._limit_error(request, executed, last_summary)

                try:
                    result = self._execute_tool(
                        tool_call.name,
                        arguments,
                        executed,
                        request_id=request.request_id,
                    )
                except Exception:
                    return self._internal_tool_error(
                        request,
                        tool_call.name,
                        executed,
                        last_summary,
                        changed,
                    )
                if not self._is_read_only_tool(tool_call.name):
                    mutation_tool_call_count += 1
                discovery_result = _agent_discovery_result(tool_call.name, result.result)
                if discovery_result is not None:
                    discovery_results.append(discovery_result)
                generation_result = _generation_result(tool_call.name, arguments, result.result)
                if generation_result is not None:
                    generation_results.append(generation_result)
                validation_result = _validation_result(tool_call.name, result.result)
                if validation_result is not None:
                    validation_results.append(validation_result)
                ranking_result = _ranking_result(tool_call.name, arguments, result.result)
                if ranking_result is not None:
                    ranking_results.append(ranking_result)
                changed = changed or bool(getattr(result.result, "changed", False))
                state_summary = getattr(result.result, "state_summary", None)
                if state_summary is not None:
                    last_summary = state_summary
                transcript.append(self._tool_transcript(tool_call.name, result.result))

    def _call_model(
        self,
        request: SessionStateAgentInput,
        transcript: list[dict[str, Any]],
        current_summary: SessionStateSummary | None,
    ) -> SessionStateModelResponse:
        payload = {
            "messages": [
                {"role": "system", "content": self.system_prompt},
                {
                    "role": "user",
                    "content": {
                        "session_id": request.session_id,
                        "locale": request.locale,
                        "user_message": request.user_message,
                        "request_id": request.request_id,
                        "current_state_summary": (
                            None
                            if current_summary is None
                            else current_summary.model_dump(mode="json")
                        ),
                    },
                },
                *transcript,
            ],
            "tools": [spec.model_dump(mode="json") for spec in self.tools.specs()],
        }
        if hasattr(self.model, "invoke"):
            try:
                raw = self.model.invoke(payload["messages"], tools=payload["tools"])
            except TypeError:
                raw = self.model.invoke(payload)
        elif callable(self.model):
            raw = self.model(payload)
        else:
            raise TypeError("configured model is not invokable")
        return self._normalize_model_response(raw)

    def _execute_tool(
        self,
        name: str,
        arguments: Mapping[str, object],
        executed: list[ExecutedSessionTool],
        *,
        request_id: str | None,
    ) -> "_ToolExecution":
        result = self.tools.run(name, arguments)
        error = getattr(result, "error", None)
        changed = bool(getattr(result, "changed", False))
        success = _tool_execution_success(name, result)
        message = getattr(result, "message", None)
        session_id = getattr(result, "session_id", None) or arguments.get("session_id")
        error_code = None
        if error is not None:
            code = getattr(error, "code", None)
            error_code = getattr(code, "value", code)
        executed.append(
            ExecutedSessionTool(
                name=name,
                success=success,
                changed=changed,
                error_code=error_code,
                message=message,
                error_message=None if error is None else getattr(error, "message", None),
                error_field=None if error is None else getattr(error, "field", None),
                error_value=None if error is None else getattr(error, "value", None),
            )
        )
        logger.info(
            "session_state_agent_tool_executed",
            extra={
                "session_id": session_id,
                "request_id": request_id,
                "tool_name": name,
                "success": success,
                "changed": changed,
                "error_code": error_code,
                "executed_tool_count": len(executed),
            },
        )
        return _ToolExecution(result=result)

    @staticmethod
    def _normalize_model_response(raw: Any) -> SessionStateModelResponse:
        if isinstance(raw, SessionStateModelResponse):
            return raw
        if isinstance(raw, str):
            return SessionStateModelResponse.model_validate_json(raw)
        if isinstance(raw, Mapping):
            return SessionStateModelResponse.model_validate(raw)
        if hasattr(raw, "model_dump"):
            return SessionStateModelResponse.model_validate(raw.model_dump())
        tool_calls = getattr(raw, "tool_calls", None)
        content = getattr(raw, "content", None)
        if tool_calls is not None:
            normalized_calls = [
                {
                    "name": call.get("name") if isinstance(call, Mapping) else getattr(call, "name", ""),
                    "arguments": (
                        call.get("args", call.get("arguments", {}))
                        if isinstance(call, Mapping)
                        else getattr(call, "args", getattr(call, "arguments", {}))
                    ),
                }
                for call in tool_calls
            ]
            return SessionStateModelResponse(tool_calls=normalized_calls, message=content)
        raise TypeError(f"unsupported model response type: {type(raw).__name__}")

    @staticmethod
    def _validate_tool_arguments(name: str, arguments: Mapping[str, object]) -> ValidationError | None:
        try:
            _TOOL_INPUT_MODELS[name].model_validate(arguments)
        except ValidationError as exc:
            return exc
        return None

    @staticmethod
    def _tool_transcript(name: str, result: Any) -> dict[str, Any]:
        return {
            "role": "tool",
            "name": name,
            "content": result.model_dump(mode="json", exclude_none=True),
        }

    @staticmethod
    def _final_message(
        changed: bool,
        unresolved: list[UnresolvedSessionRequest],
        failed_tools: list[ExecutedSessionTool],
        model_message: str | None,
    ) -> str:
        if not failed_tools and not unresolved and model_message:
            return model_message
        if failed_tools:
            return _partial_or_failed_message(changed, failed_tools)
        return SessionStateAgent._default_message(changed, unresolved)

    @staticmethod
    def _default_message(changed: bool, unresolved: list[UnresolvedSessionRequest]) -> str:
        if changed:
            if unresolved:
                return "적용 가능한 조건을 세션에 반영했고, 일부 요청은 확인이 필요합니다."
            return "요청한 조건을 세션에 반영했습니다."
        if unresolved:
            return "현재 도구로 바로 적용할 수 없는 요청이 있어 확인이 필요합니다."
        return "세션 상태를 확인했습니다. 새로 변경된 조건은 없습니다."

    @staticmethod
    def _input_error(exc: ValidationError) -> SessionStateAgentResult:
        first = exc.errors()[0]
        field = ".".join(str(part) for part in first["loc"])
        return SessionStateAgentResult(
            success=False,
            session_id=None,
            request_id=None,
            message="입력값이 올바르지 않습니다.",
            error=SessionStateAgentError(
                code=SessionStateAgentErrorCode.INVALID_INPUT,
                message=str(first["msg"]),
                field=field,
            ),
        )

    @staticmethod
    def _session_error(
        request: SessionStateAgentInput,
        result: SessionToolResult,
        executed: list[ExecutedSessionTool],
    ) -> SessionStateAgentResult:
        error = _agent_error_from_tool_result(
            result,
            fallback_code=SessionStateAgentErrorCode.SESSION_NOT_AVAILABLE,
        )
        return SessionStateAgentResult(
            success=False,
            session_id=request.session_id,
            request_id=request.request_id,
            message="세션을 찾을 수 없거나 만료되었습니다.",
            executed_tools=executed,
            failed_tools=_failed_tools(executed),
            error=error,
        )

    @staticmethod
    def _tool_failure(
        request: SessionStateAgentInput,
        result: SessionToolResult,
        executed: list[ExecutedSessionTool],
        state_summary: SessionStateSummary | None,
        changed: bool,
    ) -> SessionStateAgentResult:
        return SessionStateAgentResult(
            success=False,
            session_id=request.session_id,
            request_id=request.request_id,
            message="최종 세션 상태를 확인하지 못했습니다.",
            changed=changed,
            partially_applied=changed,
            state_summary=state_summary,
            executed_tools=executed,
            failed_tools=_failed_tools(executed),
            error=_agent_error_from_tool_result(
                result,
                fallback_code=SessionStateAgentErrorCode.TOOL_ERROR,
            ),
        )

    @staticmethod
    def _failure(
        request: SessionStateAgentInput,
        message: str,
        code: SessionStateAgentErrorCode,
        executed: list[ExecutedSessionTool],
        state_summary: SessionStateSummary | None,
        changed: bool,
        *,
        tool_name: str | None = None,
    ) -> SessionStateAgentResult:
        return SessionStateAgentResult(
            success=False,
            session_id=request.session_id,
            request_id=request.request_id,
            message=message,
            changed=changed,
            partially_applied=changed and bool(_failed_tools(executed)),
            state_summary=state_summary,
            executed_tools=executed,
            failed_tools=_failed_tools(executed),
            error=SessionStateAgentError(
                code=code,
                message=message,
                tool_name=tool_name,
            ),
        )

    @staticmethod
    def _invalid_tool_arguments(
        request: SessionStateAgentInput,
        tool_name: str,
        exc: ValidationError,
        executed: list[ExecutedSessionTool],
        state_summary: SessionStateSummary | None,
        changed: bool,
    ) -> SessionStateAgentResult:
        first = exc.errors()[0]
        field = ".".join(str(part) for part in first["loc"])
        message = f"모델이 {tool_name} 도구에 올바르지 않은 인자를 생성했습니다."
        return SessionStateAgentResult(
            success=False,
            session_id=request.session_id,
            request_id=request.request_id,
            message=message,
            changed=changed,
            partially_applied=changed,
            state_summary=state_summary,
            executed_tools=executed,
            failed_tools=_failed_tools(executed),
            error=SessionStateAgentError(
                code=SessionStateAgentErrorCode.INVALID_TOOL_ARGUMENTS,
                message=str(first["msg"]),
                tool_name=tool_name,
                field=field,
            ),
        )

    @staticmethod
    def _internal_tool_error(
        request: SessionStateAgentInput,
        tool_name: str,
        executed: list[ExecutedSessionTool],
        state_summary: SessionStateSummary | None,
        changed: bool,
    ) -> SessionStateAgentResult:
        logger.exception(
            "session_state_agent_tool_unhandled_exception",
            extra={
                "session_id": request.session_id,
                "request_id": request.request_id,
                "tool_name": tool_name,
            },
        )
        return SessionStateAgentResult(
            success=False,
            session_id=request.session_id,
            request_id=request.request_id,
            message="도구 실행 중 오류가 발생했습니다.",
            changed=changed,
            partially_applied=changed,
            state_summary=state_summary,
            executed_tools=executed,
            failed_tools=_failed_tools(executed),
            error=SessionStateAgentError(
                code=SessionStateAgentErrorCode.INTERNAL_ERROR,
                message="internal tool execution error",
                tool_name=tool_name,
            ),
        )

    @staticmethod
    def _limit_error(
        request: SessionStateAgentInput,
        executed: list[ExecutedSessionTool],
        state_summary: SessionStateSummary | None,
    ) -> SessionStateAgentResult:
        changed = any(item.changed for item in executed)
        return SessionStateAgentResult(
            success=False,
            session_id=request.session_id,
            request_id=request.request_id,
            message="도구 호출 한도를 초과해 실행을 중단했습니다.",
            changed=changed,
            partially_applied=changed,
            state_summary=state_summary,
            executed_tools=executed,
            failed_tools=_failed_tools(executed),
            error=SessionStateAgentError(
                code=SessionStateAgentErrorCode.TOOL_CALL_LIMIT_EXCEEDED,
                message="tool call limit exceeded",
            ),
        )

    @staticmethod
    def _is_read_only_tool(name: str) -> bool:
        return name in READ_ONLY_TOOL_NAMES


class _ToolExecution(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    result: Any


def _agent_error_from_tool_result(
    result: SessionToolResult,
    *,
    fallback_code: SessionStateAgentErrorCode,
) -> SessionStateAgentError:
    if result.error is None:
        return SessionStateAgentError(
            code=fallback_code,
            message=result.message,
        )
    code = (
        SessionStateAgentErrorCode.SESSION_NOT_AVAILABLE
        if result.error.code.value == "SESSION_NOT_AVAILABLE"
        else fallback_code
    )
    return SessionStateAgentError(
        code=code,
        message=result.error.message,
        field=result.error.field,
        value=result.error.value,
    )


def _failed_tools(executed: list[ExecutedSessionTool]) -> list[ExecutedSessionTool]:
    return [tool for tool in executed if not tool.success]


def _tool_execution_success(name: str, result: Any) -> bool:
    if name == "generate_timetable_candidates":
        try:
            generation = TimetableGenerationResult.model_validate(
                result.model_dump() if hasattr(result, "model_dump") else result
            )
        except ValidationError:
            return False
        return generation.error is None
    if name == "validate_timetable_candidate":
        try:
            TimetableValidationResult.model_validate(
                result.model_dump() if hasattr(result, "model_dump") else result
            )
        except ValidationError:
            return False
        return True
    if name == "score_timetable_candidate":
        try:
            ScoredTimetableCandidate.model_validate(
                result.model_dump() if hasattr(result, "model_dump") else result
            )
            return True
        except ValidationError:
            return False
    if name == "rank_timetable_candidates":
        try:
            ranking = TimetableRankingResult.model_validate(
                result.model_dump() if hasattr(result, "model_dump") else result
            )
        except ValidationError:
            return False
        return ranking.success
    return bool(getattr(result, "success", False))


def _generation_result(
    tool_name: str,
    arguments: Mapping[str, object],
    result: Any,
) -> tuple[TimetableGenerationRequest, TimetableGenerationResult] | None:
    if tool_name != "generate_timetable_candidates":
        return None
    try:
        request = TimetableGenerationRequest.model_validate(arguments)
        generation = TimetableGenerationResult.model_validate(
            result.model_dump() if hasattr(result, "model_dump") else result
        )
    except ValidationError:
        logger.warning("session_state_agent_unexpected_generation_result")
        return None
    return request, generation


def _validation_result(
    tool_name: str,
    result: Any,
) -> AgentValidationResult | None:
    if tool_name != "validate_timetable_candidate":
        return None
    try:
        validation = TimetableValidationResult.model_validate(
            result.model_dump() if hasattr(result, "model_dump") else result
        )
    except ValidationError:
        logger.warning("session_state_agent_unexpected_validation_result")
        return None
    return AgentValidationResult(
        valid=validation.valid,
        checked_section_ids=list(validation.checked_section_ids),
        violation_codes=[violation.code.value for violation in validation.violations],
        violation_messages=[violation.message for violation in validation.violations[:3]],
    )


def _ranking_result(
    tool_name: str,
    arguments: Mapping[str, object],
    result: Any,
) -> tuple[TimetableScoringRequest | None, TimetableRankingResult] | None:
    if tool_name != "rank_timetable_candidates":
        return None
    try:
        request = TimetableScoringRequest.model_validate(arguments)
    except ValidationError:
        logger.warning("session_state_agent_unexpected_ranking_request")
        request = None
    try:
        ranking = TimetableRankingResult.model_validate(
            result.model_dump() if hasattr(result, "model_dump") else result
        )
    except ValidationError:
        logger.warning("session_state_agent_unexpected_ranking_result")
        return None
    return request, ranking


def _agent_ranked_timetable_candidates(
    request: TimetableScoringRequest | None,
    result: TimetableRankingResult,
) -> list[AgentRankedTimetableCandidate]:
    section_map = _resolved_section_map([] if request is None else request.sections)
    return [
        _agent_ranked_timetable_candidate(candidate, section_map)
        for candidate in result.ranked_candidates
    ]


def _agent_ranked_timetable_candidate(
    candidate: ScoredTimetableCandidate,
    section_map: dict[str, ResolvedSection],
) -> AgentRankedTimetableCandidate:
    return AgentRankedTimetableCandidate(
        rank=candidate.rank or 0,
        candidate_id=candidate.candidate_id,
        comparison_score=candidate.total_score,
        total_credits=candidate.candidate.total_credits,
        section_ids=list(candidate.candidate.section_ids),
        sections=[
            _agent_timetable_section(section)
            for section in _sections_for_candidate(candidate, section_map)
        ],
        score_components=[_agent_score_component(component) for component in candidate.score_components],
        satisfied_preferences=[
            _agent_scored_preference_evidence(evidence)
            for evidence in candidate.satisfied_preferences
        ],
        unsatisfied_preferences=[
            _agent_scored_preference_evidence(evidence)
            for evidence in candidate.unsatisfied_preferences
        ],
        trade_offs=[_agent_timetable_trade_off(trade_off) for trade_off in candidate.trade_offs],
        tie_breaker=dict(candidate.tie_breaker),
    )


def _resolved_section_map(sections: list[ResolvedSection]) -> dict[str, ResolvedSection]:
    mapping: dict[str, ResolvedSection] = {}
    for section in sections:
        mapping[section.source.key] = section
        mapping[section.section.section_id] = section
    return mapping


def _sections_for_candidate(
    candidate: ScoredTimetableCandidate,
    section_map: dict[str, ResolvedSection],
) -> list[ResolvedSection]:
    resolved: list[ResolvedSection] = []
    for source in candidate.candidate.section_sources:
        section = section_map.get(source.key) or section_map.get(source.section_id)
        if section is not None:
            resolved.append(section)
    if not resolved:
        for section_id in candidate.candidate.section_ids:
            section = section_map.get(section_id)
            if section is not None:
                resolved.append(section)
    return resolved


def _agent_timetable_section(section: ResolvedSection) -> AgentTimetableSection:
    course_section = section.section
    return AgentTimetableSection(
        catalog_id=section.catalog_id,
        section_id=course_section.section_id,
        course_id=course_section.course_id,
        course_code=course_section.course_code,
        course_name=course_section.course_name,
        division=course_section.division,
        professor=course_section.professor,
        credit=course_section.credit,
        class_times=[meeting.model_dump(mode="json") for meeting in course_section.class_times],
    )


def _agent_score_component(component: ScoreComponent) -> AgentScoreComponent:
    return AgentScoreComponent(
        code=component.code.value,
        label=component.label,
        score=component.score,
        satisfied=component.satisfied,
        details=dict(component.details),
    )


def _agent_scored_preference_evidence(
    evidence: PreferenceEvidence,
) -> AgentScoredPreferenceEvidence:
    return AgentScoredPreferenceEvidence(
        code=evidence.code.value,
        component_code=None if evidence.component_code is None else evidence.component_code.value,
        values=dict(evidence.values),
    )


def _agent_timetable_trade_off(trade_off: ScoringTradeOff) -> AgentTimetableTradeOff:
    return AgentTimetableTradeOff(
        code=trade_off.code.value,
        values=dict(trade_off.values),
    )


def _agent_ranking_summary(
    request: TimetableScoringRequest | None,
    result: TimetableRankingResult,
) -> AgentRankingSummary:
    scores = [candidate.total_score for candidate in result.ranked_candidates]
    return AgentRankingSummary(
        ranking_applied=result.success,
        evaluated_candidate_count=result.total_candidates,
        returned_candidate_count=result.returned_candidates,
        soft_preferences_present=(
            _soft_preferences_present(request.soft_preferences)
            if request is not None
            else False
        ),
        scoring_policy_id=result.scoring_policy.policy_id,
        highest_score=max(scores) if scores else None,
        lowest_score=min(scores) if scores else None,
        has_tied_scores=len(scores) != len(set(scores)),
        message=result.message,
    )


def _agent_ranking_error(error: TimetableScoringError) -> AgentRankingError:
    return AgentRankingError(
        code=error.code.value,
        message=error.message,
        candidate_id=error.candidate_id,
    )


def _soft_preferences_present(preferences: object) -> bool:
    data = preferences.model_dump(mode="json") if hasattr(preferences, "model_dump") else {}
    return any(bool(value) for value in data.values())

def _agent_generation_summary(
    request: TimetableGenerationRequest,
    result: TimetableGenerationResult,
) -> AgentTimetableGenerationSummary:
    applied_hard_constraints: dict[str, Any] = {}
    if request.required_course_ids:
        applied_hard_constraints["required_course_ids"] = list(request.required_course_ids)
    if request.excluded_course_ids:
        applied_hard_constraints["excluded_course_ids"] = list(request.excluded_course_ids)
    if request.required_free_days:
        applied_hard_constraints["required_free_days"] = [
            day.value for day in request.required_free_days
        ]
    if request.earliest_start_time is not None:
        applied_hard_constraints["earliest_start_time"] = request.earliest_start_time
    if request.latest_end_time is not None:
        applied_hard_constraints["latest_end_time"] = request.latest_end_time
    if request.department is not None:
        applied_hard_constraints["department"] = request.department
    return AgentTimetableGenerationSummary(
        generated_candidate_count=len(result.candidates),
        total_candidates_found=result.total_candidates_found,
        search_nodes_visited=result.search_nodes_visited,
        search_truncated=result.search_truncated,
        termination_reason=result.termination_reason.value,
        applied_hard_constraints=applied_hard_constraints,
        target_additional_course_count=request.target_additional_course_count,
        target_additional_credits=request.target_additional_credits,
    )


def _agent_timetable_candidates(
    candidates: list[GeneratedTimetableCandidate],
) -> list[AgentTimetableCandidate]:
    return [
        AgentTimetableCandidate(
            candidate_id=candidate.candidate_id,
            section_ids=list(candidate.section_ids),
            section_sources=[
                source.model_dump(mode="json") for source in candidate.section_sources
            ],
            fixed_section_ids=list(candidate.fixed_section_ids),
            fixed_section_sources=[
                source.model_dump(mode="json")
                for source in candidate.fixed_section_sources
            ],
            added_section_ids=list(candidate.added_section_ids),
            added_section_sources=[
                source.model_dump(mode="json")
                for source in candidate.added_section_sources
            ],
            course_ids=list(candidate.course_ids),
            total_credits=candidate.total_credits,
            valid=candidate.validation.valid,
            generation_order=candidate.generation_order,
        )
        for candidate in sorted(candidates, key=lambda item: item.generation_order)
    ]


def _agent_generation_failure_reasons(
    reasons: list[GenerationFailureReason],
    *,
    limit: int = 3,
) -> list[AgentGenerationFailureReason]:
    return [
        AgentGenerationFailureReason(
            code=reason.code.value,
            message=_generation_failure_message(reason),
            course_id=reason.course_id,
            section_id=reason.section_id,
            constraint=reason.constraint,
            count=reason.count,
        )
        for reason in reasons[:limit]
    ]


def _generation_failure_message(reason: GenerationFailureReason) -> str:
    messages = {
        GenerationFailureCode.FIXED_TIMETABLE_CONFLICT: (
            "선택한 전공 분반끼리 시간이 겹치거나 현재 Hard 조건과 충돌합니다."
        ),
        GenerationFailureCode.REQUIRED_COURSE_UNAVAILABLE: (
            "필수로 지정한 과목의 모든 분반이 현재 조건에서 사용할 수 없습니다."
        ),
        GenerationFailureCode.CAMPUS_MOVEMENT_VIOLATION: (
            "연속 수업 사이 캠퍼스 이동이 현재 이동 규칙상 어렵습니다."
        ),
        GenerationFailureCode.TARGET_COURSE_COUNT_UNREACHABLE: (
            "현재 후보와 조건으로는 요청한 과목 수를 채울 수 없습니다."
        ),
        GenerationFailureCode.TARGET_CREDITS_UNREACHABLE: (
            "현재 후보와 조건으로는 요청한 학점을 채울 수 없습니다."
        ),
        GenerationFailureCode.SEARCH_LIMIT_REACHED: (
            "탐색 제한에 도달해 현재 제한 안에서만 후보를 확인했습니다."
        ),
        GenerationFailureCode.INVALID_GENERATION_REQUEST: (
            "시간표 생성 요청의 section 또는 조건 구성이 올바르지 않습니다."
        ),
    }
    return messages.get(reason.code, reason.message)


def _unresolved_requests_from_failed_tools(
    failed_tools: list[ExecutedSessionTool],
) -> list[UnresolvedSessionRequest]:
    unresolved: list[UnresolvedSessionRequest] = []
    for tool in failed_tools:
        reason = tool.error_message or "도구 실행이 실패했습니다."
        unresolved.append(
            UnresolvedSessionRequest(
                source_text=f"도구 실행 실패: {tool.name}",
                reason=reason,
                needed_information=(
                    f"tool={tool.name}, error_code={tool.error_code or 'UNKNOWN'}"
                ),
                requires_user_confirmation=True,
            )
        )
    return unresolved


def _agent_discovery_result(
    tool_name: str,
    result: Any,
) -> AgentDiscoveryResult | None:
    if tool_name not in {"search_courses_by_name", "discover_courses"}:
        return None
    try:
        discovery = CourseDiscoveryResult.model_validate(
            result.model_dump() if hasattr(result, "model_dump") else result
        )
    except ValidationError:
        logger.warning(
            "session_state_agent_unexpected_discovery_result",
            extra={"tool_name": tool_name},
        )
        return None
    return AgentDiscoveryResult(
        tool_name=tool_name,
        catalog_id=discovery.catalog_id,
        resolution=discovery.resolution.value,
        total_matched_courses=discovery.total_matched_courses,
        returned_candidate_count=len(discovery.candidates),
        message=discovery.message,
        candidate_courses=[
            _agent_course_candidate(candidate) for candidate in discovery.candidates
        ],
    )


def _agent_course_candidate(candidate: CourseCandidate) -> AgentCourseCandidate:
    return AgentCourseCandidate(
        course_id=candidate.course_id,
        course_code=candidate.course_code,
        course_name=candidate.course_name,
        category=candidate.category.value,
        area=candidate.area,
        department=candidate.department,
        matching_section_count=candidate.matching_section_count,
        total_section_count=candidate.total_section_count,
        matching_section_ids=list(candidate.matching_section_ids),
        match_reasons=list(candidate.match_reasons),
    )


def _candidate_courses_from_discovery(
    discovery_results: list[AgentDiscoveryResult],
) -> list[AgentCourseCandidate]:
    candidates: list[AgentCourseCandidate] = []
    seen: set[tuple[str, str]] = set()
    for discovery in discovery_results:
        for candidate in discovery.candidate_courses:
            key = (discovery.catalog_id, candidate.course_id)
            if key in seen:
                continue
            seen.add(key)
            candidates.append(candidate)
    return candidates


def _confirmation_request_from_discovery(
    discovery_results: list[AgentDiscoveryResult],
) -> ConfirmationRequest | None:
    for discovery in discovery_results:
        if discovery.resolution != DiscoveryResolution.AMBIGUOUS.value:
            continue
        return ConfirmationRequest(
            reason="검색 결과가 여러 과목 후보로 나뉘어 자동으로 확정할 수 없습니다.",
            question="원하는 과목의 course_id, 과목코드 또는 과목명을 선택해 주세요.",
            candidates=discovery.candidate_courses,
        )
    return None


def _partial_or_failed_message(
    changed: bool,
    failed_tools: list[ExecutedSessionTool],
) -> str:
    failed_lines = [
        (
            f"{tool.name} 요청은 "
            f"{tool.error_code or 'UNKNOWN'} 오류로 적용하지 못했습니다."
        )
        for tool in failed_tools
    ]
    if changed:
        return "\n".join(
            [
                "일부 조건만 세션에 반영했습니다.",
                *failed_lines,
            ]
        )
    return "\n".join(
        [
            "요청한 조건을 세션에 반영하지 못했습니다.",
            *failed_lines,
        ]
    )


def load_session_state_agent_prompt() -> str:
    return SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")


def result_to_pretty_json(result: SessionStateAgentResult) -> str:
    return json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2)
