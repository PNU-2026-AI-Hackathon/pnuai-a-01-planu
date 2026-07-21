"""Unit tests for structured general-education preference parsing."""

from __future__ import annotations

import json

import pytest

from backend.app.core.errors import AppError
from backend.app.models import Day, GeneralPreferenceLLMOutput, PreferenceRules
from backend.app.services.general_preference_parser import (
    GeneralPreferenceParser,
    parse_general_preferences,
    supported_general_preference_fields,
)


class FakeStructuredLLM:
    def __init__(self, output):
        self.output = output
        self.schema = None
        self.calls = 0

    def with_structured_output(self, schema):
        self.schema = schema
        return self

    def invoke(self, messages):
        self.calls += 1
        assert self.schema is GeneralPreferenceLLMOutput
        assert messages[0][0] == "system"
        return self.output


def test_hard_and_soft_conditions_are_split_into_existing_rules() -> None:
    result = parse_general_preferences(
        "금요일은 가능하면 쉬고 싶고 오전 수업은 절대 안 돼.",
        llm=FakeStructuredLLM(
            {
                "hard_conditions": {"earliest_start_time": "10:00"},
                "soft_conditions": {"preferred_free_days": ["FRI"]},
                "unsupported_conditions": [],
                "warnings": [],
            }
        ),
    )

    assert result.hard_conditions.earliest_start_time == "10:00"
    assert result.hard_conditions.preferred_first_class_time is None
    assert result.soft_conditions.preferred_free_days == [Day.FRI]
    assert result.soft_conditions.earliest_start_time is None


def test_concrete_course_names_keep_hard_and_soft_strength() -> None:
    result = parse_general_preferences(
        "고전읽기와토론은 꼭 듣고 경제학원론은 가능하면 피하고 싶어.",
        llm=FakeStructuredLLM(
            {
                "hard_conditions": {"required_course_names": ["고전읽기와토론"]},
                "soft_conditions": {"avoided_course_names": ["경제학원론"]},
            }
        ),
    )

    assert result.hard_conditions.required_course_names == ["고전읽기와토론"]
    assert result.soft_conditions.avoided_course_names == ["경제학원론"]


def test_omitted_soft_course_preference_is_recovered_from_prompt() -> None:
    result = parse_general_preferences(
        "고전읽기와토론을 우선하고 싶고 경제학원론은 가능하면 피하고 싶어.",
        llm=FakeStructuredLLM(
            {
                "soft_conditions": {
                    "avoided_course_names": ["경제학원론"],
                },
            }
        ),
    )

    assert result.soft_conditions.preferred_course_names == ["고전읽기와토론"]
    assert result.soft_conditions.avoided_course_names == ["경제학원론"]


def test_soft_course_preference_is_demoted_from_hard_output() -> None:
    result = parse_general_preferences(
        "고전읽기와토론을 우선하고 싶고 경제학원론은 가능하면 피하고 싶어.",
        llm=FakeStructuredLLM(
            {
                "hard_conditions": {
                    "required_course_names": ["고전읽기와토론"],
                },
                "soft_conditions": {
                    "avoided_course_names": ["경제학원론"],
                },
            }
        ),
    )

    assert result.hard_conditions.required_course_names == []
    assert result.soft_conditions.preferred_course_names == ["고전읽기와토론"]
    assert result.soft_conditions.avoided_course_names == ["경제학원론"]


def test_unsupported_conditions_are_not_silently_ignored() -> None:
    result = parse_general_preferences(
        "과제가 적고 에브리타임 평점이 높은 교수 수업을 듣고 싶어.",
        llm=FakeStructuredLLM(
            {
                "unsupported_conditions": [
                    {
                        "source_text": "과제가 적은 수업",
                        "reason_code": "DATA_NOT_AVAILABLE",
                        "reason": "현재 수강편람 데이터에서는 과제량을 확인할 수 없습니다.",
                    },
                    {
                        "source_text": "에브리타임 평점이 높은 교수",
                        "reason_code": "DATA_NOT_AVAILABLE",
                        "reason": "현재 데이터에서는 교수 평점을 확인할 수 없습니다.",
                    },
                ]
            }
        ),
    )

    assert [item.reason_code for item in result.unsupported_conditions] == [
        "DATA_NOT_AVAILABLE",
        "DATA_NOT_AVAILABLE",
    ]
    assert result.hard_conditions == PreferenceRules()
    assert result.soft_conditions == PreferenceRules()


