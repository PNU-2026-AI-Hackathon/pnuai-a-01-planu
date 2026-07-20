"""Parse user-selected major courses from natural language."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from pydantic import ValidationError

from ..models.major_selection import MajorCourseReference, MajorSelectionParseResult
from .llm_preference_parser import (
    DEFAULT_CHAT_PROXY_URL,
    DEFAULT_OPENAI_MODEL,
    chat_completions_url,
    has_proxy_token,
    load_proxy_env,
)
from .major_course_matcher import normalize_course_name, normalize_section


SYSTEM_PROMPT = """당신은 사용자가 이미 선택한 전공 과목명과 분반을 구조화하는 파서입니다.

역할 제한:
- 전공 과목을 추천하거나 사용자가 말하지 않은 과목과 분반을 추가하지 마세요.
- 사용자의 자연어에서 course_name과 section만 추출하세요.
- 분반이 명시되지 않았다면 추론하지 말고 null로 반환하세요.
- 교수명이나 수업 시간을 근거로 분반을 추론하지 마세요.
- 실제 과목 또는 분반의 존재 여부는 판단하지 마세요.
- 과목명 자동 교정, 유사 과목명 대체, 전공필수 자동 추가를 하지 마세요.
- 확정되지 않은 표현은 selected_courses에 넣지 말고 ambiguous_texts에 원문을 넣으세요.
- 사용자가 듣지 않겠다고 한 과목은 selected_courses에 넣지 마세요.
- 이전 선택을 취소하거나 변경한 경우 최종적으로 확정한 선택만 반환하세요.
- "A 또는 B", "둘 중 하나", "고민 중", "들을 수도 있다"처럼 선택이 확정되지 않은 문장은 selected_courses에 넣지 말고 원문을 ambiguous_texts에 넣으세요.
- 한 문장 안에 미확정 선택과 확정 선택이 함께 있으면, 확정 선택은 selected_courses에 넣고 ambiguous_texts에는 사용자의 전체 원문 문장을 그대로 넣으세요.
- 하나의 분반 표현을 여러 과목에 임의로 연결하지 마세요.
- 사용자가 말하지 않은 과목이나 분반을 자동 보완하지 마세요.
- 설명 문장을 출력하지 말고 지정된 구조화 형식만 반환하세요.

짧은 예시:
- "자료구조는 안 듣고 컴퓨터구조 003분반만 들을 거야" -> selected_courses: [{"course_name": "컴퓨터구조", "section": "003"}]
- "자료구조 001분반 대신 003분반으로 할게" -> selected_courses: [{"course_name": "자료구조", "section": "003"}]
- "자료구조나 알고리즘 중 하나 들을 예정이야" -> selected_courses: [], ambiguous_texts: ["자료구조나 알고리즘 중 하나 들을 예정이야"]
- "자료구조 001분반은 고민 중이고 컴퓨터구조는 들을 거야" -> selected_courses: [{"course_name": "컴퓨터구조", "section": null}], ambiguous_texts: ["자료구조 001분반은 고민 중이고 컴퓨터구조는 들을 거야"]
- "자료구조, 컴퓨터구조 003분반" -> 003분반을 자료구조에 임의로 연결하지 마세요.

