"""Fixture-driven parser tests that avoid live LLM/API calls."""

from __future__ import annotations

import json

import pytest

from backend.app.core.errors import AppError
from backend.app.models import Day, GeneralPreferenceLLMOutput
from backend.app.services.general_preference_parser import (
    GENERAL_PREFERENCE_SYSTEM_PROMPT,
    GeneralPreferenceParser,
    parse_general_preferences,
)


class CapturingStructuredLLM:
    def __init__(self, output):
        self.output = output
        self.schema = None
        self.messages = None

    def with_structured_output(self, schema):
        self.schema = schema
        return self

    def invoke(self, messages):
        self.messages = messages
        return self.output


class CapturingCallableLLM:
    def __init__(self, output):
        self.output = output
        self.payload = None

    def __call__(self, payload):
        self.payload = payload
        return self.output


def test_structured_llm_fixture_maps_all_supported_condition_groups() -> None:
    llm = CapturingStructuredLLM(
        {
            "hard_conditions": {
                "required_course_names": ["고전읽기와토론"],
                "excluded_course_names": ["스포츠댄스"],
                "excluded_days": ["FRI"],
                "earliest_start_time": "10:00",
            },
            "soft_conditions": {
                "preferred_course_names": ["대학영어"],
                "preferred_elective_areas": [2, 5],
                "preferred_first_class_time": "10:30",
            },
            "unsupported_conditions": [
                {
                    "source_text": "과제가 적은 수업",
                    "reason_code": "DATA_NOT_AVAILABLE",
                    "reason": "현재 데이터에서는 과제량을 확인할 수 없습니다.",
                }
            ],
            "warnings": [
                {
                    "code": "AMBIGUOUS_CONDITION_STRENGTH",
                    "message": "애매한 표현을 soft 조건으로 해석했습니다.",
                    "source_text": "오전 수업은 싫어",
                }
            ],
        }
    )

    result = parse_general_preferences(
        "금요일은 절대 안 되고 고전읽기와토론은 꼭, 대학영어는 가능하면 듣고 싶어.",
        llm=llm,
    )

    assert llm.schema is GeneralPreferenceLLMOutput
    assert llm.messages[0] == ("system", GENERAL_PREFERENCE_SYSTEM_PROMPT)
    human_payload = json.loads(llm.messages[1][1])
    assert "preferred_elective_areas" in human_payload["supported_soft_fields"]
    assert human_payload["prompt"].startswith("금요일은 절대")
    assert result.hard_conditions.required_course_names == ["고전읽기와토론"]
    assert result.hard_conditions.excluded_course_names == ["스포츠댄스"]
    assert result.hard_conditions.excluded_days == [Day.FRI]
    assert result.hard_conditions.earliest_start_time == "10:00"
    assert result.soft_conditions.preferred_course_names == ["대학영어"]
    assert result.soft_conditions.preferred_elective_areas == [2, 5]
    assert result.soft_conditions.preferred_first_class_time == "10:30"
    assert result.unsupported_conditions[0].source_text == "과제가 적은 수업"
    assert result.warnings[0].code == "AMBIGUOUS_CONDITION_STRENGTH"


def test_preferred_course_names_are_preserved_without_becoming_required() -> None:
    result = parse_general_preferences(
        "가능하면 대학영어를 듣고 싶어.",
        llm=CapturingStructuredLLM(
            {"soft_conditions": {"preferred_course_names": ["대학영어"]}}
        ),
    )

    assert result.soft_conditions.preferred_course_names == ["대학영어"]
    assert result.hard_conditions.required_course_names == []


def test_preferred_elective_areas_are_preserved_independently_from_course_names() -> None:
    result = parse_general_preferences(
        "2영역이나 5영역 교양이면 좋아.",
        llm=CapturingStructuredLLM(
            {"soft_conditions": {"preferred_elective_areas": [2, 5]}}
        ),
    )

    assert result.soft_conditions.preferred_elective_areas == [2, 5]
    assert result.soft_conditions.preferred_course_names == []


def test_invalid_day_enum_is_rejected_with_standard_parser_error() -> None:
    with pytest.raises(AppError) as exc_info:
        parse_general_preferences(
            "주말 수업은 싫어.",
            llm=CapturingStructuredLLM(
                {"hard_conditions": {"excluded_days": ["HOLIDAY"]}}
            ),
        )

    assert exc_info.value.code == "INVALID_PREFERENCE_OUTPUT"


def test_missing_fields_use_safe_defaults() -> None:
    result = parse_general_preferences(
        "조건 없어.",
        llm=CapturingStructuredLLM({}),
    )

    assert result.hard_conditions.required_course_names == []
    assert result.soft_conditions.preferred_elective_areas == []
    assert result.unsupported_conditions == []
    assert result.warnings == []


def test_unknown_fields_follow_current_strict_schema_policy() -> None:
    with pytest.raises(AppError) as exc_info:
        parse_general_preferences(
            "팀플 없는 수업.",
            llm=CapturingStructuredLLM({"soft_conditions": {"low_team_project": True}}),
        )

    assert exc_info.value.code == "INVALID_PREFERENCE_OUTPUT"


def test_callable_llm_receives_prompt_system_and_schema_without_network() -> None:
    llm = CapturingCallableLLM(
        {
            "soft_conditions": {"preferred_free_days": ["FRI"]},
            "unsupported_conditions": [
                {
                    "source_text": "한글 조건",
                    "reason_code": "DATA_NOT_AVAILABLE",
                    "reason": "현재 데이터에서는 확인할 수 없습니다.",
                }
            ],
        }
    )

    result = GeneralPreferenceParser(llm=llm).parse("금요일은 가능하면 쉬고 한글 조건도 원해")

    assert llm.payload["system"] == GENERAL_PREFERENCE_SYSTEM_PROMPT
    assert llm.payload["prompt"] == "금요일은 가능하면 쉬고 한글 조건도 원해"
    assert llm.payload["schema"] == "GeneralPreferenceLLMOutput"
    assert result.soft_conditions.preferred_free_days == [Day.FRI]
    assert result.unsupported_conditions[0].source_text == "한글 조건"


def test_malformed_json_output_raises_standard_parser_error() -> None:
    with pytest.raises(AppError) as exc_info:
        parse_general_preferences(
            "금요일은 쉬고 싶어.",
            llm=CapturingStructuredLLM('{"soft_conditions": '),
        )

    assert exc_info.value.code == "INVALID_PREFERENCE_OUTPUT"


def test_korean_course_names_and_weekdays_are_not_mutated() -> None:
    result = parse_general_preferences(
        "대학영어는 듣고 금요일은 피하고 싶어.",
        llm=CapturingStructuredLLM(
            {
                "hard_conditions": {"excluded_days": ["FRI"]},
                "soft_conditions": {"preferred_course_names": ["대학영어"]},
            }
        ),
    )

    assert result.hard_conditions.excluded_days == [Day.FRI]
    assert result.soft_conditions.preferred_course_names == ["대학영어"]
