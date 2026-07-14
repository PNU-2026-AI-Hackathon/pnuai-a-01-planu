"""Parse natural-language general-education preferences with trace output."""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from ..models.preference import (
    PreferenceParseResult,
    PreferenceParseStatus,
    PreferenceRules,
    PreferenceToolStatus,
    PreferenceToolUsage,
    PreferenceTraceEvent,
    merge_preference_rules,
)


DEFAULT_CHAT_PROXY_URL = "https://mlapi.run/4bbd0c4d-bf02-4e59-a635-457b1c30c56a/v1"
DEFAULT_OPENAI_MODEL = "openai/gpt-4.1-mini"
PROXY_TOKEN_PLACEHOLDER = "여기에 토큰 입력"
PROXY_TOKEN_PLACEHOLDERS = {PROXY_TOKEN_PLACEHOLDER, "여기에 api key 입력"}


SYSTEM_PROMPT = """You are PlaNU's preference parser.
Extract only general-education timetable preferences from the user's Korean or
English free text. Do not choose courses, do not build a timetable, and do not
change selected_preferences. Return only fields that fit PreferenceRules.

Rules:
- Use MON, TUE, WED, THU, FRI for weekdays.
- Use HH:MM 24-hour time.
- Hard conditions should use hard-filter fields such as required_free_days,
  excluded_days, earliest_start_time, latest_end_time, no_morning_classes, and
  excluded_time_ranges.
- Soft wishes should use ranking fields such as preferred_free_days,
  avoid_morning_classes, prefer_late_start, minimize_attendance_days,
  minimize_consecutive_classes, and compact_schedule.
- If the text is ambiguous, prefer soft ranking fields over hard filters.
"""


AGENT_SYSTEM_PROMPT = SYSTEM_PROMPT + """

Return the final parser result through the structured-response tool. Do not add
free-form text before or after the structured preference rules.
"""


LLMProvider = Callable[[dict[str, Any]], Any]


def load_proxy_env() -> None:
    """Load proxy settings from .env files without requiring python-dotenv.

    PlaNU keeps secrets in ``backend/.env``. Values already exported in the
    shell still win, but root ``.env`` no longer masks backend-specific values.
    """

    for path in _candidate_env_paths():
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)


def _candidate_env_paths() -> list[Path]:
    cwd = Path.cwd()
    module_root = Path(__file__).resolve().parents[3]
    backend_env = module_root / "backend" / ".env"
    candidates = [
        backend_env,
        cwd / ".env",
        module_root / ".env",
    ]
    unique: list[Path] = []
    for path in candidates:
        if path not in unique:
            unique.append(path)
    return unique


def extract_agent_events(result: Any) -> list[dict[str, Any]]:
    """Extract tool call/result events from LangChain agent messages."""

    events: list[dict[str, Any]] = []
    messages = result.get("messages", []) if isinstance(result, dict) else []
    for message in messages:
        tool_calls = getattr(message, "tool_calls", None) or []
        for call in tool_calls:
            if not isinstance(call, dict):
                continue
            events.append(
                {
                    "event": "tool_call",
                    "tool_name": call.get("name"),
                    "arguments": call.get("args"),
                    "id": call.get("id"),
                }
            )
        if getattr(message, "type", "") == "tool":
            content = getattr(message, "content", "")
            parsed_content: Any = content
            try:
                parsed_content = json.loads(content)
            except Exception:
                pass
            events.append(
                {
                    "event": "tool_result",
                    "tool_name": getattr(message, "name", None),
                    "content": parsed_content,
                    "id": getattr(message, "tool_call_id", None),
                }
            )
    return events


def message_content_to_text(message: Any) -> str:
    """Extract display text from a LangChain message or dict."""

    content = message.get("content", "") if isinstance(message, dict) else getattr(message, "content", message)
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                parts.append(str(item.get("text") or item.get("content") or ""))
            else:
                parts.append(str(item))
        return "\n".join(part for part in parts if part).strip()
    return str(content).strip()


