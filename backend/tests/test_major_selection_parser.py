"""Unit and opt-in integration tests for the major-selection parser.

Fake LLM tests do not inspect the model's natural-language understanding. They
verify output schema validation, exception handling, normalization,
deduplication, OpenAI-compatible tool-call parsing, and matcher handoff cases.
Only the opt-in integration test checks real LLM parsing accuracy.
"""

import json
import os

import pytest
from pydantic import ValidationError

from backend.app.models import Category, ClassTime, Course, Day, MajorSelectionParseResult
from backend.app.services.llm_preference_parser import load_proxy_env
from backend.app.services.openai_client import has_openai_api_key
from backend.app.services.major_course_matcher import (
    INVALID_ZERO_SECTION_REASON,
    MajorCourseMatcher,
)
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


def _normalize_ambiguous_texts(texts: list[str]) -> list[str]:
    return [_normalize_ambiguous_text(text) for text in texts]


def _normalize_ambiguous_text(text: str) -> str:
    return " ".join(text.strip().rstrip(".。").split())


def test_prompt_limits_major_parser_role() -> None:
    payload = build_major_selection_parse_payload(
        prompt="자료구조 001분반이랑 컴퓨터구조 003분반 들을 거야",
    )

    assert "전공 과목을 추천하거나" in SYSTEM_PROMPT
    assert "분반이 명시되지 않았다면" in SYSTEM_PROMPT
    assert "교수명이나 수업 시간을 근거로" in SYSTEM_PROMPT
    assert "실제 과목 또는 분반의 존재 여부는 판단하지 마세요" in SYSTEM_PROMPT
    assert "추천 과목을 요청하면" in SYSTEM_PROMPT
    assert payload["prompt"] == "자료구조 001분반이랑 컴퓨터구조 003분반 들을 거야"
    assert "Do not infer a section" in payload["instruction"]
    assert "recommended additional major courses" in payload["instruction"]


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


def test_duplicate_same_course_and_same_section_is_removed() -> None:
    result = _parse(
        "자료구조 001분반 자료구조 001분반",
        {
            "selected_courses": [
                {"course_name": "자료구조", "section": "001"},
                {"course_name": "자료구조", "section": "001"},
            ],
            "ambiguous_texts": [],
        },
    )

    assert [(c.course_name, c.section) for c in result.selected_courses] == [
        ("자료구조", "1")
    ]


def test_equivalent_numeric_sections_are_deduplicated() -> None:
    result = _parse(
        "자료구조 001분반 자료구조 01분반 자료구조 1분반 자료구조 001 분반",
        {
            "selected_courses": [
                {"course_name": "자료구조", "section": "001"},
                {"course_name": "자료구조", "section": "01"},
                {"course_name": "자료구조", "section": "1"},
                {"course_name": "자료구조", "section": "001분반"},
            ],
            "ambiguous_texts": [],
        },
    )

    assert [(c.course_name, c.section) for c in result.selected_courses] == [
        ("자료구조", "1")
    ]


def test_duplicate_course_without_section_is_removed() -> None:
    result = _parse(
        "자료구조를 들을 거야. 자료구조는 분반 아직 몰라.",
        {
            "selected_courses": [
                {"course_name": "자료구조", "section": None},
                {"course_name": "자료 구조", "section": None},
            ],
            "ambiguous_texts": [],
        },
    )

    assert [(c.course_name, c.section) for c in result.selected_courses] == [
        ("자료구조", None)
    ]


def test_negative_course_example_keeps_only_confirmed_selection() -> None:
    result = _parse(
        "자료구조는 안 듣고 컴퓨터구조 003분반만 들을 거야",
        {
            "selected_courses": [
                {"course_name": "컴퓨터구조", "section": "003"},
            ],
            "ambiguous_texts": [],
        },
    )

    assert [(c.course_name, c.section) for c in result.selected_courses] == [
        ("컴퓨터구조", "3")
    ]


def test_changed_selection_example_keeps_only_final_selection() -> None:
    result = _parse(
        "자료구조 001분반 대신 003분반으로 할게",
        {
            "selected_courses": [
                {"course_name": "자료구조", "section": "003"},
            ],
            "ambiguous_texts": [],
        },
    )

    assert [(c.course_name, c.section) for c in result.selected_courses] == [
        ("자료구조", "3")
    ]


def test_unconfirmed_expression_example_is_preserved_as_ambiguous_text() -> None:
    result = _parse(
        "자료구조나 알고리즘 중 하나 들을 예정이야",
        {
            "selected_courses": [],
            "ambiguous_texts": ["자료구조나 알고리즘 중 하나 들을 예정이야"],
        },
    )

    assert result.selected_courses == []
    assert result.ambiguous_texts == ["자료구조나 알고리즘 중 하나 들을 예정이야"]


def test_zero_section_is_reported_with_distinct_invalid_reason() -> None:
    course = Course(
        course_id="MA100-001",
        course_name="자료구조",
        category=Category.MAJOR_REQUIRED,
        credit=3,
        division="001",
        professor="김교수",
        class_times=[
            ClassTime(
                day=Day.MON,
                start="09:00",
                end="10:15",
                classroom="제6공학관 6201",
                building_code="6201",
            )
        ],
    )
    parse_result = _parse(
        "자료구조 000분반",
        {
            "selected_courses": [
                {"course_name": "자료구조", "section": "000분반"},
            ],
            "ambiguous_texts": [],
        },
    )

    match_result = MajorCourseMatcher([course]).match(parse_result)

    assert match_result.matched == []
    assert match_result.ambiguous == []
    assert len(match_result.unmatched) == 1
    assert match_result.unmatched[0].reason == INVALID_ZERO_SECTION_REASON