def test_ambiguous_strength_stays_soft_with_warning() -> None:
    result = parse_general_preferences(
        "오전 수업은 싫어.",
        llm=FakeStructuredLLM(
            {
                "soft_conditions": {"preferred_first_class_time": "10:00"},
                "warnings": [
                    {
                        "code": "AMBIGUOUS_CONDITION_STRENGTH",
                        "message": "'오전 수업은 싫어'를 선호 조건으로 해석했습니다.",
                        "source_text": "오전 수업은 싫어",
                    }
                ],
            }
        ),
    )

    assert result.hard_conditions.earliest_start_time is None
    assert result.soft_conditions.preferred_first_class_time == "10:00"
    assert result.warnings[0].code == "AMBIGUOUS_CONDITION_STRENGTH"


def test_ambiguous_morning_hard_output_is_softened() -> None:
    result = parse_general_preferences(
        "오전 수업은 싫어.",
        llm=FakeStructuredLLM(
            {
                "hard_conditions": {"earliest_start_time": "10:00"},
            }
        ),
    )

    assert result.hard_conditions.earliest_start_time is None
    assert result.soft_conditions.preferred_first_class_time == "10:00"
    assert any(
        warning.code == "AMBIGUOUS_CONDITION_STRENGTH"
        for warning in result.warnings
    )


def test_hard_soft_duplicate_target_keeps_hard_only() -> None:
    result = parse_general_preferences(
        "금요일은 가능하면 쉬고 싶고 사실 금요일 수업은 절대 안 돼.",
        llm=FakeStructuredLLM(
            {
                "hard_conditions": {"excluded_days": ["FRI"]},
                "soft_conditions": {"preferred_free_days": ["FRI"]},
            }
        ),
    )

    assert result.hard_conditions.excluded_days == [Day.FRI]
    assert result.soft_conditions.preferred_free_days == []
    assert any(warning.code == "HARD_SOFT_DUPLICATE_REMOVED" for warning in result.warnings)


def test_hard_soft_duplicate_course_keeps_hard_only() -> None:
    result = parse_general_preferences(
        "대학영어는 꼭 듣고 가능하면 대학영어도 우선해줘.",
        llm=FakeStructuredLLM(
            {
                "hard_conditions": {"required_course_names": ["대학영어"]},
                "soft_conditions": {"preferred_course_names": ["대학영어"]},
            }
        ),
    )

    assert result.hard_conditions.required_course_names == ["대학영어"]
    assert result.soft_conditions.preferred_course_names == []
    assert any(warning.code == "HARD_SOFT_DUPLICATE_REMOVED" for warning in result.warnings)


def test_excluded_professors_are_supported_hard_conditions() -> None:
    result = parse_general_preferences(
        "김교수 수업은 절대 넣지 마.",
        llm=FakeStructuredLLM(
            {"hard_conditions": {"excluded_professors": ["김교수"]}}
        ),
    )

    assert result.hard_conditions.excluded_professors == ["김교수"]


def test_conflicting_course_conditions_raise_standard_error() -> None:
    with pytest.raises(AppError) as exc_info:
        parse_general_preferences(
            "대학영어는 꼭 듣고 대학영어는 절대 듣기 싫어.",
            llm=FakeStructuredLLM(
                {
                    "hard_conditions": {
                        "required_course_names": ["대학영어"],
                        "excluded_course_names": ["대학영어"],
                    }
                }
            ),
        )

    assert exc_info.value.code == "CONFLICTING_PREFERENCE_CONDITIONS"


def test_invalid_time_raises_invalid_output_error() -> None:
    with pytest.raises(AppError) as exc_info:
        parse_general_preferences(
            "25시 이후 수업만 가능해.",
            llm=FakeStructuredLLM(
                {"hard_conditions": {"earliest_start_time": "25:00"}}
            ),
        )

    assert exc_info.value.code == "INVALID_PREFERENCE_OUTPUT"