def extract_final_text(result: Any) -> str:
    """Return the final non-empty LangChain response text."""

    messages = result.get("messages", []) if isinstance(result, dict) else []
    for message in reversed(messages):
        text = message_content_to_text(message)
        if text:
            return text
    return ""


def has_proxy_token(value: str | None) -> bool:
    """Return whether a PROXY_TOKEN value looks usable."""

    if not value:
        return False
    return value.strip() not in PROXY_TOKEN_PLACEHOLDERS


def trace_dict_or_none(value: Any) -> dict[str, Any] | None:
    """Normalize arbitrary LangChain event payloads for PreferenceTraceEvent."""

    if value is None:
        return None
    if isinstance(value, dict):
        return value
    return {"value": value}


class LLMPreferenceParser:
    """Convert free text into validated ``PreferenceRules`` with trace details."""

    def __init__(
        self,
        *,
        llm: Any | None = None,
        model_name: str | None = None,
        base_url: str | None = None,
    ) -> None:
        load_proxy_env()
        self.llm = llm
        self.model_name = model_name or os.getenv("OPENAI_MODEL", DEFAULT_OPENAI_MODEL)
        self.proxy_token = os.getenv("PROXY_TOKEN")
        self.base_url = base_url or os.getenv("CHAT_PROXY_URL", DEFAULT_CHAT_PROXY_URL)

    def parse(
        self,
        *,
        free_text: str,
        selected_preferences: PreferenceRules | None = None,
    ) -> PreferenceParseResult:
        """Parse user text and return merged rules plus observable tool trace."""

        selected = selected_preferences or PreferenceRules()
        text = free_text.strip()
        payload = build_preference_parse_payload(
            free_text=text,
            selected_preferences=selected,
        )
        used_tools: list[PreferenceToolUsage] = []
        trace: list[PreferenceTraceEvent] = []

        self._record(
            used_tools,
            trace,
            name="preference_payload_builder",
            purpose="Build LLM input while preserving UI-selected preferences",
            status=PreferenceToolStatus.SUCCESS,
            message="Prepared preference parsing payload.",
            input={"free_text_length": len(text)},
            output={
                "selected_fields": sorted(selected.model_fields_set),
                "has_free_text": bool(text),
            },
        )

        if not text:
            merged = merge_preference_rules(selected_preferences=selected)
            self._record(
                used_tools,
                trace,
                name="input_guard",
                purpose="Skip LLM parsing when no free text was provided",
                status=PreferenceToolStatus.SKIPPED,
                message="No free text provided; using selected preferences only.",
            )
            return PreferenceParseResult(
                status=PreferenceParseStatus.SKIPPED,
                merged_preferences=merged,
                used_tools=used_tools,
                trace=trace,
            )

        try:
            raw_output = self._invoke_llm(payload, used_tools, trace)
            llm_preferences = self._validate_llm_output(raw_output, used_tools, trace)
            self._validate_domain_rules(llm_preferences, used_tools, trace)
            merged = merge_preference_rules(
                selected_preferences=selected,
                llm_preferences=llm_preferences,
            )
            self._record(
                used_tools,
                trace,
                name="preference_rule_merger",
                purpose="Merge UI selections with LLM additions",
                status=PreferenceToolStatus.SUCCESS,
                message="Merged selected preferences and LLM preferences.",
                output={
                    "llm_fields": sorted(llm_preferences.model_fields_set),
                    "merged_fields": sorted(merged.model_fields_set),
                },
            )
            return PreferenceParseResult(
                status=PreferenceParseStatus.SUCCESS,
                llm_preferences=llm_preferences,
                merged_preferences=merged,
                used_tools=used_tools,
                trace=trace,
                raw_output=self._safe_raw_output(raw_output),
            )
        except Exception as exc:
            fallback = PreferenceRules()
            merged = merge_preference_rules(
                selected_preferences=selected,
                llm_preferences=fallback,
            )
            self._record(
                used_tools,
                trace,
                name="llm_parse_fallback",
                purpose="Continue recommendation with safe empty LLM rules",
                status=PreferenceToolStatus.SUCCESS,
                message="LLM parsing failed; using empty PreferenceRules fallback.",
                error=str(exc),
            )
            return PreferenceParseResult(
                status=PreferenceParseStatus.FALLBACK,
                llm_preferences=fallback,
                merged_preferences=merged,
                used_tools=used_tools,
                trace=trace,
                fallback_used=True,
                warnings=["LLM_PARSE_FALLBACK"],
            )

    def _invoke_llm(
        self,
        payload: dict[str, Any],
        used_tools: list[PreferenceToolUsage],
        trace: list[PreferenceTraceEvent],
    ) -> Any:
        if self.llm is None:
            return self._invoke_agent_tool_call(payload, used_tools, trace)
        return self._invoke_structured_output(payload, used_tools, trace)

    def _invoke_structured_output(
        self,
        payload: dict[str, Any],
        used_tools: list[PreferenceToolUsage],
        trace: list[PreferenceTraceEvent],
    ) -> Any:
        self._record(
            used_tools,
            trace,
            name="langchain_structured_output",
            purpose="Ask the LLM for PreferenceRules-shaped structured output",
            status=PreferenceToolStatus.STARTED,
            message="Starting structured preference parse.",
            input={
                "model": self.model_name,
                "schema": "PreferenceRules",
                "free_text_length": len(payload["free_text"]),
            },
        )

        llm = self.llm or self._build_default_llm()
        if hasattr(llm, "with_structured_output"):
            structured_llm = llm.with_structured_output(PreferenceRules)
            output = structured_llm.invoke(self._messages(payload))
        elif callable(llm):
            output = llm(payload)
        else:
            raise RuntimeError("configured LLM is not invokable")

        self._record(
            used_tools,
            trace,
            name="langchain_structured_output",
            purpose="Ask the LLM for PreferenceRules-shaped structured output",
            status=PreferenceToolStatus.SUCCESS,
            message="Structured preference parse completed.",
            output={"output_type": type(output).__name__},
        )
        return output

    def _build_default_llm(self) -> Any:
        if not has_proxy_token(self.proxy_token):
            raise RuntimeError("PROXY_TOKEN is not configured")
        try:
            from langchain_openai import ChatOpenAI
        except ImportError as exc:
            raise RuntimeError("langchain_openai is not installed") from exc
        return ChatOpenAI(
            model=self.model_name,
            api_key=self.proxy_token,
            base_url=self.base_url,
            temperature=0,
        )

    def _invoke_agent_tool_call(
        self,
        payload: dict[str, Any],
        used_tools: list[PreferenceToolUsage],
        trace: list[PreferenceTraceEvent],
    ) -> Any:
        self._record(
            used_tools,
            trace,
            name="langchain_agent",
            purpose="Run a LangChain agent that must call the preference parser tool",
            status=PreferenceToolStatus.STARTED,
            message="Starting proxy-backed LangChain agent.",
            input={
                "model": self.model_name,
                "base_url": self.base_url,
                "free_text_length": len(payload["free_text"]),
            },
        )
        if not has_proxy_token(self.proxy_token):
            raise RuntimeError("PROXY_TOKEN is not configured")
        try:
            from langchain.agents import create_agent
            from langchain.agents.structured_output import ToolStrategy
        except ImportError as exc:
            raise RuntimeError("langchain is not installed") from exc

        agent = create_agent(
            model=self._build_default_llm(),
            tools=[],
            response_format=ToolStrategy(PreferenceRules),
            system_prompt=AGENT_SYSTEM_PROMPT,
        )
        result = agent.invoke({"messages": self._agent_messages(payload)})
        agent_events = extract_agent_events(result)
        for event in agent_events:
            self._record_agent_event(used_tools, trace, event)
        raw_output = self._rules_from_agent_result(result)
        self._record(
            used_tools,
            trace,
            name="langchain_agent",
            purpose="Run a LangChain agent that must call the preference parser tool",
            status=PreferenceToolStatus.SUCCESS,
            message="Proxy-backed LangChain agent completed.",
            output={
                "event_count": len(agent_events),
                "output_type": type(raw_output).__name__,
            },
        )
        return raw_output

    def _validate_llm_output(
        self,
        raw_output: Any,
        used_tools: list[PreferenceToolUsage],
        trace: list[PreferenceTraceEvent],
    ) -> PreferenceRules:
        self._record(
            used_tools,
            trace,
            name="pydantic_preference_validator",
            purpose="Validate the LLM output against PreferenceRules",
            status=PreferenceToolStatus.STARTED,
            message="Validating LLM output.",
            input={"output_type": type(raw_output).__name__},
        )
        try:
            rules = self._coerce_to_rules(raw_output)
        except (TypeError, ValueError, ValidationError, json.JSONDecodeError) as exc:
            self._record(
                used_tools,
                trace,
                name="pydantic_preference_validator",
                purpose="Validate the LLM output against PreferenceRules",
                status=PreferenceToolStatus.ERROR,
                message="LLM output failed PreferenceRules validation.",
                error=str(exc),
            )
            raise

        self._record(
            used_tools,
            trace,
            name="pydantic_preference_validator",
            purpose="Validate the LLM output against PreferenceRules",
            status=PreferenceToolStatus.SUCCESS,
            message="LLM output passed PreferenceRules validation.",
            output={"validated_fields": sorted(rules.model_fields_set)},
        )
        return rules

    def _validate_domain_rules(
        self,
        rules: PreferenceRules,
        used_tools: list[PreferenceToolUsage],
        trace: list[PreferenceTraceEvent],
    ) -> None:
        """Record explicit PlaNU-domain validation after Pydantic validation."""

        self._record(
            used_tools,
            trace,
            name="domain_preference_validator",
            purpose="Check PlaNU-specific preference rule semantics",
            status=PreferenceToolStatus.STARTED,
            message="Validating PlaNU preference semantics.",
            input={"validated_fields": sorted(rules.model_fields_set)},
        )
        self._record(
            used_tools,
            trace,
            name="domain_preference_validator",
            purpose="Check PlaNU-specific preference rule semantics",
            status=PreferenceToolStatus.SUCCESS,
            message="PlaNU preference semantics are valid.",
            output={
                "hard_filter_count": self._hard_filter_count(rules),
                "soft_preference_count": self._soft_preference_count(rules),
            },
        )

    @staticmethod
    def _coerce_to_rules(raw_output: Any) -> PreferenceRules:
        if isinstance(raw_output, PreferenceRules):
            return raw_output
        if isinstance(raw_output, str):
            return PreferenceRules.model_validate_json(raw_output)
        if isinstance(raw_output, dict):
            return PreferenceRules.model_validate(raw_output)
        if hasattr(raw_output, "model_dump"):
            return PreferenceRules.model_validate(raw_output.model_dump())
        raise TypeError(f"unsupported LLM output type: {type(raw_output).__name__}")

    @staticmethod
    def _hard_filter_count(rules: PreferenceRules) -> int:
        hard_fields = (
            "excluded_days",
            "required_free_days",
            "earliest_start_time",
            "latest_end_time",
            "no_morning_classes",
            "excluded_time_ranges",
            "excluded_professors",
            "preferred_elective_areas",
            "required_keywords",
            "excluded_keywords",
            "max_consecutive_classes",
        )
        return sum(1 for field_name in hard_fields if getattr(rules, field_name))

    @staticmethod
    def _soft_preference_count(rules: PreferenceRules) -> int:
        soft_fields = (
            "preferred_free_days",
            "avoid_morning_classes",
            "prefer_late_start",
            "minimize_attendance_days",
            "minimize_consecutive_classes",
            "compact_schedule",
        )
        return sum(1 for field_name in soft_fields if getattr(rules, field_name))

    @staticmethod
    def _messages(payload: dict[str, Any]) -> list[tuple[str, str]]:
        return [
            ("system", SYSTEM_PROMPT),
            ("human", json.dumps(payload, ensure_ascii=False)),
        ]

    @staticmethod
    def _agent_messages(payload: dict[str, Any]) -> list[dict[str, str]]:
        return [
            {
                "role": "user",
                "content": json.dumps(payload, ensure_ascii=False),
            }
        ]

    @staticmethod
    def _rules_from_agent_result(result: Any) -> dict[str, Any]:
        if isinstance(result, dict) and "structured_response" in result:
            structured = result["structured_response"]
            if isinstance(structured, PreferenceRules):
                return structured.model_dump(mode="json", exclude_unset=True)
            if isinstance(structured, dict):
                return structured
            if hasattr(structured, "model_dump"):
                return structured.model_dump(mode="json", exclude_unset=True)

        events = extract_agent_events(result)
        for event in reversed(events):
            if event.get("event") != "tool_result":
                continue
            content = event.get("content")
            if isinstance(content, dict) and "preference_rules" in content:
                return content["preference_rules"]
        final_text = extract_final_text(result)
        try:
            parsed = json.loads(final_text)
        except json.JSONDecodeError:
            raise ValueError("agent did not return PreferenceRules JSON")
        if isinstance(parsed, dict) and "preference_rules" in parsed:
            return parsed["preference_rules"]
        if isinstance(parsed, dict):
            return parsed
        raise ValueError("agent returned unsupported PreferenceRules payload")

    @staticmethod
    def _safe_raw_output(raw_output: Any) -> dict[str, Any] | str | None:
        if raw_output is None or isinstance(raw_output, str):
            return raw_output
        if isinstance(raw_output, PreferenceRules):
            return raw_output.model_dump(mode="json", exclude_unset=True)
        if isinstance(raw_output, dict):
            return raw_output
        if hasattr(raw_output, "model_dump"):
            return raw_output.model_dump(mode="json")
        return repr(raw_output)

    @staticmethod
    def _record(
        used_tools: list[PreferenceToolUsage],
        trace: list[PreferenceTraceEvent],
        *,
        name: str,
        purpose: str,
        status: PreferenceToolStatus,
        message: str,
        input: dict[str, Any] | None = None,
        output: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        used_tools.append(
            PreferenceToolUsage(
                name=name,
                purpose=purpose,
                status=status,
                metadata={
                    "step_index": len(trace) + 1,
                    "has_error": error is not None,
                },
            )
        )
        trace.append(
            PreferenceTraceEvent(
                step=str(len(trace) + 1),
                tool=name,
                status=status,
                message=message,
                input=input,
                output=output,
                error=error,
            )
        )

    @staticmethod
    def _record_agent_event(
        used_tools: list[PreferenceToolUsage],
        trace: list[PreferenceTraceEvent],
        event: dict[str, Any],
    ) -> None:
        event_name = str(event.get("event") or "langchain_event")
        tool_name = str(event.get("tool_name") or "unknown_tool")
        status = (
            PreferenceToolStatus.STARTED
            if event_name == "tool_call"
            else PreferenceToolStatus.SUCCESS
        )
        used_tools.append(
            PreferenceToolUsage(
                name=tool_name,
                purpose=f"LangChain {event_name}",
                status=status,
                metadata={
                    "step_index": len(trace) + 1,
                    "event": event_name,
                    "id": event.get("id"),
                },
            )
        )
        trace.append(
            PreferenceTraceEvent(
                step=str(len(trace) + 1),
                tool=tool_name,
                status=status,
                message=f"LangChain {event_name}: {tool_name}",
                input=trace_dict_or_none(
                    event.get("arguments") if event_name == "tool_call" else None
                ),
                output=trace_dict_or_none(
                    event.get("content") if event_name == "tool_result" else None
                ),
            )
        )


def build_preference_parse_payload(
    *,
    free_text: str,
    selected_preferences: PreferenceRules | None = None,
) -> dict[str, Any]:
    """Build the LLM input while keeping UI-selected rules authoritative.

    The LLM should use ``selected_preferences`` as context and return only
    additional rules found in ``free_text``. Callers must merge its validated
    output with ``merge_preference_rules`` so duplicate fields are not scored or
    filtered twice.
    """

    selected = selected_preferences or PreferenceRules()
    return {
        "selected_preferences": selected.model_dump(mode="json", exclude_unset=True),
        "free_text": free_text.strip(),
        "instruction": (
            "Extract only additional timetable preferences that are not already "
            "represented in selected_preferences. Return PreferenceRules JSON."
        ),
    }


def parse_preferences_with_trace(
    *,
    free_text: str,
    selected_preferences: PreferenceRules | None = None,
    llm: Any | None = None,
    model_name: str | None = None,
    base_url: str | None = None,
) -> PreferenceParseResult:
    """Functional API for route handlers that need rules plus trace output."""

    return LLMPreferenceParser(
        llm=llm,
        model_name=model_name,
        base_url=base_url,
    ).parse(
        free_text=free_text,
        selected_preferences=selected_preferences,
    )


def parse_llm_preferences(
    *,
    free_text: str,
    selected_preferences: PreferenceRules | None = None,
    llm: Any | None = None,
    model_name: str | None = None,
    base_url: str | None = None,
) -> PreferenceRules:
    """Return only merged rules for callers that do not need trace details."""

    return parse_preferences_with_trace(
        free_text=free_text,
        selected_preferences=selected_preferences,
        llm=llm,
        model_name=model_name,
        base_url=base_url,
    ).merged_preferences


def merge_selected_and_llm_preferences(
    *,
    selected_preferences: PreferenceRules | None = None,
    llm_preferences: PreferenceRules | None = None,
) -> PreferenceRules:
    """Apply the documented precedence: UI selection, then LLM, then defaults."""

    return merge_preference_rules(selected_preferences, llm_preferences)


def _result_to_pretty_json(result: PreferenceParseResult) -> str:
    return json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2)


