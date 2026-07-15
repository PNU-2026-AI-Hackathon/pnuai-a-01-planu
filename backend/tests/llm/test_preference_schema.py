"""Unit tests for PreferenceRules schema and normalization policies."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.app.models import PreferenceRules


def test_valid_structured_preferences_pass_schema() -> None:
    rules = PreferenceRules(
        required_course_names=["대학영어"],
        preferred_course_names=["컴퓨팅사고와인공지능"],
        excluded_course_names=["고전읽기와토론"],
        avoided_course_names=["철학의기초"],
        preferred_elective_areas=[4],
        earliest_start_time="10:00",
    )

    assert rules.required_course_names == ["대학영어"]
    assert rules.preferred_course_names == ["컴퓨팅사고와인공지능"]
    assert rules.excluded_course_names == ["고전읽기와토론"]
    assert rules.avoided_course_names == ["철학의기초"]
    assert rules.preferred_elective_areas == [4]
    assert rules.earliest_start_time == "10:00"


@pytest.mark.parametrize("area", [0, 8])
def test_invalid_elective_area_is_rejected(area: int) -> None:
    with pytest.raises(ValidationError, match="elective areas"):
        PreferenceRules(preferred_elective_areas=[area])


@pytest.mark.parametrize("time_value", ["9:00", "24:00", "10:60", "오전 10시"])
def test_invalid_earliest_start_time_is_rejected(time_value: str) -> None:
    with pytest.raises(ValidationError):
        PreferenceRules(earliest_start_time=time_value)


def test_duplicate_array_values_are_deduplicated() -> None:
    rules = PreferenceRules(
        required_course_names=["대학영어", "대학영어"],
        preferred_course_names=["컴퓨팅사고와인공지능", "컴퓨팅사고와인공지능"],
        excluded_course_names=["고전읽기와토론", "고전읽기와토론"],
        avoided_course_names=["철학의기초", "철학의기초"],
        preferred_elective_areas=[4, 4, 6],
    )

    assert rules.required_course_names == ["대학영어"]
    assert rules.preferred_course_names == ["컴퓨팅사고와인공지능"]
    assert rules.excluded_course_names == ["고전읽기와토론"]
    assert rules.avoided_course_names == ["철학의기초"]
    assert rules.preferred_elective_areas == [4, 6]


def test_unknown_fields_are_rejected() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        PreferenceRules(disliked_course_names=["철학의기초"])


def test_defaults_are_empty_arrays_or_none() -> None:
    rules = PreferenceRules()

    assert rules.required_course_names == []
    assert rules.preferred_course_names == []
    assert rules.excluded_course_names == []
    assert rules.avoided_course_names == []
    assert rules.preferred_elective_areas == []
    assert rules.earliest_start_time is None


def test_required_and_preferred_course_fields_remain_independent() -> None:
    rules = PreferenceRules(
        required_course_names=["대학영어"],
        preferred_course_names=["컴퓨팅사고와인공지능"],
    )

    assert rules.required_course_names == ["대학영어"]
    assert rules.preferred_course_names == ["컴퓨팅사고와인공지능"]


def test_excluded_and_avoided_course_fields_remain_independent() -> None:
    rules = PreferenceRules(
        excluded_course_names=["고전읽기와토론"],
        avoided_course_names=["철학의기초"],
    )

    assert rules.excluded_course_names == ["고전읽기와토론"]
    assert rules.avoided_course_names == ["철학의기초"]