출력 형식:
{
  "selected_courses": [
    {"course_name": "자료구조", "section": "001"}
  ],
  "ambiguous_texts": []
}
"""


class EmptyMajorSelectionPromptError(ValueError):
    """Raised when the major-selection prompt is empty."""


class MajorSelectionLLMError(RuntimeError):
    """Raised when the major-selection LLM call fails."""


class MajorSelectionLLMTimeoutError(MajorSelectionLLMError):
    """Raised when the major-selection LLM call times out."""


class InvalidMajorSelectionOutputError(ValueError):
    """Raised when the LLM output cannot become a valid parse result."""


class MajorSelectionParser:
    """Convert free text into a validated ``MajorSelectionParseResult``."""

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
        self.model_name = model_name or os.getenv("OPENAI_MODEL", DEFAULT_OPENAI_MODEL)
        self.base_url = base_url or os.getenv("CHAT_PROXY_URL", DEFAULT_CHAT_PROXY_URL)
        self.proxy_token = self._env_proxy_token()
        self.timeout_seconds = timeout_seconds

    def parse(self, prompt: str) -> MajorSelectionParseResult:
        """Parse explicit major course selections without catalog matching."""

        text = prompt.strip()
        if not text:
            raise EmptyMajorSelectionPromptError("major selection prompt is empty")

        payload = build_major_selection_parse_payload(prompt=text)
        try:
            raw_output = self._invoke_llm(payload)
        except TimeoutError as exc:
            raise MajorSelectionLLMTimeoutError(
                "major selection LLM request timed out"
            ) from exc
        except ValidationError as exc:
            raise InvalidMajorSelectionOutputError(
                "major selection LLM output failed validation"
            ) from exc
        except Exception as exc:
            raise MajorSelectionLLMError("major selection LLM request failed") from exc

        try:
            result = self._validate_output(raw_output)
        except (TypeError, ValueError, ValidationError, json.JSONDecodeError) as exc:
            raise InvalidMajorSelectionOutputError(
                "major selection LLM output failed validation"
            ) from exc

        if not result.selected_courses and not result.ambiguous_texts:
            raise InvalidMajorSelectionOutputError(
                "major selection LLM output was empty"
            )
        return result

    def _invoke_llm(self, payload: dict[str, Any]) -> Any:
        if self.llm is None:
            return self._invoke_openai_compatible_tool_call(payload)
        if hasattr(self.llm, "with_structured_output"):
            structured_llm = self.llm.with_structured_output(MajorSelectionParseResult)
            return structured_llm.invoke(self._messages(payload))
        if callable(self.llm):
            return self.llm(payload)
        raise RuntimeError("configured LLM is not invokable")

    def _invoke_openai_compatible_tool_call(self, payload: dict[str, Any]) -> dict[str, Any]:
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
            with urllib.request.urlopen(
                request,
                timeout=self.timeout_seconds,
            ) as response:
                response_payload = json.loads(response.read().decode("utf-8"))
        except TimeoutError:
            raise
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"proxy request failed with status {exc.code}") from exc
        except urllib.error.URLError as exc:
            reason = getattr(exc, "reason", "unknown")
            if isinstance(reason, TimeoutError):
                raise reason
            raise RuntimeError("proxy request failed") from exc

        return self._result_from_chat_completions_response(response_payload)

    def _tool_call_request_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "model": self.model_name,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "major_selection_from_prompt",
                        "description": (
                            "Return only explicitly selected major course names "
                            "and sections from the user's prompt."
                        ),
                        "parameters": MajorSelectionParseResult.model_json_schema(),
                    },
                }
            ],
            "tool_choice": {
                "type": "function",
                "function": {"name": "major_selection_from_prompt"},
            },
        }

    @staticmethod
    def _result_from_chat_completions_response(
        response_payload: dict[str, Any],
    ) -> dict[str, Any]:
        choices = response_payload.get("choices") or []
        if not choices:
            raise ValueError("proxy response did not include choices")
        message = choices[0].get("message") or {}
        tool_calls = message.get("tool_calls") or []
        if not tool_calls:
            raise ValueError("proxy response did not include a tool call")
        function = (tool_calls[0].get("function") or {})
        arguments_text = function.get("arguments") or "{}"
        arguments = json.loads(arguments_text)
        MajorSelectionParseResult.model_validate(arguments)
        return arguments

    @staticmethod
    def _validate_output(raw_output: Any) -> MajorSelectionParseResult:
        if isinstance(raw_output, MajorSelectionParseResult):
            result = raw_output
        elif isinstance(raw_output, str):
            result = MajorSelectionParseResult.model_validate_json(raw_output)
        elif isinstance(raw_output, dict):
            result = MajorSelectionParseResult.model_validate(raw_output)
        elif hasattr(raw_output, "model_dump"):
            result = MajorSelectionParseResult.model_validate(raw_output.model_dump())
        else:
            raise TypeError(f"unsupported LLM output type: {type(raw_output).__name__}")

        selected_courses = [
            MajorCourseReference(
                course_name=reference.course_name,
                section=normalize_section(reference.section),
            )
            for reference in result.selected_courses
        ]
        ambiguous_texts = [text.strip() for text in result.ambiguous_texts if text.strip()]
        return MajorSelectionParseResult(
            selected_courses=deduplicate_major_course_references(selected_courses),
            ambiguous_texts=ambiguous_texts,
        )

    @staticmethod
    def _messages(payload: dict[str, Any]) -> list[tuple[str, str]]:
        return [
            ("system", SYSTEM_PROMPT),
            ("human", json.dumps(payload, ensure_ascii=False)),
        ]

    @staticmethod
    def _env_proxy_token() -> str | None:
        return os.getenv("PROXY_TOKEN")


def build_major_selection_parse_payload(*, prompt: str) -> dict[str, str]:
    """Build the LLM input for explicit major course selection parsing."""

    return {
        "prompt": prompt.strip(),
        "instruction": (
            "Extract only course_name and section values explicitly stated in "
            "prompt. Return section as null when the user did not explicitly "
            "write a section. Do not infer a section from professor, time, "
            "course existence, or context. Put uncertain or non-final selection "
            "phrases into ambiguous_texts. Do not include courses the user says "
            "they will not take. If the user cancels or changes a previous "
            "selection, return only the final confirmed selection. Treat phrases "
            "like 'A 또는 B', '둘 중 하나', '고민 중', and '들을 수도 있다' "
            "as ambiguous_texts, not selected_courses. Do not attach one section "
            "expression to multiple courses. Do not automatically fill in "
            "unstated courses or sections. If one sentence includes both an "
            "uncertain course and a confirmed course, extract the confirmed "
            "course and put the whole original sentence into ambiguous_texts. "
            "Examples: '자료구조는 안 듣고 "
            "컴퓨터구조 003분반만 들을 거야' returns only 컴퓨터구조 003; "
            "'자료구조 001분반 대신 003분반으로 할게' returns only 자료구조 "
            "003; '자료구조나 알고리즘 중 하나 들을 예정이야' returns no "
            "selected courses and adds the sentence to ambiguous_texts; "
            "'자료구조 001분반은 고민 중이고 컴퓨터구조는 들을 거야' returns "
            "컴퓨터구조 with null section and adds the whole sentence to "
            "ambiguous_texts; "
            "'자료구조, 컴퓨터구조 003분반' must not attach 003 to 자료구조."
        ),
    }


def deduplicate_major_course_references(
    references: list[MajorCourseReference],
) -> list[MajorCourseReference]:
    """Remove duplicate selected courses while preserving LLM output order."""

    seen: set[tuple[str, str | None]] = set()
    deduplicated: list[MajorCourseReference] = []
    for reference in references:
        key = (
            normalize_course_name(reference.course_name),
            normalize_section(reference.section),
        )
        if key in seen:
            continue
        seen.add(key)
        deduplicated.append(reference)
    return deduplicated


def parse_major_selection(
    prompt: str,
    *,
    llm: Any | None = None,
    model_name: str | None = None,
    base_url: str | None = None,
) -> MajorSelectionParseResult:
    """Functional API for parsing user-selected major courses."""

    return MajorSelectionParser(
        llm=llm,
        model_name=model_name,
        base_url=base_url,
    ).parse(prompt)
