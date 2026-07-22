"""Parse natural-language general-education preferences with trace output."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
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
- In PlaNU, morning classes are classes that start before 10:00.
- If the user strongly forbids morning classes, use earliest_start_time: "10:00".
- If the user softly prefers avoiding morning classes, use
  preferred_first_class_time: "10:00".
- If the user gives a concrete time, prefer the user's time over PlaNU defaults.
- earliest_start_time is a hard filter. preferred_first_class_time is a soft
  ranking preference.
- Do not return both earliest_start_time and preferred_first_class_time for the
  same morning preference unless the user separately states a hard condition and
  a soft preference.
- PlaNU's default lunch time is MON-FRI 12:00-13:00.
- Strong lunch requests go to excluded_time_ranges. Soft lunch requests go to
  preferred_free_time_ranges. Do not ask the user what lunch time means.
- Course-name fields must contain only concrete course names explicitly written
  by the user.
- Do not turn requests about presentations, team projects, difficulty,
  workload, fun, grades, or professor kindness into course names.
- Do not turn broad subjects, academic areas, categories, or phrases ending in
  "과목" into course names. For example, if the user says they like a broad
  category but excludes one concrete course, return only the concrete course
  exclusion and do not add the category to course-name fields.
- Do not invent or guess course names.
- Use required_course_names, preferred_course_names, excluded_course_names, and
  avoided_course_names for explicit course-name requests.
- Course-name preference rules:
  - Extract only concrete course names explicitly stated by the user.
  - Treat a clearly stated course nickname or abbreviation as an explicit
    course-name mention when the user uses it as a course request. Return the
    nickname or abbreviation as written; downstream catalog matching may resolve
    it to the official course name. For example, "컴프입 듣고 싶어" is a
    preferred course-name request for "컴프입".
  - Preserve a contiguous course-name phrase before Korean particles such as
    은, 는, 을, 를, 만은, and 만. Do not split a course name merely because it
    contains connectors such as 와, 과, and, or &, when they are written without
    spaces inside the course-name phrase.
  - Use required_course_names when a concrete course is expressed as a hard
    requirement.
  - Use preferred_course_names when a concrete course is expressed as a positive
    soft preference.
  - Use excluded_course_names when a concrete course is expressed as a hard
    negative constraint. Expressions such as "절대", "무조건 제외",
    "포함하지 마", "넣지 마", "듣고 싶지 않다", and "있으면 안 된다"
    indicate excluded_course_names when they apply to a concrete course.
  - Use avoided_course_names when a concrete course is expressed as a negative
    soft preference. Expressions such as "가능하면 피하고 싶다",
    "다른 선택지가 있으면 피해줘", "별로다", "우선순위를 낮춰줘", and
    "절대 제외할 정도는 아니다" indicate avoided_course_names unless a later
    phrase turns the same course into a hard exclusion.
  - Soft course-name preferences are valid parser results and must not be ignored.
  - Expressions such as "가능하면", "되도록", "듣고 싶다", "선호한다",
    "우선적으로 고려해줘", "있으면 좋겠다", and
    "꼭 들어야 하는 것은 아니지만 듣고 싶다" indicate
    preferred_course_names unless an explicit hard expression is also present.
  - Do not convert soft course-name preferences into required_course_names.
  - Do not leave preferred_course_names empty when the user explicitly names a
    concrete course and expresses a positive soft preference for it.
  - Do not convert negative soft preferences into preferred_course_names.
  - Do not invent, normalize, or infer course names that the user did not state.
  - If the same course is mentioned with an earlier hard requirement and a later
    correction such as "아니", "필수까지는 아니고", "꼭은 아니고", or
    "반드시까지는 아니고", the later softened preference overrides the earlier
    hard requirement. Return the course only in preferred_course_names.
  - "대학영어는 반드시 넣어줘." -> required_course_names: ["대학영어"]
  - "가능하면 대학영어를 듣고 싶어." -> preferred_course_names: ["대학영어"]
  - "대학영어를 선호해." -> preferred_course_names: ["대학영어"]
  - "대학영어가 시간표에 있으면 좋겠어." -> preferred_course_names: ["대학영어"]
  - "꼭 들어야 하는 건 아니지만 대학영어를 듣고 싶어." -> preferred_course_names: ["대학영어"]
- For concrete first-class or start-time constraints, use earliest_start_time
  when the user says classes or the first class should start at or after that
  time. Phrases such as "첫 수업은 10시부터", "첫 수업은 10시 이후",
  "10시보다 이른 수업은 싫다", and "10시 이후 수업" should produce
  earliest_start_time: "10:00". Use preferred_first_class_time only for a
  purely soft ranking preference that does not constrain allowed schedules.
- For elective-area preferences, extract only the explicit numeric areas stated
  by the user. "4영역" means [4], not [1, 2, 3, 4]. Do not expand a single
  area number into a range or infer unstated areas.
- Do not duplicate the same meaning across multiple fields.
- Do not return conditions already represented in selected_preferences.
- Never delete or change existing UI-selected conditions.
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


def should_use_direct_proxy_client() -> bool:
    """Avoid LangChain's Pydantic v1 compatibility path on Python 3.14+."""

    return sys.version_info >= (3, 14)


