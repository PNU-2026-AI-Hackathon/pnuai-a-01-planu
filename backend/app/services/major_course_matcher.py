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


def normalize_course_name(value: str) -> str:
    """Normalize spacing without changing the literal course name."""

    return re.sub(r"\s+", " ", value.strip())


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
    """Resolve selected major course references to existing ``Course`` objects."""

    def __init__(self, courses: Iterable[Course]) -> None:
        self._by_name: dict[str, list[Course]] = defaultdict(list)
        for course in courses:
            self._by_name[normalize_course_name(course.course_name)].append(course)

    def match(self, parse_result: MajorSelectionParseResult) -> MajorCourseMatchResult:
        matched: list[MatchedMajorCourse] = []
        ambiguous: list[AmbiguousMajorCourse] = []
        unmatched: list[UnmatchedMajorCourse] = []

        for reference in parse_result.selected_courses:
            candidates = list(self._by_name.get(normalize_course_name(reference.course_name), []))
            section = normalize_section(reference.section)

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
                matched.append(MatchedMajorCourse(reference=reference, course=section_matches[0]))
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
        )
