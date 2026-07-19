"""Tests for parsing user-selected major courses from natural language."""

import json

import pytest

from backend.app.models import MajorSelectionParseResult
from backend.app.services.major_selection_parser import (
    EmptyMajorSelectionPromptError,
    InvalidMajorSelectionOutputError,
    MajorSelectionLLMError,
    MajorSelectionLLMTimeoutError,
    MajorSelectionParser,
    SYSTEM_PROMPT,
    build_major_selection_parse_payload,
    parse_major_selection,
)


class FakeStructuredLLM:
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


class RaisingStructuredLLM:
    def __init__(self, exc: Exception):
        self.exc = exc

    def with_structured_output(self, schema):
        return self

    def invoke(self, messages):
        raise self.exc


def _parse(prompt: str, output: dict) -> MajorSelectionParseResult:
    return parse_major_selection(prompt, llm=FakeStructuredLLM(output))


def test_prompt_limits_major_parser_role() -> None:
    payload = build_major_selection_parse_payload(
        prompt="자료구조 001분반이랑 컴퓨터구조 003분반 들을 거야",
    )

    assert "전공 과목을 추천하거나" in SYSTEM_PROMPT
    assert "분반이 명시되지 않았다면" in SYSTEM_PROMPT
    assert "교수명이나 수업 시간을 근거로" in SYSTEM_PROMPT
    assert "실제 과목 또는 분반의 존재 여부는 판단하지 마세요" in SYSTEM_PROMPT
    assert payload["prompt"] == "자료구조 001분반이랑 컴퓨터구조 003분반 들을 거야"
    assert "Do not infer a section" in payload["instruction"]


def test_parse_multiple_courses_and_sections() -> None:
    result = _parse(
        "자료구조 001분반이랑 컴퓨터구조 003분반 들을 거야",
        {
            "selected_courses": [
                {"course_name": "자료구조", "section": "001"},
                {"course_name": "컴퓨터구조", "section": "003"},
            ],
            "ambiguous_texts": [],
        },
    )

    assert [course.course_name for course in result.selected_courses] == [
        "자료구조",
        "컴퓨터구조",
    ]
    assert [course.section for course in result.selected_courses] == ["1", "3"]
    assert result.ambiguous_texts == []


def test_parse_comma_and_newline_separated_input() -> None:
    result = _parse(
        "자료구조 001분반,\n컴퓨터구조 003분반",
        {
            "selected_courses": [
                {"course_name": "자료구조", "section": "001"},
                {"course_name": "컴퓨터구조", "section": "003"},
            ],
            "ambiguous_texts": [],
        },
    )

    assert [(c.course_name, c.section) for c in result.selected_courses] == [
        ("자료구조", "1"),
        ("컴퓨터구조", "3"),
    ]


def test_parse_various_section_spellings_with_existing_normalizer() -> None:
    result = _parse(
        "자료구조 1분반, 컴퓨터구조 01 분반",
        {
            "selected_courses": [
                {"course_name": "자료구조", "section": "1분반"},
                {"course_name": "컴퓨터구조", "section": "01 분반"},
            ],
            "ambiguous_texts": [],
        },
    )

    assert [course.section for course in result.selected_courses] == ["1", "1"]


def test_parse_prompt_with_unrelated_explanation() -> None:
    result = _parse(
        "이번 학기는 바쁠 것 같지만 자료구조 001분반과 컴퓨터구조 003분반을 들을 거야",
        {
            "selected_courses": [
                {"course_name": "자료구조", "section": "001"},
                {"course_name": "컴퓨터구조", "section": "003"},
            ],
            "ambiguous_texts": [],
        },
    )

    assert [course.course_name for course in result.selected_courses] == [
        "자료구조",
        "컴퓨터구조",
    ]


def test_missing_section_is_preserved_as_none() -> None:
    result = _parse(
        "자료구조를 들을 거야",
        {
            "selected_courses": [
                {"course_name": "자료구조", "section": None},
            ],
            "ambiguous_texts": [],
        },
    )

    assert result.selected_courses[0].course_name == "자료구조"
    assert result.selected_courses[0].section is None


def test_uncertain_expression_goes_to_ambiguous_texts() -> None:
    result = _parse(
        "자료구조는 들을 수도 있어",
        {
            "selected_courses": [],
            "ambiguous_texts": ["자료구조는 들을 수도 있어"],
        },
    )

    assert result.selected_courses == []
    assert result.ambiguous_texts == ["자료구조는 들을 수도 있어"]


def test_professor_name_does_not_imply_section() -> None:
    result = _parse(
        "김교수님 자료구조를 들을 거야",
        {
            "selected_courses": [
                {"course_name": "자료구조", "section": None},
            ],
            "ambiguous_texts": [],
        },
    )

    assert result.selected_courses[0].section is None


@pytest.mark.parametrize("prompt", ["", "   "])
def test_empty_prompt_raises(prompt: str) -> None:
    with pytest.raises(EmptyMajorSelectionPromptError):
        parse_major_selection(prompt, llm=FakeStructuredLLM({}))


def test_invalid_llm_output_shape_raises() -> None:
    with pytest.raises(InvalidMajorSelectionOutputError):
        parse_major_selection(
            "자료구조 001분반",
            llm=FakeStructuredLLM({"selected_courses": [{"section": "001"}]}),
        )


def test_llm_call_exception_raises_sanitized_error() -> None:
    with pytest.raises(MajorSelectionLLMError) as exc_info:
        parse_major_selection(
            "자료구조 001분반",
            llm=RaisingStructuredLLM(RuntimeError("raw secret response")),
        )

    assert str(exc_info.value) == "major selection LLM request failed"


def test_llm_timeout_raises_distinct_error() -> None:
    with pytest.raises(MajorSelectionLLMTimeoutError):
        parse_major_selection(
            "자료구조 001분반",
            llm=RaisingStructuredLLM(TimeoutError("slow")),
        )


def test_empty_structured_result_raises() -> None:
    with pytest.raises(InvalidMajorSelectionOutputError):
        parse_major_selection(
            "컴퓨터 관련 수업 하나 넣을 예정이야",
            llm=FakeStructuredLLM({"selected_courses": [], "ambiguous_texts": []}),
        )


def test_structured_llm_receives_major_selection_schema() -> None:
    llm = FakeStructuredLLM(
        {
            "selected_courses": [
                {"course_name": "자료구조", "section": "001"},
            ],
            "ambiguous_texts": [],
        }
    )

    result = parse_major_selection("자료구조 001분반", llm=llm)

    assert llm.schema is MajorSelectionParseResult
    assert llm.messages[0][0] == "system"
    assert result.selected_courses[0].section == "1"


def test_callable_llm_and_json_output_are_supported() -> None:
    def fake_llm(payload):
        assert payload["prompt"] == "자료구조 001분반"
        return json.dumps(
            {
                "selected_courses": [
                    {"course_name": "자료구조", "section": "001분반"},
                ],
                "ambiguous_texts": [],
            },
            ensure_ascii=False,
        )

    result = parse_major_selection("자료구조 001분반", llm=fake_llm)

    assert result.selected_courses[0].course_name == "자료구조"
    assert result.selected_courses[0].section == "1"