def chat_completions_url(base_url: str) -> str:
    """Return the OpenAI-compatible chat completions endpoint URL."""

    stripped = base_url.rstrip("/")
    if stripped.endswith("/chat/completions"):
        return stripped
    return f"{stripped}/chat/completions"


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
            llm_preferences = self._drop_selected_preferences(
                llm_preferences,
                selected,
                used_tools,
                trace,
            )
            llm_preferences = self._drop_broad_course_categories(
                llm_preferences,
                used_tools,
                trace,
            )
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
            if should_use_direct_proxy_client():
                return self._invoke_openai_compatible_tool_call(
                    payload,
                    used_tools,
                    trace,
                )
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

    def _invoke_openai_compatible_tool_call(
        self,
        payload: dict[str, Any],
        used_tools: list[PreferenceToolUsage],
        trace: list[PreferenceTraceEvent],
    ) -> Any:
        self._record(
            used_tools,
            trace,
            name="openai_compatible_tool_call",
            purpose=(
                "Call the proxy chat-completions API directly with function tools "
                "on Python 3.14+"
            ),
            status=PreferenceToolStatus.STARTED,
            message="Starting direct OpenAI-compatible tool call.",
            input={
                "model": self.model_name,
                "base_url": self.base_url,
                "free_text_length": len(payload["free_text"]),
            },
        )
        if not has_proxy_token(self.proxy_token):
            raise RuntimeError("PROXY_TOKEN is not configured")

        request_payload = self._tool_call_request_payload(payload)
        request = urllib.request.Request(
            chat_completions_url(self.base_url),
            data=json.dumps(request_payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.proxy_token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                response_payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"proxy returned HTTP {exc.code}: {body}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"proxy request failed: {exc.reason}") from exc

        raw_output = self._rules_from_chat_completions_response(
            response_payload,
            used_tools,
            trace,
        )
        self._record(
            used_tools,
            trace,
            name="openai_compatible_tool_call",
            purpose=(
                "Call the proxy chat-completions API directly with function tools "
                "on Python 3.14+"
            ),
            status=PreferenceToolStatus.SUCCESS,
            message="Direct OpenAI-compatible tool call completed.",
            output={"output_type": type(raw_output).__name__},
        )
        return raw_output

    def _tool_call_request_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "model": self.model_name,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": AGENT_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(payload, ensure_ascii=False),
                },
            ],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "preference_rules_from_prompt",
                        "description": (
                            "Return PlaNU PreferenceRules parsed from the user's "
                            "explicit natural-language preferences."
                        ),
                        "parameters": PreferenceRules.model_json_schema(),
                    },
                }
            ],
            "tool_choice": {
                "type": "function",
                "function": {"name": "preference_rules_from_prompt"},
            },
        }

    def _rules_from_chat_completions_response(
        self,
        response_payload: dict[str, Any],
        used_tools: list[PreferenceToolUsage],
        trace: list[PreferenceTraceEvent],
    ) -> dict[str, Any]:
        choices = response_payload.get("choices") or []
        if not choices:
            raise ValueError("proxy response did not include choices")
        message = choices[0].get("message") or {}
        tool_calls = message.get("tool_calls") or []
        if not tool_calls:
            raise ValueError("proxy response did not include a tool call")

        tool_call = tool_calls[0]
        function = tool_call.get("function") or {}
        arguments_text = function.get("arguments") or "{}"
        try:
            arguments = json.loads(arguments_text)
        except json.JSONDecodeError as exc:
            raise ValueError("tool call arguments were not valid JSON") from exc

        self._record_agent_event(
            used_tools,
            trace,
            {
                "event": "tool_call",
                "tool_name": function.get("name") or "preference_rules_from_prompt",
                "arguments": arguments,
                "id": tool_call.get("id"),
            },
        )
        rules = PreferenceRules.model_validate(arguments)
        result = {
            "ok": True,
            "tool_name": function.get("name") or "preference_rules_from_prompt",
            "preference_rules": rules.model_dump(mode="json", exclude_unset=True),
        }
        self._record_agent_event(
            used_tools,
            trace,
            {
                "event": "tool_result",
                "tool_name": result["tool_name"],
                "content": result,
                "id": tool_call.get("id"),
            },
        )
        return result["preference_rules"]

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

    def _drop_selected_preferences(
        self,
        llm_preferences: PreferenceRules,
        selected_preferences: PreferenceRules,
        used_tools: list[PreferenceToolUsage],
        trace: list[PreferenceTraceEvent],
    ) -> PreferenceRules:
        selected_dump = selected_preferences.model_dump(mode="json")
        llm_dump = llm_preferences.model_dump(mode="json")
        changed: list[str] = []

        for field_name, value in selected_dump.items():
            if not value or field_name not in llm_dump:
                continue
            llm_value = llm_dump[field_name]
            if isinstance(value, list) and isinstance(llm_value, list):
                selected_values = {json.dumps(item, ensure_ascii=False, sort_keys=True) for item in value}
                filtered = [
                    item
                    for item in llm_value
                    if json.dumps(item, ensure_ascii=False, sort_keys=True) not in selected_values
                ]
                if len(filtered) != len(llm_value):
                    llm_dump[field_name] = filtered
                    changed.append(field_name)
            elif llm_value == value and field_name in llm_preferences.model_fields_set:
                llm_dump[field_name] = PreferenceRules.model_fields[field_name].default
                changed.append(field_name)

        if changed:
            self._record(
                used_tools,
                trace,
                name="selected_preference_deduplicator",
                purpose="Remove LLM rules already represented by UI selections",
                status=PreferenceToolStatus.SUCCESS,
                message="Removed duplicate LLM preferences already selected in the UI.",
                output={"fields": sorted(set(changed))},
            )
        return PreferenceRules.model_validate(llm_dump)

    def _drop_broad_course_categories(
        self,
        llm_preferences: PreferenceRules,
        used_tools: list[PreferenceToolUsage],
        trace: list[PreferenceTraceEvent],
    ) -> PreferenceRules:
        """Remove broad subject/category phrases from concrete course fields."""

        course_fields = (
            "required_course_names",
            "preferred_course_names",
            "excluded_course_names",
            "avoided_course_names",
        )
        llm_dump = llm_preferences.model_dump(mode="json")
        changed: dict[str, list[str]] = {}
        for field_name in course_fields:
            values = llm_dump.get(field_name) or []
            filtered = [
                value
                for value in values
                if not self._looks_like_broad_course_category(value)
            ]
            if filtered != values:
                llm_dump[field_name] = filtered
                changed[field_name] = [
                    value for value in values if value not in filtered
                ]

        if changed:
            self._record(
                used_tools,
                trace,
                name="course_category_filter",
                purpose="Remove broad categories from concrete course-name fields",
                status=PreferenceToolStatus.SUCCESS,
                message="Removed broad course categories from LLM course-name output.",
                output={"removed": changed},
            )
        return PreferenceRules.model_validate(llm_dump)

    @staticmethod
    def _looks_like_broad_course_category(value: Any) -> bool:
        if not isinstance(value, str):
            return False
        normalized = value.strip()
        if not normalized:
            return False
        broad_terms = {
            "경제",
            "경제학",
            "공학",
            "과학",
            "사회",
            "사회과학",
            "예술",
            "인문",
            "인문학",
            "자연",
            "자연과학",
            "철학",
        }
        if normalized in broad_terms:
            return True
        broad_suffixes = (
            "과목",
            "수업",
            "강의",
            "분야",
            "계열",
            "영역",
        )
        return any(normalized.endswith(suffix) for suffix in broad_suffixes)

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
            "excluded_time_ranges",
            "excluded_professors",
            "preferred_elective_areas",
            "required_course_names",
            "excluded_course_names",
            "max_consecutive_classes",
        )
        return sum(1 for field_name in hard_fields if getattr(rules, field_name))

    @staticmethod
    def _soft_preference_count(rules: PreferenceRules) -> int:
        soft_fields = (
            "preferred_first_class_time",
            "preferred_free_time_ranges",
            "preferred_free_days",
            "preferred_course_names",
            "avoided_course_names",
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
            "Extract all additional supported PreferenceRules that are explicitly "
            "stated in free_text and are not already represented in "
            "selected_preferences. Supported rules include timetable constraints, "
            "free-day preferences, time-range preferences, concrete course-name "
            "preferences, including clear course nicknames or abbreviations, "
            "professor exclusions, and elective-area preferences. "
            "A positive soft preference for a concrete course name must be "
            "returned in preferred_course_names. Do not omit it merely because it "
            "is optional. Keep required_course_names for hard requirements only. "
            "Return PreferenceRules JSON."
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