def test_blank_prompt_does_not_call_llm() -> None:
    llm = FakeStructuredLLM({"soft_conditions": {"preferred_free_days": ["FRI"]}})

    result = parse_general_preferences("   ", llm=llm)

    assert result == GeneralPreferenceParser(llm=llm).parse("")
    assert llm.calls == 0


def test_unknown_structured_field_is_rejected() -> None:
    with pytest.raises(AppError) as exc_info:
        parse_general_preferences(
            "점수를 높게 줘.",
            llm=FakeStructuredLLM({"preferred_free_day_score": 30}),
        )

    assert exc_info.value.code == "INVALID_PREFERENCE_OUTPUT"


def test_openai_tool_call_response_extracts_general_preference_arguments() -> None:
    output = GeneralPreferenceParser._result_from_chat_completions_response(
        {
            "choices": [
                {
                    "message": {
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "general_preference_from_prompt",
                                    "arguments": json.dumps(
                                        {
                                            "preference_result": {
                                                "hard_conditions": {
                                                    "earliest_start_time": "10:00",
                                                },
                                                "soft_conditions": {
                                                    "preferred_free_days": ["FRI"],
                                                },
                                                "unsupported_conditions": [],
                                                "warnings": [],
                                            },
                                        },
                                        ensure_ascii=False,
                                    ),
                                }
                            }
                        ]
                    }
                }
            ]
        }
    )

    assert output["hard_conditions"]["earliest_start_time"] == "10:00"
    assert output["soft_conditions"]["preferred_free_days"] == ["FRI"]


def test_openai_tool_call_response_defers_domain_conflict_validation() -> None:
    output = GeneralPreferenceParser._result_from_chat_completions_response(
        {
            "choices": [
                {
                    "message": {
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "general_preference_from_prompt",
                                    "arguments": json.dumps(
                                        {
                                            "preference_result": {
                                                "hard_conditions": {
                                                    "required_course_names": ["대학영어"],
                                                    "excluded_course_names": ["대학영어"],
                                                }
                                            },
                                        },
                                        ensure_ascii=False,
                                    ),
                                }
                            }
                        ]
                    }
                }
            ]
        }
    )

    assert output["hard_conditions"]["required_course_names"] == ["대학영어"]
    assert output["hard_conditions"]["excluded_course_names"] == ["대학영어"]


def test_near_schema_live_output_is_normalized_before_validation() -> None:
    output = GeneralPreferenceParser._result_from_chat_completions_response(
        {
            "choices": [
                {
                    "message": {
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "general_preference_from_prompt",
                                    "arguments": json.dumps(
                                        {
                                            "preference_result": {
                                                "soft_conditions": {
                                                    "preferred_days": ["FRI"],
                                                },
                                                "unsupported_conditions": [
                                                    "발표 없는 수업은 현재 지원하지 않습니다.",
                                                ],
                                            },
                                        },
                                        ensure_ascii=False,
                                    ),
                                }
                            }
                        ]
                    }
                }
            ]
        }
    )

    assert output["soft_conditions"]["preferred_free_days"] == ["FRI"]
    assert output["unsupported_conditions"] == [
        {
            "source_text": "발표 없는 수업은 현재 지원하지 않습니다.",
            "reason_code": "UNSUPPORTED_CONDITION",
            "reason": "현재 PlaNU 데이터와 규칙으로 적용할 수 없는 조건입니다.",
        }
    ]


def test_wrong_scope_field_is_rejected_by_structured_schema() -> None:
    with pytest.raises(AppError) as exc_info:
        parse_general_preferences(
            "금요일은 가능하면 쉬고 싶어.",
            llm=FakeStructuredLLM(
                {"hard_conditions": {"preferred_free_days": ["FRI"]}}
            ),
        )

    assert exc_info.value.code == "INVALID_PREFERENCE_OUTPUT"


def test_supported_fields_match_generator_and_ranker_boundaries() -> None:
    fields = supported_general_preference_fields()

    assert "earliest_start_time" in fields["hard_conditions"]
    assert "excluded_time_ranges" in fields["hard_conditions"]
    assert "excluded_professors" in fields["hard_conditions"]
    assert "preferred_free_days" in fields["soft_conditions"]
    assert "compact_schedule" in fields["soft_conditions"]
    assert "selected_template" not in fields["soft_conditions"]
