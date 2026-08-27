"""LLM-backed regression tests for natural-language preference parsing."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from backend.app.models import PreferenceParseStatus, PreferenceRules, time_to_minutes
from backend.app.services.llm_preference_parser import load_proxy_env, parse_preferences_with_trace
from backend.app.services.openai_client import has_openai_api_key


CASES_PATH = Path(__file__).with_name("cases") / "preference_cases.json"
LEGACY_CASES_PATH = Path(__file__).with_name("preference_cases.json")
FIELD_ALIASES = {
    "disliked_course_names": "avoided_course_names",
}
SET_FIELDS = {
    "required_course_names",
    "preferred_course_names",
    "excluded_course_names",
    "avoided_course_names",
    "preferred_elective_areas",
}
TIME_FIELDS = {
    "earliest_start_time",
    "latest_end_time",
    "preferred_first_class_time",
}


def _load_cases() -> list[dict[str, Any]]:
    path = CASES_PATH if CASES_PATH.exists() else LEGACY_CASES_PATH
    return json.loads(path.read_text(encoding="utf-8"))


def _case_ids(cases: list[dict[str, Any]]) -> list[str]:
    return [case["id"] for case in cases]


def _actual_value(rules: PreferenceRules, field_name: str) -> Any:
    return getattr(rules, FIELD_ALIASES.get(field_name, field_name))


def _normalize_expected_field(field_name: str) -> str:
    return FIELD_ALIASES.get(field_name, field_name)


def _normalize_time(value: Any) -> int | None:
    if value is None:
        return None
    if hasattr(value, "hour") and hasattr(value, "minute"):
        return int(value.hour) * 60 + int(value.minute)
    return time_to_minutes(str(value))


def _assert_field_matches(
    *,
    case: dict[str, Any],
    rules: PreferenceRules,
    field_name: str,
    expected: Any,
    trace_ids: list[str],
) -> None:
    actual_field = _normalize_expected_field(field_name)
    actual = _actual_value(rules, field_name)
    message = _failure_message(
        case=case,
        field_name=actual_field,
        expected=expected,
        actual=actual,
        rules=rules,
        trace_ids=trace_ids,
    )

    if actual_field in SET_FIELDS:
        assert len(actual) == len(set(actual)), message
        assert set(actual) == set(expected), message
    elif actual_field in TIME_FIELDS:
        assert _normalize_time(actual) == _normalize_time(expected), message
    else:
        assert actual == expected, message


def _assert_field_empty(
    *,
    case: dict[str, Any],
    rules: PreferenceRules,
    field_name: str,
    trace_ids: list[str],
) -> None:
    actual_field = _normalize_expected_field(field_name)
    actual = _actual_value(rules, field_name)
    message = _failure_message(
        case=case,
        field_name=actual_field,
        expected=[],
        actual=actual,
        rules=rules,
        trace_ids=trace_ids,
    )
    assert actual in (None, []), message


def _trace_ids(result: Any) -> list[str]:
    ids: list[str] = []
    for tool in result.used_tools:
        trace_id = tool.metadata.get("id")
        if trace_id:
            ids.append(str(trace_id))
    return ids


def _failure_message(
    *,
    case: dict[str, Any],
    field_name: str,
    expected: Any,
    actual: Any,
    rules: PreferenceRules,
    trace_ids: list[str],
) -> str:
    payload = {
        "case_id": case["id"],
        "input": case["input"],
        "field": field_name,
        "expected": expected,
        "actual": actual,
        "actual_rules": rules.model_dump(mode="json"),
        "trace_ids": trace_ids,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


CASES = _load_cases()


@pytest.mark.llm_eval
@pytest.mark.parametrize("case", CASES, ids=_case_ids(CASES))
def test_llm_preference_cases(case: dict[str, Any]) -> None:
    load_proxy_env()
    import os

    if not has_openai_api_key(os.getenv("OPENAI_API_KEY")):
        pytest.skip("OPENAI_API_KEY is not configured; skipping real LLM evaluation")

    result = parse_preferences_with_trace(free_text=case["input"])
    trace_ids = _trace_ids(result)
    assert result.status == PreferenceParseStatus.SUCCESS, json.dumps(
        {
            "case_id": case["id"],
            "input": case["input"],
            "status": result.status,
            "warnings": result.warnings,
            "trace": [event.model_dump(mode="json") for event in result.trace],
            "trace_ids": trace_ids,
        },
        ensure_ascii=False,
        indent=2,
    )

    rules = result.llm_preferences
    for field_name, expected in case.get("expected", {}).items():
        _assert_field_matches(
            case=case,
            rules=rules,
            field_name=field_name,
            expected=expected,
            trace_ids=trace_ids,
        )
    for field_name in case.get("expected_empty", []):
        _assert_field_empty(
            case=case,
            rules=rules,
            field_name=field_name,
            trace_ids=trace_ids,
        )
