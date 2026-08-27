"""Regression tests for traceable LLM preference parsing."""

import json

from backend.app.models import Day, PreferenceParseStatus, PreferenceRules
from backend.app.services.llm_preference_parser import (
    DEFAULT_CHAT_PROXY_URL,
    DEFAULT_OPENAI_MODEL,
    PROXY_TOKEN_PLACEHOLDER,
    SYSTEM_PROMPT,
    LLMPreferenceParser,
    build_preference_parse_payload,
    chat_completions_url,
    parse_preferences_with_trace,
    should_use_direct_proxy_client,
)


class FakeStructuredLLM:
    def __init__(self, output):
        self.output = output
        self.schema = None

    def with_structured_output(self, schema):
        self.schema = schema
        return self

    def invoke(self, messages):
        assert self.schema is PreferenceRules
        assert messages[0][0] == "system"
        return self.output


def _parse_with_output(free_text: str, output: dict) -> PreferenceRules:
    return parse_preferences_with_trace(
        free_text=free_text,
        llm=FakeStructuredLLM(output),
    ).llm_preferences


def _weekday_lunch_ranges() -> list[dict[str, str]]:
    return [
        {"day": day, "start": "12:00", "end": "13:00"}
        for day in ["MON", "TUE", "WED", "THU", "FRI"]
    ]


def test_prompt_and_schema_describe_soft_course_name_preferences() -> None:
    schema = PreferenceRules.model_json_schema()
    preferred_description = schema["properties"]["preferred_course_names"]["description"]
    required_description = schema["properties"]["required_course_names"]["description"]
    payload = build_preference_parse_payload(
        free_text="가능하면 대학영어를 듣고 싶어.",
        selected_preferences=PreferenceRules(),
    )

    assert "preferred_course_names" in SYSTEM_PROMPT
    assert "Soft course-name preferences are valid parser results and must not be ignored" in SYSTEM_PROMPT
    assert "가능하면 대학영어를 듣고 싶어" in SYSTEM_PROMPT
    assert "required_course_names" in SYSTEM_PROMPT
    assert "nickname or abbreviation" in SYSTEM_PROMPT
    assert "positive soft preferences" in preferred_description
    assert "가능하면 대학영어를 듣고 싶어" in preferred_description
    assert "hard requirements" in required_description
    assert "preferred_course_names" in payload["instruction"]
    assert "Do not omit it merely because it is optional" in payload["instruction"]
    assert "nicknames or abbreviations" in payload["instruction"]


def test_soft_course_name_phrases_map_to_preferred_course_names() -> None:
    cases = [
        "가능하면 대학영어를 듣고 싶어.",
        "대학영어를 선호해.",
        "대학영어가 시간표에 있으면 좋겠어.",
        "꼭 들어야 하는 건 아니지만 대학영어를 듣고 싶어.",
    ]

    for text in cases:
        rules = _parse_with_output(
            text,
            {"preferred_course_names": ["대학영어"]},
        )
        assert rules.preferred_course_names == ["대학영어"], (
            text,
            rules.model_dump(mode="json"),
        )
        assert rules.required_course_names == []


def test_hard_course_name_phrase_stays_required_not_preferred() -> None:
    rules = _parse_with_output(
        "대학영어는 반드시 넣어줘.",
        {"required_course_names": ["대학영어"]},
    )

    assert rules.required_course_names == ["대학영어"]
    assert rules.preferred_course_names == []


def test_non_concrete_course_descriptions_do_not_create_preferred_names() -> None:
    rules = _parse_with_output(
        "재미있는 영어 관련 수업을 듣고 싶어.",
        {},
    )

    assert rules.preferred_course_names == []
    assert rules.required_course_names == []


def test_broad_subject_terms_do_not_create_preferred_names() -> None:
    rules = _parse_with_output(
        "인문학 관련은 좋아하지만 민주주의론은 절대 듣고 싶지 않아.",
        {
            "preferred_course_names": ["인문학"],
            "excluded_course_names": ["민주주의론"],
        },
    )

    assert rules.preferred_course_names == []
    assert rules.excluded_course_names == ["민주주의론"]


def test_morning_hard_condition_uses_earliest_start_time() -> None:
    rules = _parse_with_output(
        "아침 수업은 절대 안 돼.",
        {"earliest_start_time": "10:00"},
    )

    assert rules.earliest_start_time == "10:00"
    assert rules.preferred_first_class_time is None


def test_morning_soft_condition_uses_preferred_first_class_time() -> None:
    rules = _parse_with_output(
        "가능하면 아침 수업은 피하고 싶어.",
        {"preferred_first_class_time": "10:00"},
    )

    assert rules.preferred_first_class_time == "10:00"
    assert rules.earliest_start_time is None


def test_concrete_morning_time_wins_default() -> None:
    rules = _parse_with_output(
        "11시 이전 수업은 절대 안 돼.",
        {"earliest_start_time": "11:00"},
    )

    assert rules.earliest_start_time == "11:00"


