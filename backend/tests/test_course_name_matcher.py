"""Regression tests for tolerant course-name matching."""

from backend.app.services.course_name_matcher import (
    course_name_aliases,
    course_name_matches,
    normalize_course_name,
)


def test_normalize_course_name_ignores_spacing_punctuation_and_roman_suffix() -> None:
    assert normalize_course_name("수사학  (I)") == normalize_course_name("수사학")
    assert normalize_course_name("일반물리학(I)") == normalize_course_name("일반물리학")


def test_course_name_matches_clear_abbreviation_alias() -> None:
    assert "컴프입" in course_name_aliases("컴퓨터및프로그래밍입문")
    assert course_name_matches("컴프입", "컴퓨터및프로그래밍입문")


def test_course_name_matching_does_not_treat_unrelated_short_text_as_match() -> None:
    assert not course_name_matches("컴입", "컴퓨터및프로그래밍입문")
