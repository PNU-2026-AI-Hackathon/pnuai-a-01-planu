"""Parse general-education preference prompts into supported rule groups."""

from __future__ import annotations

import json
import os
import re
from typing import Any

from pydantic import BaseModel, ValidationError

from ..core.errors import AppError
from ..models.course import Day, time_to_minutes
from ..models.preference import (
    GeneralPreferenceLLMOutput,
    GeneralPreferenceParseResult,
    HardPreferenceConditions,
    PreferenceWarning,
    SoftPreferenceConditions,
    UnsupportedCondition,
)
from .llm_preference_parser import (
    DEFAULT_CHAT_PROXY_URL,
    DEFAULT_OPENAI_MODEL,
    load_proxy_env,
)
from .preference_constants import MORNING_END_TIME
from .openai_client import (
    DEFAULT_OPENAI_BASE_URL,
    has_openai_api_key,
    normalize_openai_model_name,
    request_chat_completions,
)


MAX_PROMPT_LENGTH = 2000

GENERAL_PREFERENCE_SYSTEM_PROMPT = f"""당신은 PlaNU의 교양 시간표 선호 파서입니다.

사용자의 자연어 입력을 hard_conditions, soft_conditions,
unsupported_conditions, warnings로만 구조화하세요.

규칙:
- 시간표를 직접 추천하거나 생성하지 마세요.
- 점수나 랭킹 가중치, 템플릿을 결정하지 마세요.
- 사용자가 말하지 않은 조건을 추가하지 마세요.
- 명확한 금지/필수 표현은 hard_conditions로 분류하세요.
- 가능하면, 되도록, 선호, 피하고 싶어 같은 표현은 soft_conditions로 분류하세요.
- 강도가 불명확하면 hard로 강화하지 말고 soft_conditions와 warning을 사용하세요.
- 현재 지원하지 않는 조건은 unsupported_conditions로 분리하세요.
- unsupported_conditions의 각 항목은 반드시 객체여야 하며 source_text, reason_code, reason을 모두 포함해야 합니다.
- 수강편람에 존재하는 과목인지 추측하지 마세요.
- 과목명 필드에는 사용자가 쓴 구체적인 과목명만 넣으세요.
- 구체적인 과목명에 대해 "듣고 싶어", "우선하고 싶어", "선호해", "가능하면 듣고 싶어"라고 하면 soft_conditions.preferred_course_names에 넣으세요.
- 구체적인 과목명에 대해 "별로 듣고 싶지 않아", "가능하면 피하고 싶어"라고 하면 soft_conditions.avoided_course_names에 넣으세요.
- 구체적인 과목명에 대해 "꼭", "반드시", "무조건"이라고 하면 hard_conditions.required_course_names에 넣으세요.
- 구체적인 과목명에 대해 "절대 넣지 마", "듣지 않을래", "제외해"라고 하면 hard_conditions.excluded_course_names에 넣으세요.
- 과제량, 시험 난이도, 발표/팀플 여부, 학점, 교수 평점/친절함은 지원하지 않습니다.
- 지원하지 않는 조건은 조용히 무시하지 말고 원문 일부와 이유를 unsupported_conditions에 남기세요.
- 지원하지 않는 조건을 hard_conditions나 soft_conditions로 바꾸거나 과목명/교수명으로 추측하지 마세요.
- 요일은 MON, TUE, WED, THU, FRI enum을 우선 사용하세요.
- 시간은 HH:MM 24시간 형식만 사용하세요.
- PlaNU의 오전 수업 기준은 {MORNING_END_TIME} 이전 시작입니다.
- 오전 수업 hard 금지는 earliest_start_time: "{MORNING_END_TIME}" 하나로 표현하세요.
- 오전 수업 soft 회피는 preferred_first_class_time: "{MORNING_END_TIME}"로 표현하세요.
- "오후 6시 이후 수업은 넣지 마"처럼 특정 시각 이후 수업을 금지하면 hard_conditions.latest_end_time에 해당 시각을 넣으세요.
- 같은 의미를 hard와 soft에 중복해서 넣지 마세요.
- soft 요일 공강 선호는 반드시 soft_conditions.preferred_free_days에 넣으세요. preferred_days 같은 다른 필드는 쓰지 마세요.
- tool call arguments에는 반드시 preference_result 하나만 넣고, 그 안에 hard_conditions, soft_conditions, unsupported_conditions, warnings를 넣으세요.
- 입력으로 받은 prompt, supported_hard_fields, supported_soft_fields는 tool call arguments에 절대 복사하지 마세요.
- 설명 문장을 따로 출력하지 말고 지정된 구조화 형식만 반환하세요.
"""