def test_morning_hard_and_soft_can_be_combined_when_separate() -> None:
    rules = _parse_with_output(
        "10시 전 수업은 안 되고 가능하면 11시 이후에 시작하고 싶어.",
        {
            "earliest_start_time": "10:00",
            "preferred_first_class_time": "11:00",
        },
    )

    assert rules.earliest_start_time == "10:00"
    assert rules.preferred_first_class_time == "11:00"


def test_lunch_soft_condition_expands_to_weekdays() -> None:
    rules = _parse_with_output(
        "점심시간에는 수업이 없었으면 좋겠어.",
        {"preferred_free_time_ranges": _weekday_lunch_ranges()},
    )

    assert [item.model_dump(mode="json") for item in rules.preferred_free_time_ranges] == _weekday_lunch_ranges()


def test_lunch_hard_condition_expands_to_weekdays() -> None:
    rules = _parse_with_output(
        "점심시간에는 절대 수업을 넣지 마.",
        {"excluded_time_ranges": _weekday_lunch_ranges()},
    )

    assert [item.model_dump(mode="json") for item in rules.excluded_time_ranges] == _weekday_lunch_ranges()


def test_course_name_strength_fields() -> None:
    rules = _parse_with_output(
        "대학영어는 반드시 넣고 가능하면 고전읽기와토론을 듣고 싶고 "
        "컴퓨팅사고와인공지능은 절대 넣지 말고 열린사고와표현은 가능하면 피하고 싶어.",
        {
            "required_course_names": ["대학영어"],
            "preferred_course_names": ["고전읽기와토론"],
            "excluded_course_names": ["컴퓨팅사고와인공지능"],
            "avoided_course_names": ["열린사고와표현"],
        },
    )

    assert rules.required_course_names == ["대학영어"]
    assert rules.preferred_course_names == ["고전읽기와토론"]
    assert rules.excluded_course_names == ["컴퓨팅사고와인공지능"]
    assert rules.avoided_course_names == ["열린사고와표현"]


def test_unsupported_conditions_do_not_create_course_names() -> None:
    rules = _parse_with_output(
        "발표 없고 학점 잘 주는 수업을 듣고 싶어.",
        {},
    )

    assert rules.required_course_names == []
    assert rules.preferred_course_names == []
    assert rules.excluded_course_names == []
    assert rules.avoided_course_names == []


def test_parse_preferences_with_trace_uses_structured_output() -> None:
    selected = PreferenceRules(preferred_first_class_time="11:00")
    result = parse_preferences_with_trace(
        free_text="금요일은 공강이면 좋고 오전 수업은 피하고 싶어요.",
        selected_preferences=selected,
        llm=FakeStructuredLLM(
            {
                "preferred_free_days": ["FRI"],
                "preferred_course_names": ["고전읽기와토론"],
            }
        ),
    )

    assert result.status == PreferenceParseStatus.SUCCESS
    assert result.fallback_used is False
    assert result.llm_preferences.preferred_free_days == [Day.FRI]
    assert result.merged_preferences.preferred_first_class_time == "11:00"
    assert result.merged_preferences.preferred_course_names == ["고전읽기와토론"]
    assert [tool.name for tool in result.used_tools] == [
        "preference_payload_builder",
        "langchain_structured_output",
        "langchain_structured_output",
        "pydantic_preference_validator",
        "pydantic_preference_validator",
        "domain_preference_validator",
        "domain_preference_validator",
        "preference_rule_merger",
    ]
    assert result.trace[-1].tool == "preference_rule_merger"
    assert result.trace[-2].tool == "domain_preference_validator"
    assert result.trace[-2].output == {
        "hard_filter_count": 0,
        "soft_preference_count": 2,
    }


