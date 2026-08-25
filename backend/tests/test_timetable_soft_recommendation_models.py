from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.app.models.course import Day
from backend.app.models.timetable_soft_recommendation import (
    RECOMMENDATION_POLICY_VERSION,
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


def _metric(
    code: SoftPreferenceRecommendationMetricCode,
    value: int | float | bool,
    direction: SoftPreferenceMetricDirection = SoftPreferenceMetricDirection.LOWER_IS_BETTER,
) -> SoftPreferenceRecommendationMetric:
    return SoftPreferenceRecommendationMetric(
        code=code,
        value=value,
        direction=direction,
        candidate_count=2,
    )


def _evidence() -> SoftPreferenceRecommendationEvidence:
    before = _metric(
        SoftPreferenceRecommendationMetricCode.PREFERRED_FREE_DAY_UNSATISFIED_COUNT,
        2,
    )
    after = _metric(
        SoftPreferenceRecommendationMetricCode.PREFERRED_FREE_DAY_UNSATISFIED_COUNT,
        0,
    )
    return SoftPreferenceRecommendationEvidence(
        before_top_candidate_ids=["tt-before", "tt-stable"],
        after_top_candidate_ids=["tt-after", "tt-stable"],
        top_candidates_changed=True,
        before_metrics=[before],
        after_metrics=[after],
        improved_metrics=[after],
        worsened_metrics=[],
    )


_UNSET = object()

def _suggestion(
    suggestion_id: str = "sug_1",
    *,
    field: SoftPreferenceRecommendationField = SoftPreferenceRecommendationField.PREFERRED_FREE_DAYS,
    operation: SoftPreferenceSuggestionOperation = SoftPreferenceSuggestionOperation.REPLACE_VALUE,
    current_value: object = _UNSET,
    suggested_value: object = _UNSET,
) -> SoftPreferenceRecommendation:
    return SoftPreferenceRecommendation(
        suggestion_id=suggestion_id,
        basis=SoftPreferenceSuggestionBasis.COMMON_CURRENT_TOP_WEAKNESS,
        field=field,
        operation=operation,
        current_value=[Day.FRI] if current_value is _UNSET else current_value,
        suggested_value=[Day.TUE] if suggested_value is _UNSET else suggested_value,
        reason="현재 상위 후보가 금요일 공강 선호를 공통으로 만족하지 못했습니다.",
        expected_benefit="화요일 공강 후보가 상위권으로 올라올 수 있습니다.",
        tradeoff="금요일 공강 선호는 약해집니다.",
        evidence=_evidence(),
    )


def test_valid_recommendation_result_can_be_created() -> None:
    request = SoftPreferenceRecommendationRequest(
        session_id="session-1",
        feedback_target=SoftPreferenceFeedbackTarget.DIFFERENT_FREE_DAY,
        protected_soft_preferences=[
            SoftPreferenceRecommendationField.DISLIKED_COURSE_IDS,
            SoftPreferenceRecommendationField.DISLIKED_COURSE_IDS,
        ],
        max_suggestions=2,
    )
    result = SoftPreferenceRecommendationResult(
        suggestions=[_suggestion()],
        blocked_reasons=[],
        analyzed_candidate_count=5,
        current_top_candidate_ids=["tt-before", "tt-stable"],
    )

    assert request.protected_soft_preferences == [
        SoftPreferenceRecommendationField.DISLIKED_COURSE_IDS
    ]
    assert result.recommendation_policy_version == RECOMMENDATION_POLICY_VERSION
    assert result.suggestions[0].field is SoftPreferenceRecommendationField.PREFERRED_FREE_DAYS


def test_three_suggestions_are_allowed() -> None:
    result = SoftPreferenceRecommendationResult(
        suggestions=[
            _suggestion("sug_1"),
            _suggestion(
                "sug_2",
                field=SoftPreferenceRecommendationField.PREFERRED_EARLIEST_START_TIME,
                operation=SoftPreferenceSuggestionOperation.SET_VALUE,
                current_value="09:00",
                suggested_value="10:00",
            ),
            _suggestion(
                "sug_3",
                field=SoftPreferenceRecommendationField.COMPACT_SCHEDULE,
                operation=SoftPreferenceSuggestionOperation.SET_VALUE,
                current_value=None,
                suggested_value=True,
            ),
        ],
        analyzed_candidate_count=5,
        current_top_candidate_ids=["tt-current"],
    )

    assert len(result.suggestions) == 3


def test_four_or_more_suggestions_are_rejected() -> None:
    with pytest.raises(ValidationError):
        SoftPreferenceRecommendationResult(
            suggestions=[
                _suggestion("sug_1"),
                _suggestion("sug_2"),
                _suggestion("sug_3"),
                _suggestion("sug_4"),
            ],
            analyzed_candidate_count=5,
            current_top_candidate_ids=["tt-current"],
        )


def test_hard_field_target_recommendation_is_rejected() -> None:
    with pytest.raises(ValidationError):
        SoftPreferenceRecommendation.model_validate(
            {
                **_suggestion().model_dump(mode="json"),
                "field": "required_course_ids",
            }
        )


def test_unsupported_field_is_rejected() -> None:
    with pytest.raises(ValidationError):
        SoftPreferenceRecommendation.model_validate(
            {
                **_suggestion().model_dump(mode="json"),
                "field": "minimize_attendance_days",
            }
        )


def test_unsupported_operation_is_rejected() -> None:
    with pytest.raises(ValidationError, match="not allowed"):
        _suggestion(
            field=SoftPreferenceRecommendationField.PREFERRED_EARLIEST_START_TIME,
            operation=SoftPreferenceSuggestionOperation.ADD_VALUE,
            current_value="09:00",
            suggested_value="10:00",
        )


def test_invalid_feedback_target_is_rejected() -> None:
    with pytest.raises(ValidationError):
        SoftPreferenceRecommendationRequest(
            session_id="session-1",
            feedback_target="avoid_professor",
        )


def test_duplicate_suggestion_id_is_rejected() -> None:
    with pytest.raises(ValidationError, match="duplicate suggestion_id"):
        SoftPreferenceRecommendationResult(
            suggestions=[_suggestion("same"), _suggestion("same")],
            analyzed_candidate_count=2,
            current_top_candidate_ids=["tt-current"],
        )


def test_empty_suggestions_with_blocked_reason_are_allowed() -> None:
    result = SoftPreferenceRecommendationResult(
        suggestions=[],
        blocked_reasons=[
            SoftPreferenceRecommendationBlockedReason(
                code=SoftPreferenceRecommendationBlockedCode.NO_CANDIDATES,
                message="분석할 시간표 후보가 없습니다.",
                details={"session_id": "session-1"},
            )
        ],
        analyzed_candidate_count=0,
        current_top_candidate_ids=[],
    )

    assert result.suggestions == []
    assert result.blocked_reasons[0].code is SoftPreferenceRecommendationBlockedCode.NO_CANDIDATES


def test_empty_suggestions_without_blocked_reason_are_rejected() -> None:
    with pytest.raises(ValidationError, match="blocked_reasons"):
        SoftPreferenceRecommendationResult(
            suggestions=[],
            blocked_reasons=[],
            analyzed_candidate_count=0,
            current_top_candidate_ids=[],
        )


def test_evidence_requires_changed_metrics_to_exist_before_and_after() -> None:
    with pytest.raises(ValidationError, match="must exist in both"):
        SoftPreferenceRecommendationEvidence(
            before_top_candidate_ids=["tt-before"],
            after_top_candidate_ids=["tt-after"],
            top_candidates_changed=True,
            before_metrics=[
                _metric(SoftPreferenceRecommendationMetricCode.TOTAL_EARLY_MINUTES, 120)
            ],
            after_metrics=[
                _metric(SoftPreferenceRecommendationMetricCode.TOTAL_EARLY_MINUTES, 60)
            ],
            improved_metrics=[
                _metric(SoftPreferenceRecommendationMetricCode.TOTAL_LATE_MINUTES, 0)
            ],
        )


def test_soft_preference_value_types_match_real_model_fields() -> None:
    _suggestion(
        field=SoftPreferenceRecommendationField.PREFERRED_FREE_DAYS,
        current_value=[Day.MON],
        suggested_value=[Day.TUE],
    )
    _suggestion(
        field=SoftPreferenceRecommendationField.PREFERRED_COURSE_IDS,
        operation=SoftPreferenceSuggestionOperation.ADD_VALUE,
        current_value=["C101"],
        suggested_value=["C101", "C102"],
    )
    _suggestion(
        field=SoftPreferenceRecommendationField.DISLIKED_COURSE_IDS,
        operation=SoftPreferenceSuggestionOperation.REMOVE_VALUE,
        current_value=["C101"],
        suggested_value=[],
    )
    _suggestion(
        field=SoftPreferenceRecommendationField.PREFERRED_LATEST_END_TIME,
        operation=SoftPreferenceSuggestionOperation.SET_VALUE,
        current_value="18:00",
        suggested_value="17:00",
    )
    _suggestion(
        field=SoftPreferenceRecommendationField.COMPACT_SCHEDULE,
        operation=SoftPreferenceSuggestionOperation.CLEAR_VALUE,
        current_value=True,
        suggested_value=None,
    )

    with pytest.raises(ValidationError, match="list of Day"):
        _suggestion(
            field=SoftPreferenceRecommendationField.PREFERRED_FREE_DAYS,
            current_value=["FRI"],
            suggested_value=["TUE"],
        )
    with pytest.raises(ValidationError, match="HH:MM"):
        _suggestion(
            field=SoftPreferenceRecommendationField.PREFERRED_EARLIEST_START_TIME,
            operation=SoftPreferenceSuggestionOperation.SET_VALUE,
            current_value="09:00",
            suggested_value=True,
        )
    with pytest.raises(ValidationError, match="boolean"):
        _suggestion(
            field=SoftPreferenceRecommendationField.COMPACT_SCHEDULE,
            operation=SoftPreferenceSuggestionOperation.SET_VALUE,
            current_value=None,
            suggested_value="true",
        )


def test_request_max_suggestions_is_limited_to_one_through_three() -> None:
    SoftPreferenceRecommendationRequest(session_id="session-1", max_suggestions=1)
    SoftPreferenceRecommendationRequest(session_id="session-1", max_suggestions=3)

    with pytest.raises(ValidationError):
        SoftPreferenceRecommendationRequest(session_id="session-1", max_suggestions=0)
    with pytest.raises(ValidationError):
        SoftPreferenceRecommendationRequest(session_id="session-1", max_suggestions=4)