HARD_FIELDS = {
    "excluded_days",
    "required_free_days",
    "earliest_start_time",
    "latest_end_time",
    "excluded_time_ranges",
    "excluded_professors",
    "required_course_names",
    "excluded_course_names",
    "max_consecutive_classes",
}

SOFT_FIELDS = {
    "preferred_first_class_time",
    "preferred_free_time_ranges",
    "preferred_free_days",
    "preferred_course_names",
    "avoided_course_names",
    "preferred_elective_areas",
    "minimize_attendance_days",
    "minimize_consecutive_classes",
    "compact_schedule",
}


class GeneralPreferenceParser:
    """Convert optional general-education prompt text into validated rules."""

    def __init__(
        self,
        *,
        llm: Any | None = None,
        model_name: str | None = None,
        base_url: str | None = None,
        timeout_seconds: int = 60,
        ) -> None:
        load_proxy_env()
        self.llm = llm
        self.model_name = normalize_openai_model_name(
            model_name or os.getenv("OPENAI_MODEL", DEFAULT_OPENAI_MODEL)
        )
        self.base_url = base_url or os.getenv("OPENAI_BASE_URL", DEFAULT_CHAT_PROXY_URL)
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.timeout_seconds = timeout_seconds

    def parse(self, prompt: str) -> GeneralPreferenceParseResult:
        text = prompt.strip()
        if len(text) > MAX_PROMPT_LENGTH:
            raise AppError(
                "PREFERENCE_PROMPT_TOO_LONG",
                "교양 선호 입력이 너무 깁니다.",
                details={"max_length": MAX_PROMPT_LENGTH},
            )
        if not text:
            return GeneralPreferenceParseResult()

        raw_output = self._invoke_llm(text)
        try:
            parsed = self._coerce_output(raw_output)
        except ValidationError as exc:
            raise self._validation_error(exc) from exc
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise AppError(
                "INVALID_PREFERENCE_OUTPUT",
                "교양 선호 파서 출력 형식이 올바르지 않습니다.",
            ) from exc

        return self._validate_and_normalize(parsed, raw_output=raw_output, prompt=text)

    def _invoke_llm(self, prompt: str) -> Any:
        try:
            if self.llm is None:
                return self._invoke_openai_compatible_tool_call(prompt)
            llm = self.llm
            if hasattr(llm, "with_structured_output"):
                structured_llm = llm.with_structured_output(
                    GeneralPreferenceLLMOutput
                )
                return structured_llm.invoke(self._messages(prompt))
            if callable(llm):
                return llm(
                    {
                        "system": GENERAL_PREFERENCE_SYSTEM_PROMPT,
                        "prompt": prompt,
                        "schema": "GeneralPreferenceLLMOutput",
                    }
                )
        except TimeoutError as exc:
            raise AppError(
                "PREFERENCE_PARSE_TIMEOUT",
                "교양 선호 파서 LLM 호출 시간이 초과되었습니다.",
            ) from exc
        except AppError:
            raise
        except Exception as exc:
            raise AppError(
                "PREFERENCE_PARSE_FAILED",
                "교양 선호 파서 LLM 호출에 실패했습니다.",
            ) from exc
        raise AppError(
            "PREFERENCE_PARSE_FAILED",
            "교양 선호 파서 LLM을 호출할 수 없습니다.",
        )

    def _invoke_openai_compatible_tool_call(self, prompt: str) -> dict[str, Any]:
        if not has_openai_api_key(self.api_key):
            raise AppError(
                "PREFERENCE_PARSE_FAILED",
                "교양 선호 파서 LLM 설정이 없습니다.",
                hint="OPENAI_API_KEY를 설정하거나 테스트에서 llm을 주입해 주세요.",
            )

        request_payload = self._tool_call_request_payload(prompt)
        try:
            response_payload = request_chat_completions(
                request_payload,
                api_key=self.api_key,
                base_url=self.base_url,
                timeout_seconds=self.timeout_seconds,
            )
        except TimeoutError as exc:
            raise AppError(
                "PREFERENCE_PARSE_TIMEOUT",
                "교양 선호 파서 LLM 호출 시간이 초과되었습니다.",
            ) from exc
        except RuntimeError as exc:
            raise AppError(
                "PREFERENCE_PARSE_FAILED",
                "교양 선호 파서 LLM 호출에 실패했습니다.",
            ) from exc

        return self._result_from_chat_completions_response(response_payload)

    def _tool_call_request_payload(self, prompt: str) -> dict[str, Any]:
        output_schema = GeneralPreferenceLLMOutput.model_json_schema()
        return {
            "model": self.model_name,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": GENERAL_PREFERENCE_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "prompt": prompt,
                            "supported_hard_fields": sorted(HARD_FIELDS),
                            "supported_soft_fields": sorted(SOFT_FIELDS),
                            "output_contract": (
                                "Call general_preference_from_prompt with only "
                                "preference_result. Do not copy prompt or "
                                "supported_*_fields into the tool arguments."
                            ),
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "general_preference_from_prompt",
                        "description": (
                            "Split explicit general-education timetable preferences "
                            "into hard, soft, unsupported, and warning groups. "
                            "The input prompt must not be copied into arguments."
                        ),
                        "parameters": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "preference_result": output_schema,
                            },
                            "required": ["preference_result"],
                        },
                    },
                }
            ],
            "tool_choice": {
                "type": "function",
                "function": {"name": "general_preference_from_prompt"},
            },
        }

    @staticmethod
    def _result_from_chat_completions_response(
        response_payload: dict[str, Any],
    ) -> dict[str, Any]:
        choices = response_payload.get("choices") or []
        if not choices:
            raise ValueError("OpenAI response did not include choices")
        message = choices[0].get("message") or {}
        tool_calls = message.get("tool_calls") or []
        if not tool_calls:
            raise ValueError("OpenAI response did not include a tool call")
        function = tool_calls[0].get("function") or {}
        arguments_text = function.get("arguments") or "{}"
        arguments = json.loads(arguments_text)
        arguments = GeneralPreferenceParser._normalize_llm_output_payload(arguments)
        return arguments

    def _build_default_llm(self) -> Any:
        if not has_openai_api_key(self.api_key):
            raise AppError(
                "PREFERENCE_PARSE_FAILED",
                "교양 선호 파서 LLM 설정이 없습니다.",
                hint="OPENAI_API_KEY를 설정하거나 테스트에서 llm을 주입해 주세요.",
            )
        try:
            from langchain_openai import ChatOpenAI
        except ImportError as exc:
            raise AppError(
                "PREFERENCE_PARSE_FAILED",
                "교양 선호 파서 LLM 클라이언트를 사용할 수 없습니다.",
            ) from exc
        kwargs: dict[str, Any] = {
            "model": self.model_name,
            "api_key": self.api_key,
            "temperature": 0,
        }
        if self.base_url != DEFAULT_OPENAI_BASE_URL:
            kwargs["base_url"] = self.base_url
        return ChatOpenAI(**kwargs)

    @staticmethod
    def _messages(prompt: str) -> list[tuple[str, str]]:
        payload = {
            "prompt": prompt,
            "supported_hard_fields": sorted(HARD_FIELDS),
            "supported_soft_fields": sorted(SOFT_FIELDS),
        }
        return [
            ("system", GENERAL_PREFERENCE_SYSTEM_PROMPT),
            ("human", json.dumps(payload, ensure_ascii=False)),
        ]

    @staticmethod
    def _coerce_output(raw_output: Any) -> GeneralPreferenceLLMOutput:
        if isinstance(raw_output, GeneralPreferenceLLMOutput):
            return raw_output
        if isinstance(raw_output, str):
            return GeneralPreferenceLLMOutput.model_validate_json(raw_output)
        if isinstance(raw_output, dict):
            return GeneralPreferenceLLMOutput.model_validate(
                GeneralPreferenceParser._normalize_llm_output_payload(raw_output)
            )
        if hasattr(raw_output, "model_dump"):
            return GeneralPreferenceLLMOutput.model_validate(
                GeneralPreferenceParser._normalize_llm_output_payload(
                    raw_output.model_dump()
                )
            )
        raise TypeError(f"unsupported LLM output type: {type(raw_output).__name__}")

    @staticmethod
    def _normalize_llm_output_payload(raw_output: dict[str, Any]) -> dict[str, Any]:
        """Accept safe near-schema LLM outputs without changing their meaning."""

        payload = raw_output.get("preference_result", raw_output)
        normalized = dict(payload)
        soft = normalized.get("soft_conditions")
        if isinstance(soft, dict):
            normalized_soft = dict(soft)
            if (
                "preferred_days" in normalized_soft
                and "preferred_free_days" not in normalized_soft
            ):
                normalized_soft["preferred_free_days"] = normalized_soft.pop(
                    "preferred_days"
                )
            normalized["soft_conditions"] = normalized_soft

        unsupported = normalized.get("unsupported_conditions")
        if isinstance(unsupported, list):
            normalized["unsupported_conditions"] = [
                GeneralPreferenceParser._normalize_unsupported_condition(item)
                for item in unsupported
            ]
        return normalized

    @staticmethod
    def _normalize_unsupported_condition(value: Any) -> Any:
        if not isinstance(value, str):
            return value
        return {
            "source_text": value,
            "reason_code": "UNSUPPORTED_CONDITION",
            "reason": "현재 PlaNU 데이터와 규칙으로 적용할 수 없는 조건입니다.",
        }

    @staticmethod
    def _validation_error(exc: ValidationError) -> AppError:
        text = str(exc)
        code = "INVALID_PREFERENCE_OUTPUT"
        if "course names cannot be both" in text or "latest_end_time" in text:
            code = "CONFLICTING_PREFERENCE_CONDITIONS"
        return AppError(
            code,
            "교양 선호 조건을 검증할 수 없습니다.",
            details={"error_count": len(exc.errors())},
        )

    def _validate_and_normalize(
        self,
        parsed: GeneralPreferenceLLMOutput,
        *,
        raw_output: Any,
        prompt: str,
    ) -> GeneralPreferenceParseResult:
        warnings = list(parsed.warnings)
        unsupported = list(parsed.unsupported_conditions)
        hard_dump = self._scoped_dump(parsed.hard_conditions)
        soft_dump = self._scoped_dump(parsed.soft_conditions)

        self._normalize_ambiguous_morning_strength(prompt, hard_dump, soft_dump, warnings)
        self._recover_soft_course_preferences(prompt, hard_dump, soft_dump)

        hard_dump, soft_dump = self._drop_hard_soft_duplicates(
            hard_dump,
            soft_dump,
            warnings,
        )
        self._detect_day_conflicts(hard_dump, soft_dump, warnings)
        self._detect_course_conflicts(hard_dump, soft_dump, warnings)

        try:
            hard = HardPreferenceConditions.model_validate(hard_dump).to_preference_rules()
            soft = SoftPreferenceConditions.model_validate(soft_dump).to_preference_rules()
        except ValidationError as exc:
            raise self._validation_error(exc) from exc

        raw = self._safe_raw_output(raw_output)
        return GeneralPreferenceParseResult(
            hard_conditions=hard,
            soft_conditions=soft,
            unsupported_conditions=self._dedupe_unsupported(unsupported),
            warnings=self._dedupe_warnings(warnings),
            raw_output=raw,
        )

    @staticmethod
    def _recover_soft_course_preferences(
        prompt: str,
        hard: dict[str, Any],
        soft: dict[str, Any],
    ) -> None:
        """Recover explicit positive soft course names the LLM omitted."""

        existing = set(hard.get("required_course_names") or [])
        existing.update(hard.get("excluded_course_names") or [])
        existing.update(soft.get("preferred_course_names") or [])
        existing.update(soft.get("avoided_course_names") or [])
        recovered: list[str] = []
        for match in re.finditer(
            r"([가-힣A-Za-z0-9&·()\s]{2,40}?)(?:은|는|을|를)\s*"
            r"(?:우선하고 싶|우선적으로 고려|선호|가능하면 듣고 싶|듣고 싶)",
            prompt,
        ):
            name = GeneralPreferenceParser._clean_recovered_course_name(
                match.group(1)
            )
            if (
                not name
                or GeneralPreferenceParser._looks_like_non_course_phrase(name)
            ):
                continue
            if name in (hard.get("required_course_names") or []):
                hard["required_course_names"] = [
                    item for item in hard["required_course_names"] if item != name
                ]
                existing.discard(name)
            if name in (hard.get("excluded_course_names") or []):
                hard["excluded_course_names"] = [
                    item for item in hard["excluded_course_names"] if item != name
                ]
                existing.discard(name)
            if name in existing and not GeneralPreferenceParser._is_duplicate_course_suffix(name, existing):
                continue
            if GeneralPreferenceParser._is_duplicate_course_suffix(name, existing):
                continue
            recovered.append(name)
            existing.add(name)
        if recovered:
            soft["preferred_course_names"] = [
                *(soft.get("preferred_course_names") or []),
                *recovered,
            ]

    @staticmethod
    def _looks_like_non_course_phrase(value: str) -> bool:
        return any(
            token in value
            for token in (
                "수업",
                "과제",
                "발표",
                "교수",
                "평점",
                "요일",
                "오전",
                "오후",
            )
        )

    @staticmethod
    def _normalize_ambiguous_morning_strength(
        prompt: str,
        hard: dict[str, Any],
        soft: dict[str, Any],
        warnings: list[PreferenceWarning],
    ) -> None:
        if hard.get("earliest_start_time") != MORNING_END_TIME:
            return
        if "오전" not in prompt:
            return
        if not any(token in prompt for token in ("싫어", "피하고 싶", "별로")):
            return
        if any(
            token in prompt
            for token in ("절대", "하나도", "넣지 마", "안 돼", "금지", "무조건")
        ):
            return
        hard.pop("earliest_start_time", None)
        soft.setdefault("preferred_first_class_time", MORNING_END_TIME)
        warnings.append(
            PreferenceWarning(
                code="AMBIGUOUS_CONDITION_STRENGTH",
                message="오전 수업 회피 표현을 soft 조건으로 해석했습니다.",
                source_text="오전 수업",
            )
        )

    @staticmethod
    def _clean_recovered_course_name(value: str) -> str:
        name = " ".join(value.strip().split())
        return re.sub(
            r"^(?:가능하면|되도록|가급적|꼭 필요한 것은 아니지만|필수까지는 아니고)\s+",
            "",
            name,
        ).strip()

    @staticmethod
    def _is_duplicate_course_suffix(value: str, existing: set[str]) -> bool:
        return any(value.endswith(name) for name in existing if name != value)

    @staticmethod
    def _scoped_dump(
        rules: BaseModel,
    ) -> dict[str, Any]:
        return rules.model_dump(mode="json", exclude_unset=True)

    @staticmethod
    def _drop_hard_soft_duplicates(
        hard: dict[str, Any],
        soft: dict[str, Any],
        warnings: list[PreferenceWarning],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        hard_days = set(hard.get("excluded_days") or []) | set(hard.get("required_free_days") or [])
        preferred_days = [day for day in soft.get("preferred_free_days") or [] if day not in hard_days]
        if preferred_days != (soft.get("preferred_free_days") or []):
            soft["preferred_free_days"] = preferred_days
            warnings.append(
                PreferenceWarning(
                    code="HARD_SOFT_DUPLICATE_REMOVED",
                    message="같은 요일 공강 조건은 더 강한 hard 조건으로 통합했습니다.",
                )
            )

        hard_courses = set(hard.get("required_course_names") or []) | set(hard.get("excluded_course_names") or [])
        for field_name in ("preferred_course_names", "avoided_course_names"):
            values = [name for name in soft.get(field_name) or [] if name not in hard_courses]
            if values != (soft.get(field_name) or []):
                soft[field_name] = values
                warnings.append(
                    PreferenceWarning(
                        code="HARD_SOFT_DUPLICATE_REMOVED",
                        message="같은 과목 조건은 더 강한 hard 조건으로 통합했습니다.",
                    )
                )

        if hard.get("earliest_start_time") and soft.get("preferred_first_class_time"):
            if (
                time_to_minutes(soft["preferred_first_class_time"])
                <= time_to_minutes(hard["earliest_start_time"])
            ):
                soft.pop("preferred_first_class_time")
                warnings.append(
                    PreferenceWarning(
                        code="HARD_SOFT_DUPLICATE_REMOVED",
                        message="첫 수업 시작 선호는 더 강한 hard 시작 시간 조건으로 통합했습니다.",
                    )
                )
        return hard, soft

    @staticmethod
    def _detect_day_conflicts(
        hard: dict[str, Any],
        soft: dict[str, Any],
        warnings: list[PreferenceWarning],
    ) -> None:
        excluded = set(hard.get("excluded_days") or [])
        required_free = set(hard.get("required_free_days") or [])
        if excluded & required_free:
            warnings.append(
                PreferenceWarning(
                    code="CONFLICTING_CONDITIONS",
                    message="같은 요일이 제외 요일과 필수 공강 요일에 동시에 포함되어 있습니다.",
                )
            )
        preferred = set(soft.get("preferred_free_days") or [])
        if excluded & preferred:
            warnings.append(
                PreferenceWarning(
                    code="CONFLICTING_CONDITIONS",
                    message="요일 hard 제외 조건과 soft 선호 조건이 충돌합니다.",
                )
            )

    @staticmethod
    def _detect_course_conflicts(
        hard: dict[str, Any],
        soft: dict[str, Any],
        warnings: list[PreferenceWarning],
    ) -> None:
        required = set(hard.get("required_course_names") or [])
        excluded = set(hard.get("excluded_course_names") or [])
        if required & excluded:
            names = ", ".join(sorted(required & excluded))
            raise AppError(
                "CONFLICTING_PREFERENCE_CONDITIONS",
                f"필수 과목과 제외 과목이 충돌합니다: {names}.",
            )
        preferred = set(soft.get("preferred_course_names") or [])
        avoided = set(soft.get("avoided_course_names") or [])
        if preferred & avoided:
            names = ", ".join(sorted(preferred & avoided))
            raise AppError(
                "CONFLICTING_PREFERENCE_CONDITIONS",
                f"선호 과목과 비선호 과목이 충돌합니다: {names}.",
            )

    @staticmethod
    def _dedupe_unsupported(
        values: list[UnsupportedCondition],
    ) -> list[UnsupportedCondition]:
        seen: set[tuple[str, str]] = set()
        deduped: list[UnsupportedCondition] = []
        for item in values:
            key = (item.source_text, item.reason_code)
            if key in seen:
                continue
            deduped.append(item)
            seen.add(key)
        return deduped

    @staticmethod
    def _dedupe_warnings(values: list[PreferenceWarning]) -> list[PreferenceWarning]:
        seen: set[tuple[str, str, str | None]] = set()
        deduped: list[PreferenceWarning] = []
        for item in values:
            key = (item.code, item.message, item.source_text)
            if key in seen:
                continue
            deduped.append(item)
            seen.add(key)
        return deduped

    @staticmethod
    def _safe_raw_output(raw_output: Any) -> dict[str, Any] | str | None:
        if raw_output is None or isinstance(raw_output, str):
            return raw_output
        if isinstance(raw_output, dict):
            return raw_output
        if hasattr(raw_output, "model_dump"):
            return raw_output.model_dump(mode="json")
        return repr(raw_output)


def parse_general_preferences(
    prompt: str,
    *,
    llm: Any | None = None,
    model_name: str | None = None,
    base_url: str | None = None,
    timeout_seconds: int = 60,
) -> GeneralPreferenceParseResult:
    """Functional API for parsing general-education preference prompts."""

    return GeneralPreferenceParser(
        llm=llm,
        model_name=model_name,
        base_url=base_url,
        timeout_seconds=timeout_seconds,
    ).parse(prompt)


def supported_general_preference_fields() -> dict[str, list[str]]:
    """Expose parser boundaries for integration tests and API documentation."""

    return {
        "hard_conditions": sorted(HARD_FIELDS),
        "soft_conditions": sorted(SOFT_FIELDS),
        "day_values": [day.value for day in Day],
    }