def test_parse_preferences_falls_back_when_llm_is_unavailable(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", PROXY_TOKEN_PLACEHOLDER)
    selected = PreferenceRules(preferred_free_days=["MON"])
    result = parse_preferences_with_trace(
        free_text="금요일 공강도 원해요.",
        selected_preferences=selected,
    )

    assert result.status == PreferenceParseStatus.FALLBACK
    assert result.fallback_used is True
    assert result.warnings == ["LLM_PARSE_FALLBACK"]
    assert result.llm_preferences == PreferenceRules()
    assert result.merged_preferences.preferred_free_days == [Day.MON]
    assert result.trace[-1].tool == "llm_parse_fallback"
    assert "OPENAI_API_KEY" in (result.trace[-1].error or "")


def test_parse_preferences_skips_empty_free_text() -> None:
    selected = PreferenceRules(earliest_start_time="10:00")
    result = parse_preferences_with_trace(
        free_text="   ",
        selected_preferences=selected,
    )

    assert result.status == PreferenceParseStatus.SKIPPED
    assert result.merged_preferences.earliest_start_time == "10:00"
    assert result.llm_preferences == PreferenceRules()
    assert result.trace[-1].tool == "input_guard"


def test_parse_preferences_records_validation_error_trace() -> None:
    result = parse_preferences_with_trace(
        free_text="월요일은 25시 이후만 가능해요.",
        llm=FakeStructuredLLM({"earliest_start_time": "25:00"}),
    )

    assert result.status == PreferenceParseStatus.FALLBACK
    assert result.trace[-2].tool == "pydantic_preference_validator"
    assert result.trace[-2].status == "error"
    assert "time must be a valid 24-hour time" in (result.trace[-2].error or "")


def test_parser_defaults_match_openai_settings(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", PROXY_TOKEN_PLACEHOLDER)
    parser = LLMPreferenceParser()

    assert parser.model_name == DEFAULT_OPENAI_MODEL
    assert parser.base_url == DEFAULT_CHAT_PROXY_URL
    assert parser.proxy_token == PROXY_TOKEN_PLACEHOLDER


def test_python_314_uses_direct_proxy_client() -> None:
    assert should_use_direct_proxy_client() is True


def test_chat_completions_url_appends_endpoint_once() -> None:
    assert chat_completions_url("https://example.test/v1") == (
        "https://example.test/v1/chat/completions"
    )
    assert chat_completions_url("https://example.test/v1/chat/completions") == (
        "https://example.test/v1/chat/completions"
    )


def test_direct_tool_call_request_uses_function_tool(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", PROXY_TOKEN_PLACEHOLDER)
    parser = LLMPreferenceParser()
    payload = build_preference_parse_payload(
        free_text="가능하면 대학영어를 듣고 싶어.",
        selected_preferences=PreferenceRules(),
    )

    request_payload = parser._tool_call_request_payload(payload)

    assert request_payload["tools"][0]["type"] == "function"
    assert request_payload["tools"][0]["function"]["name"] == (
        "preference_rules_from_prompt"
    )
    assert request_payload["tool_choice"] == {
        "type": "function",
        "function": {"name": "preference_rules_from_prompt"},
    }
    assert "preferred_course_names" in request_payload["tools"][0]["function"]["parameters"]["properties"]


def test_direct_tool_call_response_extracts_rules_and_trace(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", PROXY_TOKEN_PLACEHOLDER)
    parser = LLMPreferenceParser()
    used_tools = []
    trace = []

    output = parser._rules_from_chat_completions_response(
        {
            "choices": [
                {
                    "message": {
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "type": "function",
                                "function": {
                                    "name": "preference_rules_from_prompt",
                                    "arguments": json.dumps(
                                        {"preferred_course_names": ["대학영어"]},
                                        ensure_ascii=False,
                                    ),
                                },
                            }
                        ]
                    }
                }
            ]
        },
        used_tools,
        trace,
    )

    assert output == {"preferred_course_names": ["대학영어"]}
    assert trace[0].tool == "preference_rules_from_prompt"
    assert trace[0].input == {"preferred_course_names": ["대학영어"]}
    assert trace[1].output["preference_rules"] == {
        "preferred_course_names": ["대학영어"]
    }


def test_agent_tool_error_string_is_wrapped_for_trace() -> None:
    used_tools = []
    trace = []

    LLMPreferenceParser._record_agent_event(
        used_tools,
        trace,
        {
            "event": "tool_result",
            "tool_name": "preference_rules_from_prompt",
            "content": "Error invoking tool 'preference_rules_from_prompt'",
            "id": "call_1",
        },
    )

    assert trace[0].output == {
        "value": "Error invoking tool 'preference_rules_from_prompt'"
    }


def test_tool_strategy_structured_response_is_used_directly() -> None:
    output = LLMPreferenceParser._rules_from_agent_result(
        {
            "structured_response": PreferenceRules(
                preferred_free_days=["FRI"],
                preferred_first_class_time="10:00",
            )
        }
    )

    assert output == {
        "preferred_free_days": ["FRI"],
        "preferred_first_class_time": "10:00",
    }


def test_ui_selected_course_name_is_removed_from_llm_preferences() -> None:
    result = parse_preferences_with_trace(
        free_text="대학영어는 반드시 넣고 아침 수업은 피하고 싶어.",
        selected_preferences=PreferenceRules(required_course_names=["대학영어"]),
        llm=FakeStructuredLLM(
            {
                "required_course_names": ["대학영어"],
                "preferred_first_class_time": "10:00",
            }
        ),
    )

    assert result.llm_preferences.required_course_names == []
    assert result.llm_preferences.preferred_first_class_time == "10:00"
    assert result.merged_preferences.required_course_names == ["대학영어"]
    assert result.merged_preferences.preferred_first_class_time == "10:00"


def test_ui_selected_preferred_course_name_is_removed_from_llm_preferences() -> None:
    result = parse_preferences_with_trace(
        free_text="가능하면 대학영어를 듣고 싶고 아침 수업은 피하고 싶어.",
        selected_preferences=PreferenceRules(preferred_course_names=["대학영어"]),
        llm=FakeStructuredLLM(
            {
                "preferred_course_names": ["대학영어"],
                "preferred_first_class_time": "10:00",
            }
        ),
    )

    assert result.llm_preferences.preferred_course_names == [], (
        result.trace,
        result.llm_preferences.model_dump(mode="json"),
    )
    assert result.llm_preferences.preferred_first_class_time == "10:00"
    assert result.merged_preferences.preferred_course_names == ["대학영어"]