def test_openai_tool_call_response_extracts_major_selection_arguments() -> None:
    output = MajorSelectionParser._result_from_chat_completions_response(
        {
            "choices": [
                {
                    "message": {
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "major_selection_from_prompt",
                                    "arguments": json.dumps(
                                        {
                                            "selected_courses": [
                                                {
                                                    "course_name": "자료구조",
                                                    "section": "001",
                                                }
                                            ],
                                            "ambiguous_texts": [],
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

    assert output == {
        "selected_courses": [{"course_name": "자료구조", "section": "001"}],
        "ambiguous_texts": [],
    }


def test_openai_tool_call_response_without_choices_raises() -> None:
    with pytest.raises(ValueError, match="choices"):
        MajorSelectionParser._result_from_chat_completions_response({})


def test_openai_tool_call_response_without_tool_calls_raises() -> None:
    with pytest.raises(ValueError, match="tool call"):
        MajorSelectionParser._result_from_chat_completions_response(
            {"choices": [{"message": {}}]}
        )


def test_openai_tool_call_response_with_invalid_json_arguments_raises() -> None:
    with pytest.raises(json.JSONDecodeError):
        MajorSelectionParser._result_from_chat_completions_response(
            {
                "choices": [
                    {
                        "message": {
                            "tool_calls": [
                                {"function": {"arguments": "{not-json"}}
                            ]
                        }
                    }
                ]
            }
        )


def test_openai_tool_call_response_with_invalid_schema_arguments_raises() -> None:
    with pytest.raises(ValidationError):
        MajorSelectionParser._result_from_chat_completions_response(
            {
                "choices": [
                    {
                        "message": {
                            "tool_calls": [
                                {
                                    "function": {
                                        "arguments": json.dumps(
                                            {
                                                "selected_courses": [
                                                    {"section": "001"}
                                                ],
                                                "ambiguous_texts": [],
                                            },
                                            ensure_ascii=False,
                                        )
                                    }
                                }
                            ]
                        }
                    }
                ]
            }
        )


@pytest.mark.integration
def test_real_llm_major_selection_accuracy_cases_are_opt_in() -> None:
    """Validate real LLM natural-language parsing only when explicitly enabled."""

    if os.getenv("RUN_MAJOR_SELECTION_INTEGRATION") != "1":
        pytest.skip("set RUN_MAJOR_SELECTION_INTEGRATION=1 to call the real LLM")
    load_proxy_env()
    if not has_openai_api_key(os.getenv("OPENAI_API_KEY")):
        pytest.skip("OPENAI_API_KEY is not configured")

    cases = [
        {
            "prompt": "자료구조 001분반과 컴퓨터구조 003분반",
            "expected_courses": [
                ("자료구조", "1"),
                ("컴퓨터구조", "3"),
            ],
            "expected_ambiguous": [],
        },
        {
            "prompt": "자료구조를 들을 거야",
            "expected_courses": [
                ("자료구조", None),
            ],
            "expected_ambiguous": [],
        },
        {
            "prompt": "자료구조는 안 듣고 컴퓨터구조 003분반만",
            "expected_courses": [
                ("컴퓨터구조", "3"),
            ],
            "expected_ambiguous": [],
        },
        {
            "prompt": "자료구조 001분반 대신 003분반으로 할게",
            "expected_courses": [
                ("자료구조", "3"),
            ],
            "expected_ambiguous": [],
        },
        {
            "prompt": "자료구조나 알고리즘 중 하나 들을 예정",
            "expected_courses": [],
            "expected_ambiguous": [
                "자료구조나 알고리즘 중 하나 들을 예정",
            ],
        },
        {
            "prompt": "자료구조 001분반은 고민 중이고 컴퓨터구조는 들을 거야",
            "expected_courses": [
                ("컴퓨터구조", None),
            ],
            "expected_ambiguous": [
                "자료구조 001분반은 고민 중이고 컴퓨터구조는 들을 거야",
            ],
        },
        {
            "prompt": "김교수님 자료구조를 들을 거야",
            "expected_courses": [
                ("자료구조", None),
            ],
            "expected_ambiguous": [],
        },
    ]

    for case in cases:
        result = parse_major_selection(case["prompt"])
        actual_courses = [
            (course.course_name, course.section)
            for course in result.selected_courses
        ]
        actual_ambiguous = _normalize_ambiguous_texts(result.ambiguous_texts)
        expected_ambiguous = _normalize_ambiguous_texts(case["expected_ambiguous"])
        message = json.dumps(
            {
                "prompt": case["prompt"],
                "expected_courses": case["expected_courses"],
                "actual_courses": actual_courses,
                "expected_ambiguous": expected_ambiguous,
                "actual_ambiguous": actual_ambiguous,
            },
            ensure_ascii=False,
            indent=2,
        )

        assert actual_courses == case["expected_courses"], message
        assert actual_ambiguous == expected_ambiguous, message
