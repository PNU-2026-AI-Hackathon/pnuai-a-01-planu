"""Utilities for matching user-stated course names to catalog course names."""

from __future__ import annotations

import re
import unicodedata


_ROMAN_NUMERAL_SUFFIX_RE = re.compile(r"\(\s*[IVXLCDM]+\s*\)", re.IGNORECASE)
_NON_WORD_RE = re.compile(r"[\s\W_]+", re.UNICODE)

_COURSE_ALIAS_WORDS = (
    "컴퓨터",
    "프로그래밍",
    "인공지능",
    "데이터",
    "소프트웨어",
    "정보",
    "통계",
    "수학",
    "물리학",
    "화학",
    "생명과학",
    "경제학",
    "심리학",
    "사회학",
    "일본어",
    "독일어",
    "러시아어",
    "프랑스어",
    "영어",
    "한문",
    "한국어",
    "회화",
    "문법",
    "연습",
    "실험",
    "실습",
    "개론",
    "원론",
    "기초",
    "입문",
    "응용",
)
_CONNECTOR_WORDS = ("및", "와", "과", "의")


def normalize_course_name(value: str) -> str:
    """Return a comparison key tolerant of spacing, punctuation, and (I)."""

    normalized = unicodedata.normalize("NFKC", value).casefold()
    normalized = _ROMAN_NUMERAL_SUFFIX_RE.sub("", normalized)
    return _NON_WORD_RE.sub("", normalized)


def course_name_aliases(value: str) -> set[str]:
    """Build conservative aliases from a catalog or user course name."""

    normalized = normalize_course_name(value)
    aliases = {normalized} if normalized else set()
    aliases.update(_word_initial_aliases(normalized))
    return aliases


def course_name_matches(user_value: str, catalog_value: str) -> bool:
    """Return whether a user preference refers to a catalog course name."""

    user_aliases = course_name_aliases(user_value)
    catalog_aliases = course_name_aliases(catalog_value)
    return bool(user_aliases & catalog_aliases)


def _word_initial_aliases(value: str) -> set[str]:
    aliases: set[str] = set()
    for words in _segment_course_words(value):
        if len(words) >= 2:
            aliases.add("".join(word[0] for word in words if word))
    return aliases


def _segment_course_words(value: str) -> list[list[str]]:
    if not value:
        return []

    segments: list[list[str]] = []
    _segment_from_index(value, 0, [], segments)
    return segments


def _segment_from_index(
    value: str,
    index: int,
    current: list[str],
    segments: list[list[str]],
) -> None:
    if index == len(value):
        segments.append(current.copy())
        return

    for connector in _CONNECTOR_WORDS:
        if value.startswith(connector, index):
            _segment_from_index(value, index + len(connector), current, segments)

    for word in _COURSE_ALIAS_WORDS:
        if value.startswith(word, index):
            current.append(word)
            _segment_from_index(value, index + len(word), current, segments)
            current.pop()
