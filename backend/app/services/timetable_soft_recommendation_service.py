"""Deterministic analysis for Soft Preference adjustment recommendations."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from hashlib import sha256
from typing import Any

from ..models.course import Day
from ..models.planu_session_state import PlanuSessionState
from ..models.session_preferences import HardConstraints, SoftPreferences
from ..models.timetable_generation import GeneratedTimetableCandidate, ResolvedSection
from ..models.timetable_scoring import (
    ScoreComponentCode,
    ScoredTimetableCandidate,
    TimetableScoringRequest,
)
from ..models.timetable_soft_recommendation import (
    SoftPreferenceFeedbackTarget,
    SoftPreferenceMetricDirection,
    SoftPreferenceRecommendation,
    SoftPreferenceRecommendationBlockedCode,
    SoftPreferenceRecommendationBlockedReason,
    SoftPreferenceRecommendationEvidence,
    SoftPreferenceRecommendationField,
    SoftPreferenceRecommendationMetric,
    SoftPreferenceRecommendationMetricCode,
    SoftPreferenceRecommendationRequest,
    SoftPreferenceRecommendationResult,
    SoftPreferenceSuggestionBasis,
    SoftPreferenceSuggestionOperation,
)
from .timetable_soft_ranking_service import TimetableRankingService


TOP_CANDIDATE_COUNT = 3


@dataclass(frozen=True)
class _Adjustment:
    field: SoftPreferenceRecommendationField
    operation: SoftPreferenceSuggestionOperation
    suggested_value: object
    basis: SoftPreferenceSuggestionBasis
    feedback_match: bool
    common_weakness: bool


@dataclass(frozen=True)
class _EvaluatedAdjustment:
    suggestion: SoftPreferenceRecommendation
    sort_key: tuple[object, ...]


class TimetableSoftRecommendationService:
    """Compare one valid candidate set under alternative SoftPreferences."""

    def __init__(
        self,
        *,
        ranking_service: TimetableRankingService | None = None,
    ) -> None:
        self._ranking_service = ranking_service or TimetableRankingService()

    def analyze_session(
        self,
        *,
        request: SoftPreferenceRecommendationRequest,
        state: PlanuSessionState,
        candidates: Iterable[GeneratedTimetableCandidate],
        sections: Iterable[ResolvedSection],
    ) -> SoftPreferenceRecommendationResult:
        """Analyze a session snapshot without mutating it."""

        return self.analyze(
            request=request,
            candidates=candidates,
            sections=sections,
            soft_preferences=state.soft_preferences,
            hard_constraints=state.hard_constraints,
        )

    def analyze(
        self,
        *,
        request: SoftPreferenceRecommendationRequest,
        candidates: Iterable[GeneratedTimetableCandidate],
        sections: Iterable[ResolvedSection],
        soft_preferences: SoftPreferences,
        hard_constraints: HardConstraints | None = None,
    ) -> SoftPreferenceRecommendationResult:
        """Return supported Soft Preference adjustments for the same valid candidates."""

        candidate_copies = [candidate.model_copy(deep=True) for candidate in candidates]
        section_copies = [section.model_copy(deep=True) for section in sections]
        current_soft = soft_preferences.model_copy(deep=True)
        _ = None if hard_constraints is None else hard_constraints.model_copy(deep=True)

        if not candidate_copies:
            return self._blocked(
                request,
                SoftPreferenceRecommendationBlockedCode.NO_CANDIDATES,
                "분석할 시간표 후보가 없습니다.",
                analyzed_candidate_count=0,
            )

        valid_candidates = [
            candidate
            for candidate in candidate_copies
            if candidate.validation.valid
        ]
        if not valid_candidates:
            return self._blocked(
                request,
                SoftPreferenceRecommendationBlockedCode.HARD_CONSTRAINT_CAUSE,
                "현재 유효 후보가 없어 Soft Preference 변경으로 해결할 수 없습니다.",
                analyzed_candidate_count=0,
            )

        protected = set(request.protected_soft_preferences)
        if protected == set(SoftPreferenceRecommendationField):
            return self._blocked(
                request,
                SoftPreferenceRecommendationBlockedCode.ALL_CHANGEABLE_FIELDS_PROTECTED,
                "변경 가능한 Soft Preference가 모두 보호되어 있습니다.",
                analyzed_candidate_count=len(valid_candidates),
            )

        current_ranking = self._rank(valid_candidates, section_copies, current_soft)
        if current_ranking is None or not current_ranking:
            return self._blocked(
                request,
                SoftPreferenceRecommendationBlockedCode.INSUFFICIENT_SCORE_EVIDENCE,
                "현재 후보의 점수 근거를 만들 수 없습니다.",
                analyzed_candidate_count=len(valid_candidates),
            )
        current_top = current_ranking[:TOP_CANDIDATE_COUNT]
        current_top_ids = [candidate.candidate_id for candidate in current_top]

        adjustments = self._build_adjustments(
            request=request,
            candidates=valid_candidates,
            sections=section_copies,
            current_soft=current_soft,
            current_top=current_top,
            protected=protected,
        )
        if not adjustments:
            code = (
                SoftPreferenceRecommendationBlockedCode.ALL_CHANGEABLE_FIELDS_PROTECTED
                if protected
                else SoftPreferenceRecommendationBlockedCode.INSUFFICIENT_SCORE_EVIDENCE
            )
            return self._blocked(
                request,
                code,
                "근거가 있는 Soft Preference 변경 후보가 없습니다.",
                analyzed_candidate_count=len(valid_candidates),
                current_top_candidate_ids=current_top_ids,
            )

        evaluated: list[_EvaluatedAdjustment] = []
        for adjustment in adjustments:
            next_soft = self._apply_adjustment(current_soft, adjustment)
            if next_soft == current_soft:
                continue
            next_ranking = self._rank(valid_candidates, section_copies, next_soft)
            if next_ranking is None:
                continue
            if {item.candidate_id for item in next_ranking} != {
                item.candidate_id for item in current_ranking
            }:
                continue
            next_top = next_ranking[:TOP_CANDIDATE_COUNT]
            next_top_ids = [candidate.candidate_id for candidate in next_top]
            top_changed = next_top_ids != current_top_ids
            if not top_changed:
                continue

            before_metrics = self._metrics_for_field(adjustment.field, current_top)
            after_metrics = self._metrics_for_field(adjustment.field, next_top)
            improved, worsened = _metric_changes(before_metrics, after_metrics)
            if not improved:
                continue
            if not self._has_relevant_improvement(adjustment.field, improved):
                continue

            evidence = SoftPreferenceRecommendationEvidence(
                before_top_candidate_ids=current_top_ids,
                after_top_candidate_ids=next_top_ids,
                top_candidates_changed=top_changed,
                before_metrics=before_metrics,
                after_metrics=after_metrics,
                improved_metrics=improved,
                worsened_metrics=worsened,
            )
            suggestion = SoftPreferenceRecommendation(
                suggestion_id=self._suggestion_id(
                    request.session_id,
                    adjustment,
                    len(evaluated) + 1,
                ),
                basis=adjustment.basis,
                field=adjustment.field,
                operation=adjustment.operation,
                current_value=_value_for_field(current_soft, adjustment.field),
                suggested_value=adjustment.suggested_value,
                reason=self._reason(adjustment),
                expected_benefit=self._expected_benefit(evidence),
                tradeoff=self._tradeoff(evidence),
                evidence=evidence,
            )
            evaluated.append(
                _EvaluatedAdjustment(
                    suggestion=suggestion,
                    sort_key=self._sort_key(
                        adjustment,
                        evidence,
                    ),
                )
            )

        if not evaluated:
            return self._blocked(
                request,
                (
                    SoftPreferenceRecommendationBlockedCode.NOT_DETERMINABLE_WITH_CURRENT_DATA
                    if request.feedback_target is not None
                    else SoftPreferenceRecommendationBlockedCode.NO_EFFECTIVE_CHANGE
                ),
                "변경 후 상위 후보 또는 관련 지표가 실제로 개선되지 않았습니다.",
                analyzed_candidate_count=len(valid_candidates),
                current_top_candidate_ids=current_top_ids,
            )

        evaluated.sort(key=lambda item: item.sort_key)
        suggestions = [item.suggestion for item in evaluated[: request.max_suggestions]]
        return SoftPreferenceRecommendationResult(
            suggestions=suggestions,
            blocked_reasons=[],
            analyzed_candidate_count=len(valid_candidates),
            current_top_candidate_ids=current_top_ids,
        )

    def _rank(
        self,
        candidates: list[GeneratedTimetableCandidate],
        sections: list[ResolvedSection],
        soft_preferences: SoftPreferences,
    ) -> list[ScoredTimetableCandidate] | None:
        try:
            scored = [
                self._ranking_service.scoring_service.score_candidate(
                    candidate=candidate.model_copy(deep=True),
                    soft_preferences=soft_preferences.model_copy(deep=True),
                    sections=[section.model_copy(deep=True) for section in sections],
                    policy=self._ranking_service.policy,
                )
                for candidate in candidates
            ]
        except Exception:
            return None
        return self._ranking_service._assign_ranks(scored)

    def _build_adjustments(
        self,
        *,
        request: SoftPreferenceRecommendationRequest,
        candidates: list[GeneratedTimetableCandidate],
        sections: list[ResolvedSection],
        current_soft: SoftPreferences,
        current_top: list[ScoredTimetableCandidate],
        protected: set[SoftPreferenceRecommendationField],
    ) -> list[_Adjustment]:
        fields = [
            field
            for field in _fields_for_feedback(request.feedback_target)
            if field not in protected
        ]
        adjustments: list[_Adjustment] = []
        for field in fields:
            common_weakness = self._common_weakness(field, current_top)
            feedback_match = _feedback_matches_field(request.feedback_target, field)
            if request.feedback_target is None and not common_weakness:
                continue
            basis = (
                SoftPreferenceSuggestionBasis.STRUCTURED_USER_FEEDBACK
                if feedback_match
                else SoftPreferenceSuggestionBasis.COMMON_CURRENT_TOP_WEAKNESS
                if common_weakness
                else SoftPreferenceSuggestionBasis.ALTERNATIVE_RANKING_COMPARISON
            )
            for operation, suggested_value in self._candidate_values_for_field(
                field,
                request.feedback_target,
                candidates,
                sections,
                current_soft,
            ):
                adjustments.append(
                    _Adjustment(
                        field=field,
                        operation=operation,
                        suggested_value=suggested_value,
                        basis=basis,
                        feedback_match=feedback_match,
                        common_weakness=common_weakness,
                    )
                )
        return adjustments

    def _candidate_values_for_field(
        self,
        field: SoftPreferenceRecommendationField,
        feedback_target: SoftPreferenceFeedbackTarget | None,
        candidates: list[GeneratedTimetableCandidate],
        sections: list[ResolvedSection],
        current_soft: SoftPreferences,
    ) -> list[tuple[SoftPreferenceSuggestionOperation, object]]:
        if field is SoftPreferenceRecommendationField.PREFERRED_FREE_DAYS:
            current = list(current_soft.preferred_free_days)
            values = [
                day
                for day in Day
                if day not in current
                and any(day in _free_days_for_candidate(candidate, sections) for candidate in candidates)
            ]
            return [
                (
                    SoftPreferenceSuggestionOperation.ADD_VALUE
                    if not current
                    else SoftPreferenceSuggestionOperation.REPLACE_VALUE,
                    [day],
                )
                for day in values
            ]

        if field is SoftPreferenceRecommendationField.PREFERRED_EARLIEST_START_TIME:
            current = current_soft.preferred_earliest_start_time
            times = sorted({_clock(_first_start_minutes(candidate, sections)) for candidate in candidates})
            if feedback_target is SoftPreferenceFeedbackTarget.LATER_START and current is not None:
                times = [time for time in times if time > current]
            return [
                (SoftPreferenceSuggestionOperation.SET_VALUE, time)
                for time in times
                if time != current
            ]

        if field is SoftPreferenceRecommendationField.PREFERRED_LATEST_END_TIME:
            current = current_soft.preferred_latest_end_time
            times = sorted({_clock(_latest_end_minutes(candidate, sections)) for candidate in candidates})
            if feedback_target is SoftPreferenceFeedbackTarget.EARLIER_END and current is not None:
                times = [time for time in times if time < current]
            return [
                (SoftPreferenceSuggestionOperation.SET_VALUE, time)
                for time in times
                if time != current
            ]

        if field is SoftPreferenceRecommendationField.PREFERRED_COURSE_IDS:
            current = set(current_soft.preferred_course_ids)
            top_only = feedback_target not in {
                SoftPreferenceFeedbackTarget.PREFER_COURSE,
                SoftPreferenceFeedbackTarget.DIFFERENT_TOP_CANDIDATES,
            }
            if top_only:
                return []
            course_ids = sorted(
                {
                    course_id
                    for candidate in candidates
                    for course_id in candidate.course_ids
                    if course_id not in current
                }
            )
            return [
                (
                    SoftPreferenceSuggestionOperation.ADD_VALUE,
                    [*current_soft.preferred_course_ids, course_id],
                )
                for course_id in course_ids
            ]

        if field is SoftPreferenceRecommendationField.DISLIKED_COURSE_IDS:
            current = set(current_soft.disliked_course_ids)
            if feedback_target not in {
                SoftPreferenceFeedbackTarget.AVOID_COURSE,
                SoftPreferenceFeedbackTarget.DIFFERENT_TOP_CANDIDATES,
            }:
                return []
            course_ids = sorted(
                {
                    course_id
                    for candidate in candidates
                    for course_id in candidate.course_ids
                    if course_id not in current
                }
            )
            return [
                (
                    SoftPreferenceSuggestionOperation.ADD_VALUE,
                    [*current_soft.disliked_course_ids, course_id],
                )
                for course_id in course_ids
            ]

        if field is SoftPreferenceRecommendationField.COMPACT_SCHEDULE:
            current = current_soft.compact_schedule
            values: list[bool] = []
            if feedback_target is SoftPreferenceFeedbackTarget.MORE_COMPACT:
                values = [True]
            elif feedback_target is SoftPreferenceFeedbackTarget.LESS_COMPACT:
                values = [False]
            else:
                values = [value for value in (True, False) if value != current]
            return [
                (SoftPreferenceSuggestionOperation.SET_VALUE, value)
                for value in values
                if value != current
            ]

        return []

    def _common_weakness(
        self,
        field: SoftPreferenceRecommendationField,
        current_top: list[ScoredTimetableCandidate],
    ) -> bool:
        if not current_top:
            return False
        component_code = _component_code_for_field(field)
        if component_code is None:
            return False
        matching = []
        for candidate in current_top:
            component = next(
                (
                    item
                    for item in candidate.score_components
                    if item.code is component_code
                ),
                None,
            )
            if component is None:
                return False
            matching.append(component)
        return all(not component.satisfied for component in matching)

    def _metrics_for_field(
        self,
        field: SoftPreferenceRecommendationField,
        ranked: list[ScoredTimetableCandidate],
    ) -> list[SoftPreferenceRecommendationMetric]:
        metrics = [
            SoftPreferenceRecommendationMetric(
                code=SoftPreferenceRecommendationMetricCode.TOTAL_SCORE,
                value=round(sum(candidate.total_score for candidate in ranked), 6),
                direction=SoftPreferenceMetricDirection.HIGHER_IS_BETTER,
                candidate_count=len(ranked),
            ),
            SoftPreferenceRecommendationMetric(
                code=SoftPreferenceRecommendationMetricCode.SATISFIED_PREFERENCE_COUNT,
                value=sum(len(candidate.satisfied_preferences) for candidate in ranked),
                direction=SoftPreferenceMetricDirection.HIGHER_IS_BETTER,
                candidate_count=len(ranked),
            ),
            SoftPreferenceRecommendationMetric(
                code=SoftPreferenceRecommendationMetricCode.UNSATISFIED_PREFERENCE_COUNT,
                value=sum(len(candidate.unsatisfied_preferences) for candidate in ranked),
                direction=SoftPreferenceMetricDirection.LOWER_IS_BETTER,
                candidate_count=len(ranked),
            ),
        ]
        if field is SoftPreferenceRecommendationField.PREFERRED_FREE_DAYS:
            metrics.extend(
                [
                    self._component_metric(
                        ranked,
                        ScoreComponentCode.PREFERRED_FREE_DAYS,
                        SoftPreferenceRecommendationMetricCode.PREFERRED_FREE_DAY_SATISFIED_COUNT,
                        "satisfied_count",
                        SoftPreferenceMetricDirection.HIGHER_IS_BETTER,
                    ),
                    self._component_metric(
                        ranked,
                        ScoreComponentCode.PREFERRED_FREE_DAYS,
                        SoftPreferenceRecommendationMetricCode.PREFERRED_FREE_DAY_UNSATISFIED_COUNT,
                        "unsatisfied_count",
                        SoftPreferenceMetricDirection.LOWER_IS_BETTER,
                    ),
                ]
            )
        elif field is SoftPreferenceRecommendationField.PREFERRED_EARLIEST_START_TIME:
            metrics.extend(
                [
                    self._component_metric(
                        ranked,
                        ScoreComponentCode.PREFERRED_START_TIME,
                        SoftPreferenceRecommendationMetricCode.TOTAL_EARLY_MINUTES,
                        "total_early_minutes",
                        SoftPreferenceMetricDirection.LOWER_IS_BETTER,
                    ),
                    self._component_metric(
                        ranked,
                        ScoreComponentCode.PREFERRED_START_TIME,
                        SoftPreferenceRecommendationMetricCode.MAX_EARLY_START_DIFFERENCE_MINUTES,
                        "max_difference_minutes",
                        SoftPreferenceMetricDirection.LOWER_IS_BETTER,
                        aggregate=max,
                    ),
                ]
            )
        elif field is SoftPreferenceRecommendationField.PREFERRED_LATEST_END_TIME:
            metrics.extend(
                [
                    self._component_metric(
                        ranked,
                        ScoreComponentCode.PREFERRED_END_TIME,
                        SoftPreferenceRecommendationMetricCode.TOTAL_LATE_MINUTES,
                        "total_late_minutes",
                        SoftPreferenceMetricDirection.LOWER_IS_BETTER,
                    ),
                    self._component_metric(
                        ranked,
                        ScoreComponentCode.PREFERRED_END_TIME,
                        SoftPreferenceRecommendationMetricCode.MAX_LATE_END_DIFFERENCE_MINUTES,
                        "max_difference_minutes",
                        SoftPreferenceMetricDirection.LOWER_IS_BETTER,
                        aggregate=max,
                    ),
                ]
            )
        elif field is SoftPreferenceRecommendationField.PREFERRED_COURSE_IDS:
            metrics.extend(
                [
                    self._list_metric(
                        ranked,
                        ScoreComponentCode.PREFERRED_COURSES,
                        SoftPreferenceRecommendationMetricCode.PREFERRED_COURSE_INCLUDED_COUNT,
                        "included_course_ids",
                        SoftPreferenceMetricDirection.HIGHER_IS_BETTER,
                    ),
                    self._list_metric(
                        ranked,
                        ScoreComponentCode.PREFERRED_COURSES,
                        SoftPreferenceRecommendationMetricCode.PREFERRED_COURSE_MISSING_COUNT,
                        "missing_course_ids",
                        SoftPreferenceMetricDirection.LOWER_IS_BETTER,
                    ),
                ]
            )
        elif field is SoftPreferenceRecommendationField.DISLIKED_COURSE_IDS:
            metrics.append(
                self._list_metric(
                    ranked,
                    ScoreComponentCode.DISLIKED_COURSES,
                    SoftPreferenceRecommendationMetricCode.DISLIKED_COURSE_INCLUDED_COUNT,
                    "included_course_ids",
                    SoftPreferenceMetricDirection.LOWER_IS_BETTER,
                )
            )
        elif field is SoftPreferenceRecommendationField.COMPACT_SCHEDULE:
            metrics.extend(
                [
                    self._component_metric(
                        ranked,
                        ScoreComponentCode.COMPACT_SCHEDULE,
                        SoftPreferenceRecommendationMetricCode.TOTAL_GAP_MINUTES,
                        "total_gap_minutes",
                        SoftPreferenceMetricDirection.LOWER_IS_BETTER,
                    ),
                    self._component_metric(
                        ranked,
                        ScoreComponentCode.COMPACT_SCHEDULE,
                        SoftPreferenceRecommendationMetricCode.LONG_GAP_COUNT,
                        "long_gap_count",
                        SoftPreferenceMetricDirection.LOWER_IS_BETTER,
                    ),
                    self._component_metric(
                        ranked,
                        ScoreComponentCode.COMPACT_SCHEDULE,
                        SoftPreferenceRecommendationMetricCode.SHORT_GAP_COUNT,
                        "short_gap_count",
                        SoftPreferenceMetricDirection.LOWER_IS_BETTER,
                    ),
                ]
            )
        return metrics

    def _component_metric(
        self,
        ranked: list[ScoredTimetableCandidate],
        component_code: ScoreComponentCode,
        metric_code: SoftPreferenceRecommendationMetricCode,
        detail_key: str,
        direction: SoftPreferenceMetricDirection,
        *,
        aggregate=sum,
    ) -> SoftPreferenceRecommendationMetric:
        values = [
            _number(component.details.get(detail_key, 0))
            for candidate in ranked
            for component in candidate.score_components
            if component.code is component_code
        ]
        return SoftPreferenceRecommendationMetric(
            code=metric_code,
            value=aggregate(values) if values else 0,
            direction=direction,
            candidate_count=len(ranked),
        )

    def _list_metric(
        self,
        ranked: list[ScoredTimetableCandidate],
        component_code: ScoreComponentCode,
        metric_code: SoftPreferenceRecommendationMetricCode,
        detail_key: str,
        direction: SoftPreferenceMetricDirection,
    ) -> SoftPreferenceRecommendationMetric:
        value = sum(
            len(component.details.get(detail_key, []) or [])
            for candidate in ranked
            for component in candidate.score_components
            if component.code is component_code
        )
        return SoftPreferenceRecommendationMetric(
            code=metric_code,
            value=value,
            direction=direction,
            candidate_count=len(ranked),
        )

    @staticmethod
    def _has_relevant_improvement(
        field: SoftPreferenceRecommendationField,
        improved: list[SoftPreferenceRecommendationMetric],
    ) -> bool:
        relevant = _primary_metric_codes_for_field(field)
        return any(metric.code in relevant for metric in improved)

    @staticmethod
    def _reason(adjustment: _Adjustment) -> str:
        if adjustment.basis is SoftPreferenceSuggestionBasis.STRUCTURED_USER_FEEDBACK:
            return "구조화된 사용자 피드백과 일치하는 Soft Preference 변경입니다."
        if adjustment.basis is SoftPreferenceSuggestionBasis.COMMON_CURRENT_TOP_WEAKNESS:
            return "현재 상위 후보들이 공통으로 만족하지 못한 Soft Preference를 조정합니다."
        return "같은 유효 후보군을 다른 Soft Preference로 재정렬했을 때 개선 근거가 있습니다."

    @staticmethod
    def _expected_benefit(evidence: SoftPreferenceRecommendationEvidence) -> str:
        changed = ", ".join(evidence.after_top_candidate_ids)
        improved = ", ".join(metric.code.value for metric in evidence.improved_metrics)
        return f"상위 후보가 [{changed}]로 바뀌고 개선 지표가 확인되었습니다: {improved}."

    @staticmethod
    def _tradeoff(evidence: SoftPreferenceRecommendationEvidence) -> str:
        if not evidence.worsened_metrics:
            return "측정된 악화 지표는 없습니다."
        worsened = ", ".join(metric.code.value for metric in evidence.worsened_metrics)
        return f"다음 지표가 악화될 수 있습니다: {worsened}."

    @staticmethod
    def _sort_key(
        adjustment: _Adjustment,
        evidence: SoftPreferenceRecommendationEvidence,
    ) -> tuple[object, ...]:
        improvement_size = _total_improvement(evidence.improved_metrics, evidence.before_metrics)
        tradeoff_size = _total_worsening(evidence.worsened_metrics, evidence.before_metrics)
        return (
            0 if adjustment.feedback_match else 1,
            0 if adjustment.common_weakness else 1,
            0 if evidence.improved_metrics else 1,
            0 if evidence.top_candidates_changed else 1,
            0,
            -improvement_size,
            tradeoff_size,
            adjustment.field.value,
            adjustment.operation.value,
            _stable_json(adjustment.suggested_value),
        )

    @staticmethod
    def _suggestion_id(
        session_id: str,
        adjustment: _Adjustment,
        index: int,
    ) -> str:
        digest = sha256(
            "|".join(
                [
                    session_id,
                    adjustment.field.value,
                    adjustment.operation.value,
                    _stable_json(adjustment.suggested_value),
                    str(index),
                ]
            ).encode("utf-8")
        ).hexdigest()
        return f"sug_{digest[:12]}"

    @staticmethod
    def _apply_adjustment(
        current_soft: SoftPreferences,
        adjustment: _Adjustment,
    ) -> SoftPreferences:
        return current_soft.model_copy(
            update={adjustment.field.value: adjustment.suggested_value},
            deep=True,
        )

    @staticmethod
    def _blocked(
        request: SoftPreferenceRecommendationRequest,
        code: SoftPreferenceRecommendationBlockedCode,
        message: str,
        *,
        analyzed_candidate_count: int,
        current_top_candidate_ids: list[str] | None = None,
    ) -> SoftPreferenceRecommendationResult:
        return SoftPreferenceRecommendationResult(
            suggestions=[],
            blocked_reasons=[
                SoftPreferenceRecommendationBlockedReason(
                    code=code,
                    message=message,
                    details={
                        "session_id": request.session_id,
                        "feedback_target": (
                            None
                            if request.feedback_target is None
                            else request.feedback_target.value
                        ),
                    },
                )
            ],
            analyzed_candidate_count=analyzed_candidate_count,
            current_top_candidate_ids=current_top_candidate_ids or [],
        )


def _fields_for_feedback(
    feedback_target: SoftPreferenceFeedbackTarget | None,
) -> list[SoftPreferenceRecommendationField]:
    mapping = {
        SoftPreferenceFeedbackTarget.DIFFERENT_FREE_DAY: [
            SoftPreferenceRecommendationField.PREFERRED_FREE_DAYS
        ],
        SoftPreferenceFeedbackTarget.LATER_START: [
            SoftPreferenceRecommendationField.PREFERRED_EARLIEST_START_TIME
        ],
        SoftPreferenceFeedbackTarget.EARLIER_END: [
            SoftPreferenceRecommendationField.PREFERRED_LATEST_END_TIME
        ],
        SoftPreferenceFeedbackTarget.PREFER_COURSE: [
            SoftPreferenceRecommendationField.PREFERRED_COURSE_IDS
        ],
        SoftPreferenceFeedbackTarget.AVOID_COURSE: [
            SoftPreferenceRecommendationField.DISLIKED_COURSE_IDS
        ],
        SoftPreferenceFeedbackTarget.MORE_COMPACT: [
            SoftPreferenceRecommendationField.COMPACT_SCHEDULE
        ],
        SoftPreferenceFeedbackTarget.LESS_COMPACT: [
            SoftPreferenceRecommendationField.COMPACT_SCHEDULE
        ],
    }
    if feedback_target in mapping:
        return mapping[feedback_target]
    return list(SoftPreferenceRecommendationField)


def _feedback_matches_field(
    feedback_target: SoftPreferenceFeedbackTarget | None,
    field: SoftPreferenceRecommendationField,
) -> bool:
    return field in _fields_for_feedback(feedback_target) and feedback_target is not None


def _component_code_for_field(
    field: SoftPreferenceRecommendationField,
) -> ScoreComponentCode | None:
    return {
        SoftPreferenceRecommendationField.PREFERRED_FREE_DAYS: ScoreComponentCode.PREFERRED_FREE_DAYS,
        SoftPreferenceRecommendationField.PREFERRED_EARLIEST_START_TIME: ScoreComponentCode.PREFERRED_START_TIME,
        SoftPreferenceRecommendationField.PREFERRED_LATEST_END_TIME: ScoreComponentCode.PREFERRED_END_TIME,
        SoftPreferenceRecommendationField.PREFERRED_COURSE_IDS: ScoreComponentCode.PREFERRED_COURSES,
        SoftPreferenceRecommendationField.DISLIKED_COURSE_IDS: ScoreComponentCode.DISLIKED_COURSES,
        SoftPreferenceRecommendationField.COMPACT_SCHEDULE: ScoreComponentCode.COMPACT_SCHEDULE,
    }.get(field)


def _primary_metric_codes_for_field(
    field: SoftPreferenceRecommendationField,
) -> set[SoftPreferenceRecommendationMetricCode]:
    return {
        SoftPreferenceRecommendationField.PREFERRED_FREE_DAYS: {
            SoftPreferenceRecommendationMetricCode.PREFERRED_FREE_DAY_SATISFIED_COUNT,
            SoftPreferenceRecommendationMetricCode.PREFERRED_FREE_DAY_UNSATISFIED_COUNT,
        },
        SoftPreferenceRecommendationField.PREFERRED_EARLIEST_START_TIME: {
            SoftPreferenceRecommendationMetricCode.TOTAL_EARLY_MINUTES,
            SoftPreferenceRecommendationMetricCode.MAX_EARLY_START_DIFFERENCE_MINUTES,
        },
        SoftPreferenceRecommendationField.PREFERRED_LATEST_END_TIME: {
            SoftPreferenceRecommendationMetricCode.TOTAL_LATE_MINUTES,
            SoftPreferenceRecommendationMetricCode.MAX_LATE_END_DIFFERENCE_MINUTES,
        },
        SoftPreferenceRecommendationField.PREFERRED_COURSE_IDS: {
            SoftPreferenceRecommendationMetricCode.PREFERRED_COURSE_INCLUDED_COUNT,
            SoftPreferenceRecommendationMetricCode.PREFERRED_COURSE_MISSING_COUNT,
        },
        SoftPreferenceRecommendationField.DISLIKED_COURSE_IDS: {
            SoftPreferenceRecommendationMetricCode.DISLIKED_COURSE_INCLUDED_COUNT,
        },
        SoftPreferenceRecommendationField.COMPACT_SCHEDULE: {
            SoftPreferenceRecommendationMetricCode.TOTAL_GAP_MINUTES,
            SoftPreferenceRecommendationMetricCode.LONG_GAP_COUNT,
            SoftPreferenceRecommendationMetricCode.SHORT_GAP_COUNT,
        },
    }[field]


def _metric_changes(
    before_metrics: list[SoftPreferenceRecommendationMetric],
    after_metrics: list[SoftPreferenceRecommendationMetric],
) -> tuple[list[SoftPreferenceRecommendationMetric], list[SoftPreferenceRecommendationMetric]]:
    before_by_code = {metric.code: metric for metric in before_metrics}
    improved: list[SoftPreferenceRecommendationMetric] = []
    worsened: list[SoftPreferenceRecommendationMetric] = []
    for after in after_metrics:
        before = before_by_code.get(after.code)
        if before is None:
            continue
        if _is_improved(before, after):
            improved.append(after)
        elif _is_worsened(before, after):
            worsened.append(after)
    return improved, worsened


def _is_improved(
    before: SoftPreferenceRecommendationMetric,
    after: SoftPreferenceRecommendationMetric,
) -> bool:
    if after.direction is SoftPreferenceMetricDirection.HIGHER_IS_BETTER:
        return after.value > before.value
    if after.direction is SoftPreferenceMetricDirection.LOWER_IS_BETTER:
        return after.value < before.value
    return after.value != before.value


def _is_worsened(
    before: SoftPreferenceRecommendationMetric,
    after: SoftPreferenceRecommendationMetric,
) -> bool:
    if after.direction is SoftPreferenceMetricDirection.HIGHER_IS_BETTER:
        return after.value < before.value
    if after.direction is SoftPreferenceMetricDirection.LOWER_IS_BETTER:
        return after.value > before.value
    return False


def _total_improvement(
    improved: list[SoftPreferenceRecommendationMetric],
    before_metrics: list[SoftPreferenceRecommendationMetric],
) -> float:
    before_by_code = {metric.code: metric for metric in before_metrics}
    total = 0.0
    for after in improved:
        before = before_by_code.get(after.code)
        if before is None:
            continue
        total += abs(float(after.value) - float(before.value))
    return total


def _total_worsening(
    worsened: list[SoftPreferenceRecommendationMetric],
    before_metrics: list[SoftPreferenceRecommendationMetric],
) -> float:
    before_by_code = {metric.code: metric for metric in before_metrics}
    total = 0.0
    for after in worsened:
        before = before_by_code.get(after.code)
        if before is None:
            continue
        total += abs(float(after.value) - float(before.value))
    return total


def _value_for_field(
    soft_preferences: SoftPreferences,
    field: SoftPreferenceRecommendationField,
) -> object:
    value = getattr(soft_preferences, field.value)
    if isinstance(value, list):
        return list(value)
    return value


def _free_days_for_candidate(
    candidate: GeneratedTimetableCandidate,
    sections: list[ResolvedSection],
) -> set[Day]:
    occupied = {
        meeting.day
        for section in _sections_for_candidate(candidate, sections)
        for meeting in section.section.class_times
    }
    return set(Day) - occupied


def _first_start_minutes(
    candidate: GeneratedTimetableCandidate,
    sections: list[ResolvedSection],
) -> int:
    return min(
        (
            meeting.start_minutes
            for section in _sections_for_candidate(candidate, sections)
            for meeting in section.section.class_times
        ),
        default=24 * 60,
    )


def _latest_end_minutes(
    candidate: GeneratedTimetableCandidate,
    sections: list[ResolvedSection],
) -> int:
    return max(
        (
            meeting.end_minutes
            for section in _sections_for_candidate(candidate, sections)
            for meeting in section.section.class_times
        ),
        default=0,
    )


def _sections_for_candidate(
    candidate: GeneratedTimetableCandidate,
    sections: list[ResolvedSection],
) -> list[ResolvedSection]:
    by_source = {section.source.key: section for section in sections}
    by_id = {section.section.section_id: section for section in sections}
    resolved: list[ResolvedSection] = []
    if candidate.section_sources:
        for source in candidate.section_sources:
            section = by_source.get(source.key)
            if section is not None:
                resolved.append(section)
    if not resolved:
        for section_id in candidate.section_ids:
            section = by_id.get(section_id)
            if section is not None:
                resolved.append(section)
    return resolved


def _clock(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _number(value: object) -> int | float:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return value
    return 0


def _stable_json(value: object) -> str:
    def default(item: object) -> str:
        if isinstance(item, Day):
            return item.value
        return str(item)

    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=default)



