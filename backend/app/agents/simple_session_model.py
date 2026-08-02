"""Small deterministic fallback model for session-state agent development."""

from __future__ import annotations

import json
from typing import Any


class SimpleSessionStateModel:
    """Return tool calls for common Korean PlaNU preference phrases.

    This is intentionally conservative and exists so the API can run in local
    development without embedding API keys. Tests can override the agent
    dependency with richer fake models, and production can inject an LLM-backed
    model through the dependency container.
    """

    def __call__(self, payload: dict[str, Any]) -> dict[str, Any]:
        messages = payload.get("messages") or []
        user_content = _user_content(messages)
        text = str(user_content.get("user_message") or user_content.get("message") or "")
        current = user_content.get("current_state_summary") or {}

        transcript = [
            message for message in messages
            if isinstance(message, dict) and message.get("role") == "tool"
        ]
        if len(transcript) > 1:
            return self._after_tool(transcript[-1], text)

        calls: list[dict[str, Any]] = []
        unresolved: list[dict[str, Any]] = []

        hard: dict[str, Any] = {}
        soft: dict[str, Any] = {}
        if "금요일" in text and any(marker in text for marker in ("반드시", "꼭", "무조건")):
            hard["required_free_days"] = ["FRI"]
        elif "금요일" in text and any(marker in text for marker in ("가능하면", "선호", "좋겠")):
            soft["preferred_free_days"] = ["FRI"]
        if "월요일" in text and any(marker in text for marker in ("가능하면", "선호", "좋겠")):
            soft["preferred_free_days"] = [*soft.get("preferred_free_days", []), "MON"]
        if "10시 이전" in text and any(marker in text for marker in ("가능하면", "피하고 싶")):
            soft["preferred_earliest_start_time"] = "10:00"
        elif "10시 이전" in text:
            hard["earliest_start_time"] = "10:00"
        if ("5시 30분 이후" in text or "17시 30분 이후" in text) and any(
            marker in text for marker in ("절대", "안 돼", "안돼")
        ):
            hard["latest_end_time"] = "17:30"
        if "아침 수업" in text:
            unresolved.append({
                "source_text": "아침 수업",
                "reason": "구체적인 시간이 없어 조건으로 확정할 수 없습니다.",
                "needed_information": "피하고 싶은 시작 시간을 HH:MM으로 알려주세요.",
                "requires_user_confirmation": True,
            })

        if hard or soft:
            arguments: dict[str, Any] = {}
            if hard:
                arguments["hard"] = hard
            if soft:
                arguments["soft"] = soft
            calls.append({"name": "update_timetable_preferences", "arguments": arguments})

        course_name = _mentioned_course_name(text)
        if course_name is not None and not calls:
            catalog_id = current.get("major_catalog_id") or current.get("elective_catalog_id")
            if catalog_id:
                calls.append({
                    "name": "search_courses_by_name",
                    "arguments": {"catalog_id": catalog_id, "query": course_name},
                })
            else:
                unresolved.append({
                    "source_text": course_name,
                    "reason": "검색할 catalog ID가 세션에 없습니다.",
                    "needed_information": "전공 또는 교양 수강편람을 먼저 등록해 주세요.",
                    "requires_user_confirmation": True,
                })

        if calls:
            return {"tool_calls": calls, "unresolved_requests": unresolved}
        return {
            "message": "확인이 필요한 요청이 있습니다." if unresolved else "변경할 조건을 찾지 못했습니다.",
            "unresolved_requests": unresolved,
        }

    def _after_tool(self, last_tool: dict[str, Any], text: str) -> dict[str, Any]:
        if last_tool.get("name") != "search_courses_by_name":
            return {"message": "요청한 조건을 세션에 반영했습니다.", "tool_calls": []}
        content = last_tool.get("content") or {}
        candidates = content.get("candidates") or []
        if content.get("resolution") == "EXACT" and len(candidates) == 1:
            course_id = candidates[0]["course_id"]
            if any(marker in text for marker in ("빼", "제외", "싫")):
                return {
                    "tool_calls": [{
                        "name": "update_timetable_preferences",
                        "arguments": {"hard": {"excluded_course_ids": [course_id]}},
                    }]
                }
            if any(marker in text for marker in ("선호", "좋", "싶")) and "꼭" not in text:
                return {
                    "tool_calls": [{
                        "name": "update_timetable_preferences",
                        "arguments": {"soft": {"preferred_course_ids": [course_id]}},
                    }]
                }
            return {
                "tool_calls": [{
                    "name": "update_timetable_preferences",
                    "arguments": {"hard": {"required_course_ids": [course_id]}},
                }]
            }
        return {
            "message": "과목을 하나로 확정할 수 없어 확인이 필요합니다.",
            "unresolved_requests": [{
                "source_text": _mentioned_course_name(text) or "과목명",
                "reason": "검색 결과가 없거나 여러 후보가 있어 임의로 선택하지 않았습니다.",
                "needed_information": "후보 중 사용할 과목을 선택해 주세요.",
                "requires_user_confirmation": True,
            }],
        }


def _mentioned_course_name(text: str) -> str | None:
    for name in ("자료구조", "컴퓨터프로그래밍", "고급영어", "대학영어", "알고리즘"):
        if name in text:
            return name
    for marker in ("는", "은", "을", "를"):
        if marker in text:
            candidate = text.split(marker, 1)[0].strip()
            if 1 < len(candidate) <= 30 and " " not in candidate:
                return candidate
    first = text.strip().split(maxsplit=1)[0] if text.strip() else ""
    for suffix in ("은", "는", "을", "를", "이", "가"):
        if first.endswith(suffix):
            first = first[: -len(suffix)]
            break
    if 1 < len(first) <= 30:
        return first
    return None


def _user_content(messages: list[Any]) -> dict[str, Any]:
    for message in messages:
        if not isinstance(message, dict) or message.get("role") != "user":
            continue
        content = message.get("content") or {}
        if isinstance(content, dict):
            return content
        if isinstance(content, str):
            try:
                parsed = json.loads(content)
            except json.JSONDecodeError:
                return {"user_message": content}
            return parsed if isinstance(parsed, dict) else {"user_message": content}
    return {}
