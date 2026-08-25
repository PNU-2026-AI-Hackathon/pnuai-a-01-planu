"""Request/response schemas for timetable recommendation."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from ..models.course_load import CourseLoadTarget
from ..models.preference import PreferenceRules, PreferenceWarning, UnsupportedCondition
from ..models.timetable import (
    CourseLoadSatisfaction,
    RankingDiagnostic,
    RankingResult,
    RankingTemplate,
    ScoreComponent,
    Timetable,
    TimetableGenerationResult,
)
from ..services.session_store import SessionStage


class RecommendRequest(BaseModel):
    """Legacy input shape from the earlier ``POST /recommend`` design.

    ``selected_preferences`` comes from explicit UI controls. ``free_text`` is
    passed to the LLM only to extract additional rules not covered by the UI.
    TODO: Keep this schema until older clients are retired or a full combined
    recommendation route is restored. The active MVP route is
    ``POST /recommend/generate`` and uses ``preference_prompt``.
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    session_id: str = Field(min_length=1)
    required_general_count: int = Field(default=0, ge=0)
    elective_general_count: int = Field(default=0, ge=0)
    selected_preferences: PreferenceRules = Field(default_factory=PreferenceRules)
    free_text: str = Field(default="", max_length=1000)

    @property
    def user_prompt(self) -> str:
        """Backward-compatible alias for earlier design docs."""

        return self.free_text


class RecommendResponse(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    recommendations: list[RankingResult]


class TimetableGenerationRequest(BaseModel):
    """Input for generating valid timetable candidates before ranking."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    session_id: str = Field(min_length=1)
    target_total_credits: float | None = Field(default=None, gt=0)
    additional_elective_count: int | None = Field(default=None, ge=0)
    hard_conditions: PreferenceRules = Field(default_factory=PreferenceRules)
    preference_prompt: str = Field(default="", max_length=2000)
    max_candidates: int | None = Field(default=None, gt=0)

    def course_load_target(self) -> CourseLoadTarget:
        if (
            self.target_total_credits is None
            and self.additional_elective_count is None
        ):
            return CourseLoadTarget.mvp_default_policy()
        return CourseLoadTarget(
            target_total_credits=self.target_total_credits,
            additional_elective_count=self.additional_elective_count,
        )


class TimetableGenerationResponse(TimetableGenerationResult):
    """Response returned by ``POST /recommend/generate``."""

    session_stage: SessionStage
    hard_conditions: PreferenceRules = Field(default_factory=PreferenceRules)
    soft_conditions: PreferenceRules = Field(default_factory=PreferenceRules)
    unsupported_conditions: list[UnsupportedCondition] = Field(default_factory=list)
    warnings: list[PreferenceWarning] = Field(default_factory=list)


class TimetableRankingRequest(BaseModel):
    """Input for ranking candidates already stored in a session."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    session_id: str = Field(min_length=1)
    template: RankingTemplate | str = RankingTemplate.BALANCED
    top_n: int = 3


class RankedTimetableResponse(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    candidate_id: str = Field(min_length=1)
    rank: int = Field(ge=1)
    timetable: Timetable
    raw_score: float
    score_components: list[ScoreComponent]
    load_satisfaction: CourseLoadSatisfaction


class TimetableRankingResponse(BaseModel):
    """Response returned by ``POST /recommend/rank``."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    session_id: str
    template: RankingTemplate
    template_name: str
    template_description: str
    ranked_candidates: list[RankedTimetableResponse]
    requested_top_n: int
    returned_count: int
    total_candidate_count: int
    diagnostics: list[RankingDiagnostic]
    unsupported_conditions: list[UnsupportedCondition]
    warnings: list[PreferenceWarning]
    session_stage: SessionStage
