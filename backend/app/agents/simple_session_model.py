"""Deterministic local-development model for the session-state agent."""

from __future__ import annotations

import json
import re
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from ..services.preference_constants import MORNING_END_TIME


CourseIntent = Literal["required", "excluded", "preferred", "disliked"]

DAY_ALIASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("MON", ("월요일", "월욜")),
    ("TUE", ("화요일", "화욜")),
    ("WED", ("수요일", "수욜")),
    ("THU", ("목요일", "목욜")),
    ("FRI", ("금요일", "금욜")),
    ("SAT", ("토요일", "토욜")),
    ("SUN", ("일요일", "일욜")),
)
HARD_FREE_DAY_MARKERS = ("공강", "비워", "비우", "수업 없", "수업은 없", "없게", "빼줘")
SOFT_MARKERS = ("가능하면", "선호", "좋겠", "피하고 싶", "싫", "되도록")


KOREAN_DAY_ALIASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("MON", ("월요일", "월욜")),
    ("TUE", ("화요일", "화욜")),
    ("WED", ("수요일", "수욜")),
    ("THU", ("목요일", "목욜")),
    ("FRI", ("금요일", "금욜")),
)
KOREAN_HARD_FREE_DAY_MARKERS = (
    "공강",
    "비워",
    "비우",
    "수업 없",
    "수업은 없",
    "수업이 없",
    "빼줘",
)
KOREAN_SOFT_MARKERS = ("가능하면", "선호", "좋겠", "피하고", "싶어", "도록")
DEFAULT_MORNING_END_TIME = MORNING_END_TIME


class SessionStateModel(Protocol):
    """Minimal interface expected by ``SessionStateAgent``."""

    def __call__(self, payload: dict[str, Any]) -> dict[str, Any]:
        ...


class CourseMention(BaseModel):
    """One explicit course-name mention detected by the fallback model."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    intent: CourseIntent
    source_text: str = Field(min_length=1)
    catalog_hint: Literal["major", "elective"] | None = None


class LlmSessionStateModel:
    """Placeholder for a production tool-calling LLM adapter.

    The dependency container may instantiate this when a provider is explicitly
    configured. The agent itself stays SDK-agnostic; wiring a concrete OpenAI or
    proxy client belongs here rather than in ``SessionStateAgent``.
    """

    def __init__(self, *, provider: Any | None = None) -> None:
        self.provider = provider

    def __call__(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.provider is None:
            raise RuntimeError("LLM session-state model provider is not configured")
        if hasattr(self.provider, "invoke"):
            return self.provider.invoke(payload)
        if callable(self.provider):
            return self.provider(payload)
        raise RuntimeError("configured LLM provider is not invokable")


class SimpleSessionStateModel:
    """Conservative rule-based model for local development and tests.

    It is not intended to be a production natural-language model. It supports a
    small set of Korean PlaNU phrases deterministically, searches every explicit
    course mention, and waits to mutate preferences until all course searches
    have returned.
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
        if transcript and transcript[-1].get("name") == "update_timetable_preferences":
            return {"message": "요청한 조건을 세션에 반영했습니다.", "tool_calls": []}

        hard, soft, unresolved = _extract_non_course_preferences(text, current)
        mentions = _extract_course_mentions(text)
        search_results = _search_results_by_key(transcript)
        search_calls = _missing_search_calls(mentions, current, search_results)
        if search_calls:
            return {
                "tool_calls": search_calls,
                "unresolved_requests": unresolved,
            }

        resolved = _resolve_course_mentions(mentions, current, search_results)
        unresolved.extend(resolved["unresolved"])
        _merge_course_ids(hard, soft, resolved["course_ids"])

        if hard or soft:
            return {
                "tool_calls": [{
                    "name": "update_timetable_preferences",
                    "arguments": {
                        **({"hard": hard} if hard else {}),
                        **({"soft": soft} if soft else {}),
                    },
                }],
                "unresolved_requests": unresolved,
            }

        return {
            "message": (
                "적용 가능한 조건은 없고 확인이 필요한 요청이 있습니다."
                if unresolved
                else "변경할 조건을 찾지 못했습니다."
            ),
            "unresolved_requests": unresolved,
        }


