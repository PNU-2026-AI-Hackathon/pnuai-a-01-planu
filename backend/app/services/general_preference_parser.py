"""Parse general-education preference prompts into supported rule groups."""

from __future__ import annotations

import json
import os
from typing import Any

from pydantic import BaseModel, ValidationError

from ..core.errors import AppError
from ..models.course import Day, time_to_minutes
from ..models.preference import (
    GeneralPreferenceLLMOutput,
    GeneralPreferenceParseResult,
    HardPreferenceConditions,
    PreferenceRules,
    PreferenceWarning,
    SoftPreferenceConditions,
    UnsupportedCondition,
)
from .llm_preference_parser import (
    DEFAULT_CHAT_PROXY_URL,
    DEFAULT_OPENAI_MODEL,
    has_proxy_token,
    load_proxy_env,
)


MORNING_END_TIME = "10:00"
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
- 수강편람에 존재하는 과목인지 추측하지 마세요.
- 과목명 필드에는 사용자가 쓴 구체적인 과목명만 넣으세요.
- 과제량, 시험 난이도, 발표/팀플 여부, 학점, 교수 평점/친절함은 지원하지 않습니다.
- 요일은 MON, TUE, WED, THU, FRI enum을 우선 사용하세요.
- 시간은 HH:MM 24시간 형식만 사용하세요.
- PlaNU의 오전 수업 기준은 {MORNING_END_TIME} 이전 시작입니다.
- 오전 수업 hard 금지는 earliest_start_time: "{MORNING_END_TIME}" 하나로 표현하세요.
- 오전 수업 soft 회피는 preferred_first_class_time: "{MORNING_END_TIME}"로 표현하세요.
- 같은 의미를 hard와 soft에 중복해서 넣지 마세요.
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
    ) -> None:
        load_proxy_env()
        self.llm = llm
        self.model_name = model_name or os.getenv("OPENAI_MODEL", DEFAULT_OPENAI_MODEL)
        self.base_url = base_url or os.getenv("CHAT_PROXY_URL", DEFAULT_CHAT_PROXY_URL)
        self.proxy_token = os.getenv("PROXY_TOKEN")

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

        return self._validate_and_normalize(parsed, raw_output=raw_output)

    def _invoke_llm(self, prompt: str) -> Any:
        try:
            llm = self.llm or self._build_default_llm()
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

    def _build_default_llm(self) -> Any:
        if not has_proxy_token(self.proxy_token):
            raise AppError(
                "PREFERENCE_PARSE_FAILED",
                "교양 선호 파서 LLM 설정이 없습니다.",
                hint="PROXY_TOKEN을 설정하거나 테스트에서 llm을 주입해 주세요.",
            )
        try:
            from langchain_openai import ChatOpenAI
        except ImportError as exc:
            raise AppError(
                "PREFERENCE_PARSE_FAILED",
                "교양 선호 파서 LLM 클라이언트를 사용할 수 없습니다.",
            ) from exc
        return ChatOpenAI(
            model=self.model_name,
            api_key=self.proxy_token,
            base_url=self.base_url,
            temperature=0,
        )

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
            return GeneralPreferenceLLMOutput.model_validate(raw_output)
        if hasattr(raw_output, "model_dump"):
            return GeneralPreferenceLLMOutput.model_validate(raw_output.model_dump())
        raise TypeError(f"unsupported LLM output type: {type(raw_output).__name__}")

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
    ) -> GeneralPreferenceParseResult:
        warnings = list(parsed.warnings)
        unsupported = list(parsed.unsupported_conditions)
        hard_dump = self._scoped_dump(parsed.hard_conditions)
        soft_dump = self._scoped_dump(parsed.soft_conditions)

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
) -> GeneralPreferenceParseResult:
    """Functional API for parsing general-education preference prompts."""

    return GeneralPreferenceParser(
        llm=llm,
        model_name=model_name,
        base_url=base_url,
    ).parse(prompt)


def supported_general_preference_fields() -> dict[str, list[str]]:
    """Expose parser boundaries for integration tests and API documentation."""

    return {
        "hard_conditions": sorted(HARD_FIELDS),
        "soft_conditions": sorted(SOFT_FIELDS),
        "day_values": [day.value for day in Day],
    }
