"""Tests for matching LLM-selected major courses to catalog courses."""

import pytest

from backend.app.models import (
    AmbiguousMajorCourse,
    Category,
    ClassTime,
    Course,
    Day,
    MajorCourseMatchResult,
    MajorCourseReference,
    MajorSelectionParseResult,
    MatchedMajorCourse,
    UnmatchedMajorCourse,
)
from backend.app.services.major_course_matcher import MajorCourseMatcher, normalize_section


@pytest.fixture
def catalog_courses() -> list[Course]:
    def course(course_id: str, name: str, division: str, start: str) -> Course:
        return Course(
            course_id=course_id,
            course_name=name,
            category=Category.MAJOR_REQUIRED,
            credit=3,
            division=division,
            professor="김교수",
            class_times=[
                ClassTime(
                    day=Day.MON,
                    start=start,
                    end="10:15",
                    classroom="제6공학관 6201",
                    building_code="6201",
                )
            ],
        )

    return [
        course("MA100-001", "자료구조", "001", "09:00"),
        course("MA100-002", "자료구조", "002", "09:00"),
        course("MA200-001", "운영체제", "001", "09:00"),
    ]


@pytest.mark.parametrize("raw", ["1", "01", "001", "001분반", " 001 분반 "])
def test_normalize_section_matches_catalog_numeric_sections(raw: str) -> None:
    assert normalize_section(raw) == normalize_section("001")


def test_match_returns_existing_catalog_course_object(catalog_courses: list[Course]) -> None:
    result = MajorCourseMatcher(catalog_courses).match(
        MajorSelectionParseResult(
            selected_courses=[
                MajorCourseReference(course_name="자료구조", section="001분반")
            ]
        )
    )

    assert len(result.matched) == 1
    assert result.matched[0].course is catalog_courses[0]
    assert result.ambiguous == []
    assert result.unmatched == []


def test_missing_section_is_ambiguous_even_with_single_candidate(
    catalog_courses: list[Course],
) -> None:
    result = MajorCourseMatcher(catalog_courses).match(
        MajorSelectionParseResult(
            selected_courses=[MajorCourseReference(course_name="운영체제")]
        )
    )

    assert result.matched == []
    assert result.unmatched == []
    assert len(result.ambiguous) == 1
    assert result.ambiguous[0].candidates == [catalog_courses[2]]


def test_multiple_catalog_matches_are_ambiguous(catalog_courses: list[Course]) -> None:
    duplicate = catalog_courses[0].model_copy(update={"course_id": "MA999-001"})

    result = MajorCourseMatcher([*catalog_courses, duplicate]).match(
        MajorSelectionParseResult(
            selected_courses=[MajorCourseReference(course_name="자료구조", section="1")]
        )
    )

    assert result.matched == []
    assert result.unmatched == []
    assert {course.course_id for course in result.ambiguous[0].candidates} == {
        "MA100-001",
        "MA999-001",
    }


def test_no_catalog_match_is_unmatched(catalog_courses: list[Course]) -> None:
    result = MajorCourseMatcher(catalog_courses).match(
        MajorSelectionParseResult(
            selected_courses=[MajorCourseReference(course_name="컴파일러", section="001")]
        )
    )

    assert result.matched == []
    assert result.ambiguous == []
    assert len(result.unmatched) == 1


def test_result_models_are_importable_from_domain_package() -> None:
    assert MatchedMajorCourse
    assert AmbiguousMajorCourse
    assert UnmatchedMajorCourse
    assert MajorCourseMatchResult
