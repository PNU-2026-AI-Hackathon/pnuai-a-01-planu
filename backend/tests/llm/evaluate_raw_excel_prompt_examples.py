"""Evaluate raw Excel prompt examples against the live OpenAI parser."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from backend.app.services.course_name_matcher import course_name_matches
from backend.app.services.llm_preference_parser import (
    load_proxy_env,
    parse_preferences_with_trace,
)
from backend.app.services.openai_client import has_openai_api_key


EXAMPLES_PATH = Path(__file__).with_name("raw_excel_prompt_examples.json")


def main() -> int:
    load_proxy_env()
    if not has_openai_api_key(os.getenv("OPENAI_API_KEY")):
        raise SystemExit("OPENAI_API_KEY is not configured")

    examples = json.loads(EXAMPLES_PATH.read_text(encoding="utf-8"))
    results = [evaluate_case(case) for case in examples]
    summary = {
        "total": len(results),
        "passed": sum(1 for result in results if result["passed"]),
        "failed": sum(1 for result in results if not result["passed"]),
        "results": results,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["failed"] == 0 else 1


def evaluate_case(case: dict[str, Any]) -> dict[str, Any]:
    result = parse_preferences_with_trace(free_text=case["input"])
    rules = result.llm_preferences
    dump = rules.model_dump(mode="json")
    checks: list[dict[str, Any]] = []

    if "expected_fields" in case:
        for field_name, expected in case["expected_fields"].items():
            checks.append(_field_check(field_name, expected, dump.get(field_name) or []))
    else:
        field_name = case["expected_field"]
        checks.append(
            _field_check(
                field_name,
                case["expected_extracted_names"],
                dump.get(field_name) or [],
            )
        )

    if "catalog_matches" in case:
        for user_name, catalog_name in case["catalog_matches"].items():
            checks.append(_match_check(user_name, catalog_name))
    else:
        actual_names = dump.get(case["expected_field"]) or []
        checks.extend(
            _match_check(name, case["catalog_course_name"])
            for name in actual_names
        )

    passed = result.status == "success" and all(check["passed"] for check in checks)
    return {
        "id": case["id"],
        "input": case["input"],
        "status": result.status,
        "passed": passed,
        "actual_rules": rules.model_dump(mode="json", exclude_unset=True),
        "checks": checks,
        "trace_tools": [event.tool for event in result.trace],
    }


def _field_check(field_name: str, expected: list[str], actual: list[str]) -> dict[str, Any]:
    return {
        "type": "field",
        "field": field_name,
        "expected": expected,
        "actual": actual,
        "passed": actual == expected,
    }


def _match_check(user_name: str, catalog_name: str) -> dict[str, Any]:
    return {
        "type": "catalog_match",
        "user_name": user_name,
        "catalog_name": catalog_name,
        "passed": course_name_matches(user_name, catalog_name),
    }


if __name__ == "__main__":
    raise SystemExit(main())
