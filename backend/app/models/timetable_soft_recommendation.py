"""Data contracts for deterministic Soft Preference recommendation analysis."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .course import Day, time_to_minutes


RECOMMENDATION_POLICY_VERSION = "soft_preference_recommendation_v1"


class SoftPreferenceRecommendationField(str, Enum):
    """Durable SoftPreferences fields that recommendation analysis may target."""

    PREFERRED_FREE_DAYS = "preferred_free_days"
    PREFERRED_EARLIEST_START_TIME = "preferred_earliest_start_time"
    PREFERRED_LATEST_END_TIME = "preferred_latest_end_time"
    PREFERRED_COURSE_IDS = "preferred_course_ids"
    DISLIKED_COURSE_IDS = "disliked_course_ids"
    COMPACT_SCHEDULE = "compact_schedule"


class SoftPreferenceFeedbackTarget(str, Enum):
    """Structured feedback target accepted by deterministic recommendation analysis."""

    DIFFERENT_TOP_CANDIDATES = "different_top_candidates"
    ADDRESS_COMMON_WEAKNESS = "address_common_weakness"
    DIFFERENT_FREE_DAY = "different_free_day"
    LATER_START = "later_start"
    EARLIER_END = "earlier_end"
    PREFER_COURSE = "prefer_course"
    AVOID_COURSE = "avoid_course"
    MORE_COMPACT = "more_compact"
    LESS_COMPACT = "less_compact"


class SoftPreferenceSuggestionBasis(str, Enum):
    """Why a recommendation was considered."""

    STRUCTURED_USER_FEEDBACK = "structured_user_feedback"
    COMMON_CURRENT_TOP_WEAKNESS = "common_current_top_weakness"
    ALTERNATIVE_RANKING_COMPARISON = "alternative_ranking_comparison"


class SoftPreferenceSuggestionOperation(str, Enum):
    """Atomic operation proposed for one Soft Preference field."""

    ADD_VALUE = "add_value"
    REMOVE_VALUE = "remove_value"
    REPLACE_VALUE = "replace_value"
    SET_VALUE = "set_value"
    CLEAR_VALUE = "clear_value"


class SoftPreferenceRecommendationMetricCode(str, Enum):
    """Metric codes backed by current timetable scoring details."""

    TOTAL_SCORE = "total_score"
    SATISFIED_PREFERENCE_COUNT = "satisfied_preference_count"
    UNSATISFIED_PREFERENCE_COUNT = "unsatisfied_preference_count"
    PREFERRED_FREE_DAY_SATISFIED_COUNT = "preferred_free_day_satisfied_count"
    PREFERRED_FREE_DAY_UNSATISFIED_COUNT = "preferred_free_day_unsatisfied_count"
    TOTAL_EARLY_MINUTES = "total_early_minutes"
    MAX_EARLY_START_DIFFERENCE_MINUTES = "max_early_start_difference_minutes"
    TOTAL_LATE_MINUTES = "total_late_minutes"
    MAX_LATE_END_DIFFERENCE_MINUTES = "max_late_end_difference_minutes"
    PREFERRED_COURSE_INCLUDED_COUNT = "preferred_course_included_count"
    PREFERRED_COURSE_MISSING_COUNT = "preferred_course_missing_count"
    DISLIKED_COURSE_INCLUDED_COUNT = "disliked_course_included_count"
    TOTAL_GAP_MINUTES = "total_gap_minutes"
    LONG_GAP_COUNT = "long_gap_count"
    SHORT_GAP_COUNT = "short_gap_count"


class SoftPreferenceMetricDirection(str, Enum):
    HIGHER_IS_BETTER = "higher_is_better"
    LOWER_IS_BETTER = "lower_is_better"
    CHANGED_ONLY = "changed_only"


class SoftPreferenceRecommendationBlockedCode(str, Enum):
    NO_CANDIDATES = "no_candidates"
    NO_ANALYZABLE_CANDIDATE_SET = "no_analyzable_candidate_set"
    HARD_CONSTRAINT_CAUSE = "hard_constraint_cause"
    NO_SUPPORTED_SOFT_PREFERENCES = "no_supported_soft_preferences"
    INSUFFICIENT_SCORE_EVIDENCE = "insufficient_score_evidence"
    NO_EFFECTIVE_CHANGE = "no_effective_change"
    ALL_CHANGEABLE_FIELDS_PROTECTED = "all_changeable_fields_protected"
    NOT_DETERMINABLE_WITH_CURRENT_DATA = "not_determinable_with_current_data"


class _Model(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )


SoftPreferenceValue = list[Day] | list[str] | str | bool | None
MetricValue = int | float | bool


class SoftPreferenceRecommendationRequest(_Model):
    """Read-only request to analyze possible Soft Preference adjustments."""

    session_id: str = Field(min_length=1)
    feedback_target: SoftPreferenceFeedbackTarget | None = None
    protected_soft_preferences: list[SoftPreferenceRecommendationField] = Field(
        default_factory=list,
        description="Soft Preference fields that analysis must not suggest changing.",
    )
    max_suggestions: int = Field(default=3, ge=1, le=3)

    @field_validator("protected_soft_preferences")
    @classmethod
    def dedupe_protected_fields(
        cls,
        values: list[SoftPreferenceRecommendationField],
    ) -> list[SoftPreferenceRecommendationField]:
        return list(dict.fromkeys(values))


class SoftPreferenceRecommendationMetric(_Model):
    """One comparable metric produced from current scoring structures."""

    code: SoftPreferenceRecommendationMetricCode
    value: MetricValue
    direction: SoftPreferenceMetricDirection
    candidate_count: int | None = Field(default=None, ge=0)


class SoftPreferenceRecommendationEvidence(_Model):
    """Structured before/after evidence for a proposed adjustment."""

    before_top_candidate_ids: list[str] = Field(default_factory=list)
    after_top_candidate_ids: list[str] = Field(default_factory=list)
    top_candidates_changed: bool
    before_metrics: list[SoftPreferenceRecommendationMetric] = Field(default_factory=list)
    after_metrics: list[SoftPreferenceRecommendationMetric] = Field(default_factory=list)
    improved_metrics: list[SoftPreferenceRecommendationMetric] = Field(default_factory=list)
    worsened_metrics: list[SoftPreferenceRecommendationMetric] = Field(default_factory=list)

    @field_validator("before_top_candidate_ids", "after_top_candidate_ids")
    @classmethod
    def validate_candidate_ids(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("candidate id lists must not contain empty values")
        return values

    @model_validator(mode="after")
    def validate_metric_pairs(self) -> "SoftPreferenceRecommendationEvidence":
        before_codes = {metric.code for metric in self.before_metrics}
        after_codes = {metric.code for metric in self.after_metrics}
        for metric in [*self.improved_metrics, *self.worsened_metrics]:
            if metric.code not in before_codes or metric.code not in after_codes:
                raise ValueError(
                    "improved and worsened metrics must exist in both before_metrics and after_metrics"
                )
        return self


class SoftPreferenceRecommendation(_Model):
    """One atomic recommendation for changing exactly one Soft Preference field."""

    suggestion_id: str = Field(min_length=1)
    basis: SoftPreferenceSuggestionBasis
    field: SoftPreferenceRecommendationField
    operation: SoftPreferenceSuggestionOperation
    current_value: SoftPreferenceValue = None
    suggested_value: SoftPreferenceValue = None
    reason: str = Field(min_length=1)
    expected_benefit: str = Field(min_length=1)
    tradeoff: str | None = None
    evidence: SoftPreferenceRecommendationEvidence

    @field_validator("suggestion_id")
    @classmethod
    def validate_suggestion_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("suggestion_id must not be empty")
        return value

    @model_validator(mode="after")
    def validate_field_operation_and_values(self) -> "SoftPreferenceRecommendation":
        allowed = _ALLOWED_OPERATIONS_BY_FIELD[self.field]
        if self.operation not in allowed:
            raise ValueError(
                f"operation {self.operation.value} is not allowed for {self.field.value}"
            )
        _validate_soft_preference_value(
            self.field,
            self.current_value,
            value_name="current_value",
            allow_none=True,
        )
        _validate_soft_preference_value(
            self.field,
            self.suggested_value,
            value_name="suggested_value",
            allow_none=self.operation is SoftPreferenceSuggestionOperation.CLEAR_VALUE,
        )
        if self.operation is SoftPreferenceSuggestionOperation.CLEAR_VALUE and self.suggested_value is not None:
            raise ValueError("clear_value suggestions must use suggested_value=null")
        return self


class SoftPreferenceRecommendationBlockedReason(_Model):
    """Why recommendation analysis could not produce suggestions."""

    code: SoftPreferenceRecommendationBlockedCode
    message: str = Field(min_length=1)
    details: dict[str, Any] = Field(default_factory=dict)


class SoftPreferenceRecommendationResult(_Model):
    """Read-only recommendation analysis result."""

    suggestions: list[SoftPreferenceRecommendation] = Field(default_factory=list, max_length=3)
    blocked_reasons: list[SoftPreferenceRecommendationBlockedReason] = Field(default_factory=list)
    analyzed_candidate_count: int = Field(ge=0)
    current_top_candidate_ids: list[str] = Field(default_factory=list)
    recommendation_policy_version: str = RECOMMENDATION_POLICY_VERSION

    @field_validator("current_top_candidate_ids")
    @classmethod
    def validate_current_top_candidate_ids(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("current_top_candidate_ids must not contain empty values")
        return values

    @model_validator(mode="after")
    def validate_result_shape(self) -> "SoftPreferenceRecommendationResult":
        suggestion_ids = [suggestion.suggestion_id for suggestion in self.suggestions]
        duplicates = sorted(
            {suggestion_id for suggestion_id in suggestion_ids if suggestion_ids.count(suggestion_id) > 1}
        )
        if duplicates:
            raise ValueError("duplicate suggestion_id values are not allowed: " + ", ".join(duplicates))
        if not self.suggestions and not self.blocked_reasons:
            raise ValueError("blocked_reasons are required when suggestions is empty")
        return self


_ALLOWED_OPERATIONS_BY_FIELD: dict[
    SoftPreferenceRecommendationField,
    set[SoftPreferenceSuggestionOperation],
] = {
    SoftPreferenceRecommendationField.PREFERRED_FREE_DAYS: {
        SoftPreferenceSuggestionOperation.ADD_VALUE,
        SoftPreferenceSuggestionOperation.REMOVE_VALUE,
        SoftPreferenceSuggestionOperation.REPLACE_VALUE,
        SoftPreferenceSuggestionOperation.CLEAR_VALUE,
    },
    SoftPreferenceRecommendationField.PREFERRED_EARLIEST_START_TIME: {
        SoftPreferenceSuggestionOperation.SET_VALUE,
        SoftPreferenceSuggestionOperation.CLEAR_VALUE,
    },
    SoftPreferenceRecommendationField.PREFERRED_LATEST_END_TIME: {
        SoftPreferenceSuggestionOperation.SET_VALUE,
        SoftPreferenceSuggestionOperation.CLEAR_VALUE,
    },
    SoftPreferenceRecommendationField.PREFERRED_COURSE_IDS: {
        SoftPreferenceSuggestionOperation.ADD_VALUE,
        SoftPreferenceSuggestionOperation.REMOVE_VALUE,
        SoftPreferenceSuggestionOperation.REPLACE_VALUE,
        SoftPreferenceSuggestionOperation.CLEAR_VALUE,
    },
    SoftPreferenceRecommendationField.DISLIKED_COURSE_IDS: {
        SoftPreferenceSuggestionOperation.ADD_VALUE,
        SoftPreferenceSuggestionOperation.REMOVE_VALUE,
        SoftPreferenceSuggestionOperation.REPLACE_VALUE,
        SoftPreferenceSuggestionOperation.CLEAR_VALUE,
    },
    SoftPreferenceRecommendationField.COMPACT_SCHEDULE: {
        SoftPreferenceSuggestionOperation.SET_VALUE,
        SoftPreferenceSuggestionOperation.CLEAR_VALUE,
    },
}


def _validate_soft_preference_value(
    field: SoftPreferenceRecommendationField,
    value: SoftPreferenceValue,
    *,
    value_name: str,
    allow_none: bool,
) -> None:
    if value is None:
        if allow_none:
            return
        raise ValueError(f"{value_name} must not be null for {field.value}")

    if field is SoftPreferenceRecommendationField.PREFERRED_FREE_DAYS:
        if not isinstance(value, list) or not all(isinstance(item, Day) for item in value):
            raise ValueError(f"{value_name} for {field.value} must be a list of Day values")
        return

    if field in {
        SoftPreferenceRecommendationField.PREFERRED_COURSE_IDS,
        SoftPreferenceRecommendationField.DISLIKED_COURSE_IDS,
    }:
        if (
            not isinstance(value, list)
            or not all(isinstance(item, str) and item.strip() for item in value)
        ):
            raise ValueError(f"{value_name} for {field.value} must be a list of non-empty course ids")
        return

    if field in {
        SoftPreferenceRecommendationField.PREFERRED_EARLIEST_START_TIME,
        SoftPreferenceRecommendationField.PREFERRED_LATEST_END_TIME,
    }:
        if not isinstance(value, str):
            raise ValueError(f"{value_name} for {field.value} must be a HH:MM string")
        time_to_minutes(value)
        return

    if field is SoftPreferenceRecommendationField.COMPACT_SCHEDULE:
        if not isinstance(value, bool):
            raise ValueError(f"{value_name} for {field.value} must be a boolean")
        return

    raise ValueError(f"unsupported Soft Preference field: {field.value}")