def _extract_non_course_preferences(
    text: str,
    current: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    hard = _current_hard(current)
    soft = _current_soft(current)
    unresolved: list[dict[str, Any]] = []

    _apply_day_preferences(text, hard, soft)
    _apply_time_preferences(text, hard, soft)
    _apply_credit_preferences(text, hard)
    _apply_elective_area_preferences(text, hard)
    _apply_compact_schedule_preference(text, soft)

    if "금요일" in text and any(marker in text for marker in ("반드시", "꼭", "무조건")):
        hard["required_free_days"] = _append_unique(hard.get("required_free_days", []), "FRI")
    elif "금요일" in text and any(marker in text for marker in ("가능하면", "선호", "좋겠")):
        soft["preferred_free_days"] = _append_unique(soft.get("preferred_free_days", []), "FRI")
    if "월요일" in text and any(marker in text for marker in ("가능하면", "선호", "좋겠")):
        soft["preferred_free_days"] = _append_unique(soft.get("preferred_free_days", []), "MON")

    if "10시 이전" in text and any(marker in text for marker in ("가능하면", "피하고 싶")):
        soft["preferred_earliest_start_time"] = DEFAULT_MORNING_END_TIME
    elif "10시 이전" in text or "10시 전" in text:
        hard["earliest_start_time"] = DEFAULT_MORNING_END_TIME
    if "9시부터" in text or "9시 부터" in text:
        hard["earliest_start_time"] = "09:00"
    if ("5시 30분 이후" in text or "17시 30분 이후" in text) and any(
        marker in text for marker in ("절대", "안 돼", "안돼")
    ):
        hard["latest_end_time"] = "17:30"
    if "5시 이후" in text and any(marker in text for marker in ("안 돼", "안돼", "절대")):
        hard["latest_end_time"] = "17:00"
    if "6시까지" in text or "18시까지" in text:
        hard["latest_end_time"] = "18:00"
    if "아침 수업" in text and "earliest_start_time" not in hard and "preferred_earliest_start_time" not in soft:
        unresolved.append({
            "source_text": "아침 수업",
            "reason": "구체적인 시간이 없어 조건으로 확정할 수 없습니다.",
            "needed_information": "피하고 싶은 시작 시간을 HH:MM으로 알려주세요.",
            "requires_user_confirmation": True,
        })
    _apply_compact_schedule_preference(text, soft)
    return _drop_empty(hard), _drop_empty(soft), unresolved


def _apply_day_preferences(text: str, hard: dict[str, Any], soft: dict[str, Any]) -> None:
    for day, aliases in KOREAN_DAY_ALIASES:
        if not any(alias in text for alias in aliases):
            continue
        if not any(marker in text for marker in KOREAN_HARD_FREE_DAY_MARKERS):
            continue
        if any(marker in text for marker in KOREAN_SOFT_MARKERS):
            soft["preferred_free_days"] = _append_unique(soft.get("preferred_free_days", []), day)
        else:
            hard["required_free_days"] = _append_unique(hard.get("required_free_days", []), day)

    for day, aliases in DAY_ALIASES:
        if not any(alias in text for alias in aliases):
            continue
        if not any(marker in text for marker in HARD_FREE_DAY_MARKERS):
            continue
        if any(marker in text for marker in SOFT_MARKERS):
            soft["preferred_free_days"] = _append_unique(soft.get("preferred_free_days", []), day)
        else:
            hard["required_free_days"] = _append_unique(hard.get("required_free_days", []), day)


def _apply_time_preferences(text: str, hard: dict[str, Any], soft: dict[str, Any]) -> None:
    start_time = _extract_start_after_time(text)
    if start_time is not None:
        if any(marker in text for marker in SOFT_MARKERS):
            soft["preferred_earliest_start_time"] = start_time
        else:
            hard["earliest_start_time"] = start_time

    end_time = _extract_end_before_time(text)
    if end_time is not None:
        if _is_soft_time_request(text):
            soft["preferred_latest_end_time"] = end_time
        else:
            hard["latest_end_time"] = end_time


def _is_soft_time_request(text: str) -> bool:
    if any(marker in text for marker in ("꼭", "반드시", "무조건", "절대", "모든 수업")):
        return False
    return any(marker in text for marker in SOFT_MARKERS)


def _apply_elective_area_preferences(text: str, hard: dict[str, Any]) -> None:
    if not any(marker in text for marker in ("외국어", "외국어 강의", "외국어 영역")):
        return
    if not any(marker in text for marker in ("싫", "피하고", "빼", "제외", "듣지 않", "안듣")):
        return
    hard["excluded_elective_areas"] = _append_unique(
        hard.get("excluded_elective_areas", []),
        6,
    )


def _apply_credit_preferences(text: str, hard: dict[str, Any]) -> None:
    if any(marker in text for marker in ("\ucde8\uc18c", "\uc0ad\uc81c", "\uc9c0\uc6cc", "\uc5c6\uc560")):
        clear_fields = list(hard.get("clear_fields") or [])
        if any(marker in text for marker in ("\ucd5c\uc18c", "\uc774\uc0c1", "min")):
            clear_fields.append("min_credit")
            hard.pop("min_credit", None)
        if any(marker in text for marker in ("\ucd5c\ub300", "\uc774\ud558", "max")):
            clear_fields.append("max_credit")
            hard.pop("max_credit", None)
        if clear_fields:
            hard["clear_fields"] = list(dict.fromkeys(clear_fields))
        return
    if any(marker in text for marker in ("\ub108\ubb34 \ub9ce", "\ub108\ubb34 \uc801", "\uc2eb", "\uc5b4\ub5a4 \uac8c \uc88b\uc544", "\uc5b4\ub5bb\uac8c \uc0dd\uac01")):
        return
    handled_credit_bound = False
    over_limit = re.search(
        r"(?<!\d)(\d{1,2})\s*학점\s*(초과|넘|이상).{0,12}(?:못|안|싫|어려)",
        text,
    )
    if over_limit is not None:
        value = float(over_limit.group(1))
        operator = over_limit.group(2)
        hard["max_credit"] = value
        hard["max_credit_inclusive"] = operator != "이상"
        handled_credit_bound = True
    under_limit = re.search(
        r"(?<!\d)(\d{1,2})\s*학점\s*(미만|이하).{0,12}(?:못|안|싫|어려)",
        text,
    )
    if under_limit is not None:
        value = float(under_limit.group(1))
        operator = under_limit.group(2)
        hard["min_credit"] = value
        hard["min_credit_inclusive"] = operator != "이하"
        handled_credit_bound = True
    for field, pattern in ((
        "min_credit", r"(?:\ucd5c\uc18c|(?<!\d)\d{1,2}\s*\ud559\uc810\s*\uc774\uc0c1).*?(?<!\d)(\d{1,2})\s*\ud559\uc810",
    ), (
        "max_credit", r"(?:\ucd5c\ub300|(?<!\d)\d{1,2}\s*\ud559\uc810\s*\uc774\ud558).*?(?<!\d)(\d{1,2})\s*\ud559\uc810",
    )):
        match = re.search(pattern, text)
        if match is not None:
            hard[field] = float(match.group(1))
            handled_credit_bound = True
    if handled_credit_bound:
        return
    if "학점" not in text:
        return
    exact = re.search(r"(?<!\d)(\d{1,2})\s*학점(?:을|를)?\s*(?:듣고\s*싶|으로\s*(?:맞춰|만들))", text)
    if exact is not None:
        value = float(exact.group(1))
        hard["min_credit"] = value
        hard["min_credit_inclusive"] = True
        hard["max_credit"] = value
        hard["max_credit_inclusive"] = True
        return
    for match in re.finditer(r"(?<!\d)(\d{1,2})(?:\s*[-~]\s*(\d{1,2}))?\s*학점", text):
        lower = float(match.group(1))
        upper = float(match.group(2)) if match.group(2) is not None else None
        head = text[max(0, match.start() - 12):match.start()]
        tail = text[match.end():match.end() + 12]
        if upper is not None:
            hard["min_credit"] = lower
            hard["max_credit"] = upper
        elif "초과" in tail:
            hard["min_credit"] = lower
            hard["min_credit_inclusive"] = False
        elif any(marker in tail for marker in ("이상", "넘게", "넘도록")):
            hard["min_credit"] = lower
        elif "미만" in tail:
            hard["max_credit"] = lower
            hard["max_credit_inclusive"] = False
        elif any(marker in tail for marker in ("이하", "안쪽", "까지")):
            hard["max_credit"] = lower
        elif any(marker in head for marker in ("최소", "적어도")):
            hard["min_credit"] = lower
        elif any(marker in head for marker in ("최대", "많아도")):
            hard["max_credit"] = lower


def _apply_compact_schedule_preference(text: str, soft: dict[str, Any]) -> None:
    if any(marker in text for marker in ("몰아듣기", "몰아서", "모아서", "붙여서")):
        soft["compact_schedule"] = True
        return
    if any(marker in text for marker in ("연강", "연속 수업")) and any(
        marker in text for marker in ("피하고", "싫", "없게", "줄여", "적게")
    ):
        soft["compact_schedule"] = False
        return
    has_consecutive = "연강" in text or "연속" in text
    wants_compact = any(marker in text for marker in ("몰아듣기", "몰아서", "공강 없이 붙여"))
    avoids_consecutive = has_consecutive and any(
        marker in text for marker in ("피하고", "싫", "없게", "줄여", "적게")
    )
    if avoids_consecutive:
        soft["compact_schedule"] = False
    elif wants_compact or (has_consecutive and any(marker in text for marker in ("좋", "선호", "괜찮"))):
        soft["compact_schedule"] = True


def _extract_start_after_time(text: str) -> str | None:
    if any(marker in text for marker in ("이전 수업", "전 수업", "아침 수업", "오전 수업")):
        return _first_time(text) or (DEFAULT_MORNING_END_TIME if "아침" in text or "오전" in text else None)
    if not any(marker in text for marker in ("이전 수업", "전 수업", "전에 시작", "이후 시작")):
        return None
    return _first_time(text)


def _extract_end_before_time(text: str) -> str | None:
    if any(marker in text for marker in ("이전에 전부 끝", "이전에 모두 끝", "이전에는 끝", "이전 종료", "이전에 끝")):
        value = _first_time(text)
        if value is None:
            return None
        hour, minute = value.split(":", 1)
        if ("오후" in text or "저녁" in text) and 1 <= int(hour) <= 7:
            return f"{int(hour) + 12:02d}:{minute}"
        return value
    if any(marker in text for marker in ("전에는 끝", "전에는 마", "전까지 끝", "전까지 마", "이전 종료")):
        value = _first_time(text)
        if value is None:
            return None
        hour, minute = value.split(":", 1)
        if ("오후" in text or "저녁" in text) and 1 <= int(hour) <= 7:
            return f"{int(hour) + 12:02d}:{minute}"
        return value
    if not any(marker in text for marker in ("전에는 끝", "전에 끝", "까지 끝", "이전 종료", "전에 마치")):
        return None
    value = _first_time(text)
    if value is None:
        return None
    hour, minute = value.split(":", 1)
    if 1 <= int(hour) <= 7:
        return f"{int(hour) + 12:02d}:{minute}"
    return value


def _first_time(text: str) -> str | None:
    colon = re.search(r"(?<!\d)([01]?\d|2[0-3]):([0-5]\d)", text)
    if colon is not None:
        return f"{int(colon.group(1)):02d}:{int(colon.group(2)):02d}"
    korean_actual = re.search(r"(?<!\d)([01]?\d|2[0-3])\s*시(?:\s*([0-5]?\d)\s*분)?", text)
    if korean_actual is not None:
        hour = int(korean_actual.group(1))
        minute = int(korean_actual.group(2) or "0")
        return f"{hour:02d}:{minute:02d}"
    korean = re.search(r"(?<!\d)([01]?\d|2[0-3])\s*시(?:\s*([0-5]?\d)\s*분)?", text)
    if korean is None:
        return None
    hour = int(korean.group(1))
    minute = int(korean.group(2) or "0")
    return f"{hour:02d}:{minute:02d}"


def _extract_course_mentions(text: str) -> list[CourseMention]:
    known_names = ("자료구조", "컴퓨터프로그래밍", "고급영어", "대학영어", "알고리즘", "존재하지 않는 과목")
    mentions: list[CourseMention] = []
    for name in known_names:
        index = text.find(name)
        if index < 0:
            continue
        window = text[index:index + 32]
        prefix = text[max(0, index - 8):index]
        source = _source_fragment(text, index)
        intent_text = source
        catalog_hint = "major" if "전공" in prefix else "elective" if "교양" in prefix else None
        if any(marker in intent_text for marker in ("말고", "대신", "빼", "제외")):
            intent: CourseIntent = "excluded"
        elif any(marker in intent_text for marker in ("피하고 싶", "싫", "비선호")):
            intent = "disliked"
        elif any(marker in intent_text for marker in ("선호", "좋", "듣고 싶")) and "꼭" not in intent_text and "반드시" not in intent_text:
            intent = "preferred"
        else:
            intent = "required"
        mentions.append(CourseMention(name=name, intent=intent, source_text=source, catalog_hint=catalog_hint))

    # Handle "A 대신 B" / "A 말고 B" by requiring the course after the marker.
    for marker in ("대신", "말고"):
        if marker not in text:
            continue
        before, after = text.split(marker, 1)
        before_name = _last_known_name(before, known_names)
        after_name = _first_known_name(after, known_names)
        if before_name:
            mentions = _replace_intent(mentions, before_name, "excluded", before_name + " " + marker)
        if after_name:
            mentions = _replace_intent(mentions, after_name, "required", marker + " " + after_name)

    mentions.extend(_extract_korean_course_mentions(text))
    return _dedupe_mentions(mentions)


def _extract_korean_course_mentions(text: str) -> list[CourseMention]:
    mentions: list[CourseMention] = []
    patterns: tuple[tuple[CourseIntent, str], ...] = (
        ("excluded", r"([\uac00-\ud7a3A-Za-z0-9][\uac00-\ud7a3A-Za-z0-9\s]{1,30}?)(?:\uc740|\ub294|\uc744|\ub97c|\ub3c4)?\s*(?:\ube7c\uc918|\uc81c\uc678\ud574|\ub123\uc9c0\s*\ub9c8|\ub4e3\uc9c0\s*\uc54a)"),
        ("disliked", r"([\uac00-\ud7a3A-Za-z0-9][\uac00-\ud7a3A-Za-z0-9\s]{1,30}?)(?:\uc740|\ub294|\uc744|\ub97c|\ub3c4)?\s*(?:\ube44\uc120\ud638|\uc2eb\uc5b4|\ud53c\ud558\uace0\s*\uc2f6)"),
        ("required", r"([\uac00-\ud7a3A-Za-z0-9][\uac00-\ud7a3A-Za-z0-9\s]{1,30}?)(?:\uc740|\ub294|\uc744|\ub97c|\ub3c4)?\s*(?:\uaf2d|\ubc18\ub4dc\uc2dc|\ud544\uc218|\ubb34\uc870\uac74).{0,8}(?:\ub4e3|\ub123)"),
        ("preferred", r"([\uac00-\ud7a3A-Za-z0-9][\uac00-\ud7a3A-Za-z0-9\s]{1,30}?)(?:\uc740|\ub294|\uc744|\ub97c|\ub3c4)?\s*(?:\uc120\ud638|\ub4e3\uace0\s*\uc2f6|\ub123\uc5b4\s*\uc918|\uc6b0\uc120)"),
    )
    generic = {"수업", "시간표", "조건", "과목", "교양", "전공", "연강", "강의", "외국어", "외국어 강의"}
    clauses = [
        clause.strip()
        for clause in re.split(r"(?:\ud558\uc9c0\ub9cc|\ud558\uace0|(?<=\S)\uace0\s+|\uadf8\ub9ac\uace0|,|\.|\uc774\uc5b4\uc11c)", text)
        if clause.strip()
    ]
    for clause in clauses:
        for intent, pattern in patterns:
            for match in re.finditer(pattern, clause):
                name = match.group(1).strip()
                name = re.sub(r"^(?:\uac00\ub2a5\ud558\uba74|\ub418\ub3c4\ub85d|\uadf8\ub9ac\uace0|\ub610|\uc774\uc5b4\uc11c)\s+", "", name).strip()
                name = re.sub(r"(?:\uc740|\ub294|\uc744|\ub97c|\ub3c4)$", "", name).strip()
                name = re.sub(r"(?:\uaf2d|\ubc18\ub4dc\uc2dc|\ud544\uc218|\ubb34\uc870\uac74)$", "", name).strip()
                name = re.sub(r"(?:\uc740|\ub294|\uc744|\ub97c|\ub3c4)$", "", name).strip()
                if name in generic or len(name) < 2:
                    continue
                source = match.group(0).strip()
                prefix = text[max(0, text.find(clause) - 8):text.find(clause)]
                catalog_hint = "major" if "전공" in prefix else "elective" if "교양" in prefix else None
                mentions.append(
                    CourseMention(
                        name=name,
                        intent=intent,
                        source_text=source,
                        catalog_hint=catalog_hint,
                    )
                )
    return _dedupe_mentions(mentions)

def _missing_search_calls(
    mentions: list[CourseMention],
    current: dict[str, Any],
    search_results: dict[tuple[str, str], dict[str, Any]],
) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for mention in mentions:
        for catalog_id in _catalog_ids_for_mention(current, mention):
            key = (catalog_id, mention.name)
            if key not in search_results and key not in seen:
                seen.add(key)
                calls.append({
                    "name": "search_courses_by_name",
                    "arguments": {"catalog_id": catalog_id, "query": mention.name},
                })
    return calls


def _resolve_course_mentions(
    mentions: list[CourseMention],
    current: dict[str, Any],
    search_results: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, Any]:
    course_ids: dict[str, list[str]] = {
        "required": [],
        "excluded": [],
        "preferred": [],
        "disliked": [],
    }
    unresolved: list[dict[str, Any]] = []
    for mention in mentions:
        results = [
            search_results[(catalog_id, mention.name)]
            for catalog_id in _catalog_ids_for_mention(current, mention)
            if (catalog_id, mention.name) in search_results
        ]
        exact = [
            (result, result["candidates"][0])
            for result in results
            if result.get("resolution") == "EXACT" and len(result.get("candidates") or []) == 1
        ]
        all_candidates = [
            _candidate_payload(result, candidate)
            for result in results
            for candidate in (result.get("candidates") or [])
        ]
        if len(exact) == 1 and len(all_candidates) == 1:
            course_ids[mention.intent].append(exact[0][1]["course_id"])
            continue
        reason = (
            "검색할 catalog ID가 세션에 없습니다."
            if not results
            else "검색 결과가 없거나 여러 후보가 있어 임의로 선택하지 않았습니다."
        )
        unresolved.append({
            "source_text": mention.source_text,
            "reason": reason,
            "needed_information": "후보 중 사용할 과목을 선택해 주세요.",
            "requires_user_confirmation": True,
            "candidates": all_candidates,
        })
    return {"course_ids": course_ids, "unresolved": unresolved}


def _merge_course_ids(
    hard: dict[str, Any],
    soft: dict[str, Any],
    resolved: dict[str, list[str]],
) -> None:
    required = hard.get("required_course_ids", [])
    excluded = hard.get("excluded_course_ids", [])
    preferred = soft.get("preferred_course_ids", [])
    disliked = soft.get("disliked_course_ids", [])

    excluded = _append_many(excluded, resolved["excluded"])
    required = [course_id for course_id in required if course_id not in set(excluded)]
    required = _append_many(required, resolved["required"])
    required_set = set(required)
    excluded = [course_id for course_id in excluded if course_id not in required_set]

    preferred = _append_many(preferred, resolved["preferred"])
    disliked = _append_many(disliked, resolved["disliked"])
    hard_courses = set(required) | set(excluded)
    preferred = [course_id for course_id in preferred if course_id not in hard_courses]
    disliked = [course_id for course_id in disliked if course_id not in hard_courses]

    if required:
        hard["required_course_ids"] = required
    if excluded:
        hard["excluded_course_ids"] = excluded
    if preferred:
        soft["preferred_course_ids"] = preferred
    if disliked:
        soft["disliked_course_ids"] = disliked


def _catalog_ids_for_mention(current: dict[str, Any], mention: CourseMention) -> list[str]:
    major = current.get("major_catalog_id")
    elective = current.get("elective_catalog_id")
    if mention.catalog_hint == "major":
        return [major] if major else []
    if mention.catalog_hint == "elective":
        return [elective] if elective else []
    return [catalog_id for catalog_id in (major, elective) if catalog_id]


def _search_results_by_key(transcript: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    results: dict[tuple[str, str], dict[str, Any]] = {}
    for message in transcript:
        if message.get("name") != "search_courses_by_name":
            continue
        content = message.get("content") or {}
        request = content.get("request") or {}
        catalog_id = content.get("catalog_id") or request.get("catalog_id")
        query = request.get("query")
        if isinstance(request, dict) and isinstance(query, dict):
            query = query.get("query")
        if catalog_id and query:
            results[(str(catalog_id), str(query))] = content
    return results


def _candidate_payload(result: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    catalog_id = result.get("catalog_id")
    return {
        "catalog_id": catalog_id,
        "catalog_type": _catalog_type(str(catalog_id or "")),
        "course_id": candidate.get("course_id"),
        "course_name": candidate.get("course_name"),
        "matching_section_ids": candidate.get("matching_section_ids") or [],
        "resolution": result.get("resolution"),
    }


def _current_hard(current: dict[str, Any]) -> dict[str, Any]:
    hard = current.get("hard_constraints") or {}
    return {
        "required_free_days": list(hard.get("required_free_days") or []),
        "earliest_start_time": hard.get("earliest_start_time"),
        "latest_end_time": hard.get("latest_end_time"),
        "min_credit": hard.get("min_credit"),
        "min_credit_inclusive": hard.get("min_credit_inclusive"),
        "max_credit": hard.get("max_credit"),
        "max_credit_inclusive": hard.get("max_credit_inclusive"),
        "required_course_ids": list(hard.get("required_course_ids") or []),
        "excluded_course_ids": list(hard.get("excluded_course_ids") or []),
    }


def _current_soft(current: dict[str, Any]) -> dict[str, Any]:
    soft = current.get("soft_preferences") or {}
    return {
        "preferred_free_days": list(soft.get("preferred_free_days") or []),
        "preferred_earliest_start_time": soft.get("preferred_earliest_start_time"),
        "preferred_latest_end_time": soft.get("preferred_latest_end_time"),
        "preferred_course_ids": list(soft.get("preferred_course_ids") or []),
        "disliked_course_ids": list(soft.get("disliked_course_ids") or []),
        "compact_schedule": soft.get("compact_schedule"),
    }


def _drop_empty(values: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value for key, value in values.items()
        if value not in (None, [], "")
    }


def _append_unique(values: list[str], value: str) -> list[str]:
    return list(dict.fromkeys([*values, value]))


def _append_many(values: list[str], additions: list[str]) -> list[str]:
    return list(dict.fromkeys([*values, *additions]))


def _source_fragment(text: str, index: int) -> str:
    end = len(text)
    for separator in (".", ",", " 그리고 ", " 하지만 ", "하지만", "하고 "):
        found = text.find(separator, index)
        if found >= 0:
            end = min(end, found + len(separator))
    return text[index:end].strip(" .,\n\t") or text[index:].strip()


def _replace_intent(
    mentions: list[CourseMention],
    name: str,
    intent: CourseIntent,
    source_text: str,
) -> list[CourseMention]:
    replaced = False
    result: list[CourseMention] = []
    for mention in mentions:
        if mention.name == name:
            result.append(mention.model_copy(update={"intent": intent, "source_text": source_text}))
            replaced = True
        else:
            result.append(mention)
    if not replaced:
        result.append(CourseMention(name=name, intent=intent, source_text=source_text))
    return result


def _dedupe_mentions(mentions: list[CourseMention]) -> list[CourseMention]:
    deduped: dict[tuple[str, str], CourseMention] = {}
    for mention in mentions:
        deduped[(mention.name, mention.intent)] = mention
    return list(deduped.values())


def _first_known_name(text: str, names: tuple[str, ...]) -> str | None:
    found = [(text.find(name), name) for name in names if name in text]
    return min(found)[1] if found else None


def _last_known_name(text: str, names: tuple[str, ...]) -> str | None:
    found = [(text.rfind(name), name) for name in names if name in text]
    return max(found)[1] if found else None


def _catalog_type(catalog_id: str) -> str:
    if catalog_id.endswith(":major"):
        return "major"
    if catalog_id.endswith(":elective"):
        return "elective"
    if catalog_id.endswith(":general"):
        return "general"
    return "unknown"


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
