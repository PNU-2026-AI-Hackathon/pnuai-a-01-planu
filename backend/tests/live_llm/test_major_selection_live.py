"""Opt-in live LLM tests for major-selection parsing."""

from __future__ import annotations

import pytest

from backend.app.services.major_selection_parser import MajorSelectionParser


pytestmark = pytest.mark.live_llm


def _course_map(result) -> dict[str, str | None]:
    return {course.course_name: course.section for course in result.selected_courses}


def assert_courses(result, expected: dict[str, str | None]) -> None:
    actual = _course_map(result)
    assert actual == expected
    assert len(result.selected_courses) == len(expected)


def test_major_basic_extraction_live(
    live_major_parser: MajorSelectionParser,
    trace_call,
) -> None:
    result = trace_call(
        "major_basic_extraction",
        "major_selection",
        lambda: live_major_parser.parse("자료구조 001분반이랑 컴퓨터구조 003분반을 들을 거야."),
    )

    assert_courses(result, {"자료구조": "1", "컴퓨터구조": "3"})
    assert result.ambiguous_texts == []


@pytest.mark.parametrize(
    "prompt",
    [
        "자료구조 1분반이랑 컴퓨터구조 3분반",
        "자료구조 001, 컴퓨터구조 003으로 신청할게",
        "자료구조는 001분반, 컴퓨터구조는 003분반이야",
    ],
)
def test_major_section_spellings_live(
    live_major_parser: MajorSelectionParser,
    trace_call,
    prompt: str,
) -> None:
    result = trace_call(
        "major_section_spellings",
        "major_selection",
        lambda: live_major_parser.parse(prompt),
    )

    assert_courses(result, {"자료구조": "1", "컴퓨터구조": "3"})


def test_major_missing_section_is_not_guessed_live(
    live_major_parser: MajorSelectionParser,
    trace_call,
) -> None:
    result = trace_call(
        "major_missing_section",
        "major_selection",
        lambda: live_major_parser.parse("자료구조랑 컴퓨터구조를 들을 거야."),
    )

    assert_courses(result, {"자료구조": None, "컴퓨터구조": None})


@pytest.mark.parametrize(
    ("case_name", "prompt"),
    [
        ("major_no_recommendations", "자료구조를 듣고 싶은데 같이 들으면 좋은 전공 과목도 골라 줘."),
        ("major_professor_noise", "김교수님의 자료구조 001분반과 이교수님의 컴퓨터구조 003분반을 들을 거야."),
        (
            "major_natural_noise",
            "에브리타임에서 찾아봤는데 일단 자료구조는 001분반으로 하고, 컴퓨터구조는 친구랑 같이 들으려고 003분반으로 정했어.",
        ),
    ],
)
def test_major_boundaries_live(
    live_major_parser: MajorSelectionParser,
    trace_call,
    case_name: str,
    prompt: str,
) -> None:
    result = trace_call(
        case_name,
        "major_selection",
        lambda: live_major_parser.parse(prompt),
    )

    if case_name == "major_no_recommendations":
        assert_courses(result, {"자료구조": None})
    else:
        assert_courses(result, {"자료구조": "1", "컴퓨터구조": "3"})
    assert all("교수" not in course.course_name for course in result.selected_courses)
