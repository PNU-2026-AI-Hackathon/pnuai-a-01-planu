"""Regression tests for traceable LLM preference parsing."""

from backend.app.models import Day, PreferenceParseStatus, PreferenceRules
from backend.app.services.llm_preference_parser import (
    DEFAULT_CHAT_PROXY_URL,
    DEFAULT_OPENAI_MODEL,
    PROXY_TOKEN_PLACEHOLDER,
    LLMPreferenceParser,
    parse_preferences_with_trace,
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


def test_parse_preferences_with_trace_uses_structured_output() -> None:
    selected = PreferenceRules(prefer_late_start=True)
    result = parse_preferences_with_trace(
        free_text="금요일은 공강이면 좋고 오전 수업은 피하고 싶어요.",
        selected_preferences=selected,
        llm=FakeStructuredLLM(
            {
                "preferred_free_days": ["FRI"],
                "avoid_morning_classes": True,
            }
        ),
    )

    assert result.status == PreferenceParseStatus.SUCCESS
    assert result.fallback_used is False
    assert result.llm_preferences.preferred_free_days == [Day.FRI]
    assert result.merged_preferences.prefer_late_start is True
    assert result.merged_preferences.avoid_morning_classes is True
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
    monkeypatch.setenv("PROXY_TOKEN", PROXY_TOKEN_PLACEHOLDER)
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
    assert "PROXY_TOKEN" in (result.trace[-1].error or "")


def test_parse_preferences_skips_empty_free_text() -> None:
    selected = PreferenceRules(no_morning_classes=True)
    result = parse_preferences_with_trace(
        free_text="   ",
        selected_preferences=selected,
    )

    assert result.status == PreferenceParseStatus.SKIPPED
    assert result.merged_preferences.no_morning_classes is True
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


def test_parser_defaults_match_proxy_repo_settings(monkeypatch) -> None:
    monkeypatch.setenv("PROXY_TOKEN", PROXY_TOKEN_PLACEHOLDER)
    parser = LLMPreferenceParser()

    assert parser.model_name == DEFAULT_OPENAI_MODEL
    assert parser.base_url == DEFAULT_CHAT_PROXY_URL
    assert parser.proxy_token == PROXY_TOKEN_PLACEHOLDER


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
                avoid_morning_classes=True,
            )
        }
    )

    assert output == {
        "preferred_free_days": ["FRI"],
        "avoid_morning_classes": True,
    }
