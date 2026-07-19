"""Match LLM-selected major course references to parsed catalog courses."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Iterable

from ..models.course import Course
from ..models.major_selection import (
    AmbiguousMajorCourse,
    MajorCourseMatchResult,
    MajorCourseReference,
    MajorSelectionParseResult,
    MatchedMajorCourse,
    UnmatchedMajorCourse,
)


_SECTION_SUFFIX_RE = re.compile(r"\s*분반\s*$")
INVALID_ZERO_SECTION_REASON = "000분반은 유효한 분반이 아닙니다."


def normalize_course_name(value: str) -> str:
    """Normalize course names for exact matching only.

    All whitespace is removed and English letters are compared
    case-insensitively. No substring or fuzzy matching is performed.
    """

    return re.sub(r"\s+", "", value).casefold()


def normalize_section(value: str | None) -> str | None:
    """Normalize section text to safely compare against catalog divisions.

    Current catalog sections are numeric strings such as ``001``. Numeric input
    like ``1``, ``01``, ``001`` and ``001분반`` is compared by numeric value,
    while non-numeric sections fall back to trimmed case-insensitive text.
    """

    if value is None:
        return None
    text = _SECTION_SUFFIX_RE.sub("", value.strip())
    text = re.sub(r"\s+", "", text)
    if not text:
        return None
    if text.isdigit():
        return str(int(text))
    return text.casefold()


class MajorCourseMatcher:
    """Resolve selected major course references to existing ``Course`` objects.

    Service contract: callers pass only major courses parsed from the major
    course catalog. This matcher intentionally does not filter by category.
    """

    def __init__(self, courses: Iterable[Course]) -> None:
        self._by_name: dict[str, list[Course]] = defaultdict(list)
        for course in courses:
            self._by_name[normalize_course_name(course.course_name)].append(course)

    def match(self, parse_result: MajorSelectionParseResult) -> MajorCourseMatchResult:
        matched: list[MatchedMajorCourse] = []
        ambiguous: list[AmbiguousMajorCourse] = []
        unmatched: list[UnmatchedMajorCourse] = []
        matched_course_ids: set[str] = set()

        for reference in parse_result.selected_courses:
            candidates = list(self._by_name.get(normalize_course_name(reference.course_name), []))
            section = normalize_section(reference.section)

            if section == "0":
                unmatched.append(
                    UnmatchedMajorCourse(
                        reference=reference,
                        reason=INVALID_ZERO_SECTION_REASON,
                    )
                )
                continue

            if not candidates:
                unmatched.append(
                    UnmatchedMajorCourse(
                        reference=reference,
                        reason="수강편람에서 같은 과목명을 찾지 못했습니다.",
                    )
                )
                continue

            if section is None:
                ambiguous.append(
                    AmbiguousMajorCourse(
                        reference=reference,
                        candidates=candidates,
                        reason="분반이 없어 자동 선택할 수 없습니다.",
                    )
                )
                continue

            section_matches = [
                course for course in candidates if normalize_section(course.division) == section
            ]
            if len(section_matches) == 1:
                course = section_matches[0]
                if course.course_id not in matched_course_ids:
                    matched.append(MatchedMajorCourse(reference=reference, course=course))
                    matched_course_ids.add(course.course_id)
            elif len(section_matches) > 1:
                ambiguous.append(
                    AmbiguousMajorCourse(
                        reference=reference,
                        candidates=section_matches,
                        reason="같은 과목명과 분반에 해당하는 과목이 여러 개입니다.",
                    )
                )
            else:
                unmatched.append(
                    UnmatchedMajorCourse(
                        reference=reference,
                        reason="수강편람에서 같은 과목명과 분반을 찾지 못했습니다.",
                    )
                )

        return MajorCourseMatchResult(
            matched=matched,
            ambiguous=ambiguous,
            unmatched=unmatched,
            ambiguous_texts=list(parse_result.ambiguous_texts),
        )
