"""Models for deterministic Soft-preference timetable scoring.

Scores are internal comparison values for candidates from the same user
request. They are not probabilities, are not normalized to 100, and may be
negative so small differences are not erased by artificial bounds. Hard
constraints are handled before scoring; invalid candidates are rejected instead
of receiving a low score.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .session_preferences import SoftPreferences
from .timetable_generation import GeneratedTimetableCandidate, ResolvedSection


class ScoreComponentCode(str, Enum):
    PREFERRED_FREE_DAYS = "PREFERRED_FREE_DAYS"
    PREFERRED_START_TIME = "PREFERRED_START_TIME"
    PREFERRED_END_TIME = "PREFERRED_END_TIME"
    PREFERRED_COURSES = "PREFERRED_COURSES"
    DISLIKED_COURSES = "DISLIKED_COURSES"
    COMPACT_SCHEDULE = "COMPACT_SCHEDULE"


class PreferenceEvidenceCode(str, Enum):
    FREE_DAY_PREFERENCE_SATISFIED = "FREE_DAY_PREFERENCE_SATISFIED"
    FREE_DAY_PREFERENCE_UNSATISFIED = "FREE_DAY_PREFERENCE_UNSATISFIED"
    LATE_START_PREFERENCE_SATISFIED = "LATE_START_PREFERENCE_SATISFIED"
    LATE_START_PREFERENCE_UNSATISFIED = "LATE_START_PREFERENCE_UNSATISFIED"
    EARLY_END_PREFERENCE_SATISFIED = "EARLY_END_PREFERENCE_SATISFIED"
    EARLY_END_PREFERENCE_UNSATISFIED = "EARLY_END_PREFERENCE_UNSATISFIED"
    PREFERRED_COURSE_INCLUDED = "PREFERRED_COURSE_INCLUDED"
    PREFERRED_COURSE_MISSING = "PREFERRED_COURSE_MISSING"
    DISLIKED_COURSE_INCLUDED = "DISLIKED_COURSE_INCLUDED"
    COMPACT_SCHEDULE_STRONG = "COMPACT_SCHEDULE_STRONG"
    COMPACT_SCHEDULE_MODERATE = "COMPACT_SCHEDULE_MODERATE"
    COMPACT_SCHEDULE_WEAK = "COMPACT_SCHEDULE_WEAK"
    NO_SOFT_PREFERENCES = "NO_SOFT_PREFERENCES"


class ScoringErrorCode(str, Enum):
    INVALID_SCORING_REQUEST = "INVALID_SCORING_REQUEST"
    DUPLICATE_CANDIDATE_ID = "DUPLICATE_CANDIDATE_ID"
    INVALID_CANDIDATE = "INVALID_CANDIDATE"
    SECTION_DETAILS_MISSING = "SECTION_DETAILS_MISSING"


class _Model(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )


class TimetableScoringPolicy(_Model):
    """Linear, additive scoring policy for Soft preferences.

    Defaults intentionally avoid 0..100 normalization. Start/end penalties are
    proportional to minutes outside the preferred window. Compact schedule
    subtracts gap minutes and an extra penalty for each long in-day gap; it only
    applies when ``SoftPreferences.compact_schedule`` is ``True``.

    Tie-breaking is handled by ``TimetableRankingService`` in this order:
    satisfied evidence count, disliked course count, total gap minutes, latest
    end time, then stable candidate id.
    """

    policy_id: str = "default_soft_preference_v1"
    preferred_free_day_weight: int = Field(default=12, ge=0)
    preferred_start_time_weight: int = Field(default=10, ge=0)
    early_start_penalty_per_minute: float = Field(default=0.1, ge=0)
    preferred_end_time_weight: int = Field(default=10, ge=0)
    late_end_penalty_per_minute: float = Field(default=0.1, ge=0)
    preferred_course_weight: int = Field(default=8, ge=0)
    missed_preferred_course_penalty: int = Field(default=0, ge=0)
    disliked_course_penalty: int = Field(default=15, ge=0)
    compact_schedule_weight: int = Field(default=8, ge=0)
    gap_penalty_per_minute: float = Field(default=0.05, ge=0)
    long_gap_threshold_minutes: int = Field(default=120, ge=0)
    long_gap_penalty: int = Field(default=5, ge=0)


class PreferenceEvidence(_Model):
    code: PreferenceEvidenceCode
    component_code: ScoreComponentCode | None = None
    values: dict[str, Any] = Field(default_factory=dict)


class ScoreComponent(_Model):
    code: ScoreComponentCode
    label: str = Field(min_length=1)
    score: float
    weight: float
    satisfied: bool
    details: dict[str, Any] = Field(default_factory=dict)


class ScoringTradeOff(_Model):
    code: PreferenceEvidenceCode
    values: dict[str, Any] = Field(default_factory=dict)


class ScoredTimetableCandidate(_Model):
    candidate_id: str
    candidate: GeneratedTimetableCandidate
    total_score: float
    score_components: list[ScoreComponent] = Field(default_factory=list)
    satisfied_preferences: list[PreferenceEvidence] = Field(default_factory=list)
    unsatisfied_preferences: list[PreferenceEvidence] = Field(default_factory=list)
    trade_offs: list[ScoringTradeOff] = Field(default_factory=list)
    rank: int | None = None
    tie_breaker: dict[str, Any] = Field(default_factory=dict)


class TimetableScoringError(_Model):
    code: ScoringErrorCode
    message: str
    candidate_id: str | None = None


class TimetableScoringRequest(_Model):
    candidates: list[GeneratedTimetableCandidate] = Field(default_factory=list)
    sections: list[ResolvedSection] = Field(default_factory=list)
    soft_preferences: SoftPreferences = Field(default_factory=SoftPreferences)
    max_ranked_results: int = Field(default=3, ge=1, le=5)
    scoring_policy: TimetableScoringPolicy = Field(default_factory=TimetableScoringPolicy)

    @field_validator("candidates")
    @classmethod
    def reject_duplicate_candidate_ids(
        cls,
        values: list[GeneratedTimetableCandidate],
    ) -> list[GeneratedTimetableCandidate]:
        ids = [candidate.candidate_id for candidate in values]
        duplicates = sorted({candidate_id for candidate_id in ids if ids.count(candidate_id) > 1})
        if duplicates:
            raise ValueError("duplicate candidate ids are not allowed: " + ", ".join(duplicates))
        return values


class TimetableRankingResult(_Model):
    success: bool
    ranked_candidates: list[ScoredTimetableCandidate] = Field(default_factory=list)
    total_candidates: int = Field(default=0, ge=0)
    returned_candidates: int = Field(default=0, ge=0)
    scoring_policy: TimetableScoringPolicy = Field(default_factory=TimetableScoringPolicy)
    message: str
    error: TimetableScoringError | None = None

    @model_validator(mode="after")
    def validate_counts(self) -> "TimetableRankingResult":
        if self.returned_candidates != len(self.ranked_candidates):
            raise ValueError("returned_candidates must match ranked_candidates length")
        return self