def run_interactive_cli() -> int:
    """Prompt loop for manually inspecting tool calls and trace output."""

    load_proxy_env()
    model = os.getenv("OPENAI_MODEL", DEFAULT_OPENAI_MODEL)
    base_url = os.getenv("CHAT_PROXY_URL", DEFAULT_CHAT_PROXY_URL)
    has_token = has_proxy_token(os.getenv("PROXY_TOKEN"))
    print("PlaNU LLM preference parser")
    print(f"- model: {model}")
    print(f"- chat_proxy_url: {base_url}")
    print(f"- proxy_token_configured: {has_token}")
    print("프롬프트를 입력하세요. 종료하려면 빈 줄 또는 Ctrl+C를 입력하세요.")
    while True:
        try:
            prompt = input("\npreference> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not prompt:
            return 0
        result = parse_preferences_with_trace(free_text=prompt)
        print(_result_to_pretty_json(result))


def main(argv: list[str] | None = None) -> int:
    """Run one prompt or start the interactive prompt loop."""

    import argparse

    parser = argparse.ArgumentParser(
        description="Parse PlaNU preference prompts and print tool/trace JSON.",
    )
    parser.add_argument("prompt", nargs="*", help="Prompt text to parse once.")
    parser.add_argument(
        "--selected-json",
        default=None,
        help="Optional selected PreferenceRules JSON to merge before parsing.",
    )
    args = parser.parse_args(argv)

    if not args.prompt:
        return run_interactive_cli()

    selected = (
        PreferenceRules.model_validate_json(args.selected_json)
        if args.selected_json
        else None
    )
    result = parse_preferences_with_trace(
        free_text=" ".join(args.prompt),
        selected_preferences=selected,
    )
    print(_result_to_pretty_json(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
