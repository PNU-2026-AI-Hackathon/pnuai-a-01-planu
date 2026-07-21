"""Opt-in live LLM tests for general preference parsing."""

from __future__ import annotations

import pytest

from backend.app.core.errors import AppError
from backend.app.models import Day
from backend.app.services.general_preference_parser import GeneralPreferenceParser


pytestmark = pytest.mark.live_llm


def _parser(timeout_seconds: int) -> GeneralPreferenceParser:
    return GeneralPreferenceParser(timeout_seconds=timeout_seconds)


def _parse(prompt: str, trace_call, live_llm_config, case_name: str):
    parser = _parser(live_llm_config.timeout_seconds)
    return trace_call(case_name, "general_preference", lambda: parser.parse(prompt))


def _unsupported_text(result) -> str:
    return " ".join(item.source_text for item in result.unsupported_conditions)


def test_general_smoke_soft_friday_live(trace_call, live_llm_config) -> None:
    result = _parse("금요일은 가능하면 쉬고 싶어", trace_call, live_llm_config, "general_smoke")

    assert Day.FRI in result.soft_conditions.preferred_free_days
    assert Day.FRI not in result.hard_conditions.excluded_days
    assert result.hard_conditions.earliest_start_time is None
    assert result.unsupported_conditions == []


def test_general_hard_conditions_live(trace_call, live_llm_config) -> None:
    result = _parse(
        "금요일 수업은 절대 넣지 말고 10시 이전 수업도 하나도 넣지 마.",
        trace_call,
        live_llm_config,
        "general_hard_conditions",
    )

    assert Day.FRI in result.hard_conditions.excluded_days
    assert result.hard_conditions.earliest_start_time == "10:00"
    assert Day.FRI not in result.soft_conditions.preferred_free_days
    assert result.soft_conditions.preferred_first_class_time is None


def test_general_soft_conditions_live(trace_call, live_llm_config) -> None:
    result = _parse(
        "금요일은 가능하면 쉬고 싶고 오전 수업은 피하고 싶어.",
        trace_call,
        live_llm_config,
        "general_soft_conditions",
    )

    assert Day.FRI in result.soft_conditions.preferred_free_days
    assert result.soft_conditions.preferred_first_class_time == "10:00"
    assert Day.FRI not in result.hard_conditions.excluded_days
    assert result.hard_conditions.earliest_start_time is None


def test_general_hard_soft_strength_comparison_live(trace_call, live_llm_config) -> None:
    hard = _parse("금요일 수업은 절대 안 돼.", trace_call, live_llm_config, "general_hard_friday")
    soft = _parse("금요일은 가능하면 쉬고 싶어.", trace_call, live_llm_config, "general_soft_friday")

    assert Day.FRI in hard.hard_conditions.excluded_days
    assert Day.FRI not in hard.soft_conditions.preferred_free_days
    assert Day.FRI in soft.soft_conditions.preferred_free_days
    assert Day.FRI not in soft.hard_conditions.excluded_days


def test_general_ambiguous_morning_stays_soft_live(trace_call, live_llm_config) -> None:
    result = _parse("오전 수업은 싫어.", trace_call, live_llm_config, "general_ambiguous_morning")

    assert result.hard_conditions.earliest_start_time is None
    assert result.soft_conditions.preferred_first_class_time == "10:00"


def test_general_hard_and_soft_course_names_live(trace_call, live_llm_config) -> None:
    hard = _parse(
        "고전읽기와토론은 꼭 듣고 싶고 경제학원론은 절대 넣지 마.",
        trace_call,
        live_llm_config,
        "general_hard_courses",
    )
    soft = _parse(
        "고전읽기와토론을 우선하고 싶고 경제학원론은 가능하면 피하고 싶어.",
        trace_call,
        live_llm_config,
        "general_soft_courses",
    )

    assert hard.hard_conditions.required_course_names == ["고전읽기와토론"]
    assert hard.hard_conditions.excluded_course_names == ["경제학원론"]
    assert hard.soft_conditions.preferred_course_names == []
    assert hard.soft_conditions.avoided_course_names == []
    assert soft.soft_conditions.preferred_course_names == ["고전읽기와토론"]
    assert soft.soft_conditions.avoided_course_names == ["경제학원론"]
    assert soft.hard_conditions.required_course_names == []
    assert soft.hard_conditions.excluded_course_names == []


@pytest.mark.parametrize(
    ("case_name", "prompt", "expected_source"),
    [
        (
            "general_unsupported_workload",
            "금요일은 가능하면 쉬고 싶고 과제가 적고 발표 없는 수업을 듣고 싶어.",
            ["과제", "발표"],
        ),
        (
            "general_unsupported_professor_rating",
            "에브리타임 평점이 높은 교수님 수업을 우선해 줘.",
            ["평점"],
        ),
    ],
)
def test_general_unsupported_conditions_live(
    trace_call,
    live_llm_config,
    case_name: str,
    prompt: str,
    expected_source: list[str],
) -> None:
    result = _parse(prompt, trace_call, live_llm_config, case_name)

    text = _unsupported_text(result)
    for expected in expected_source:
        assert expected in text
    assert result.hard_conditions.excluded_professors == []
    assert result.soft_conditions.preferred_course_names == []
    if "금요일" in prompt:
        assert Day.FRI in result.soft_conditions.preferred_free_days


@pytest.mark.parametrize(
    ("case_name", "prompt", "hard_time", "soft_time"),
    [
        ("general_time_10_hard", "오전 10시 이전 수업은 절대 안 돼.", "10:00", None),
        ("general_time_18_hard", "오후 6시 이후 수업은 넣지 마.", None, None),
        ("general_time_11_soft", "첫 수업은 가능하면 11시 이후였으면 좋겠어.", None, "11:00"),
    ],
)
def test_general_time_expressions_live(
    trace_call,
    live_llm_config,
    case_name: str,
    prompt: str,
    hard_time: str | None,
    soft_time: str | None,
) -> None:
    result = _parse(prompt, trace_call, live_llm_config, case_name)

    if hard_time:
        assert result.hard_conditions.earliest_start_time == hard_time
    if case_name == "general_time_18_hard":
        assert result.hard_conditions.latest_end_time == "18:00"
    assert result.soft_conditions.preferred_first_class_time == soft_time


@pytest.mark.parametrize(
    ("case_name", "prompt", "hard_days", "soft_days"),
    [
        ("general_days_hard", "월수금에는 수업을 넣지 마.", {Day.MON, Day.WED, Day.FRI}, set()),
        ("general_days_soft", "화요일이랑 목요일은 가능하면 쉬고 싶어.", set(), {Day.TUE, Day.THU}),
    ],
)
def test_general_day_expressions_live(
    trace_call,
    live_llm_config,
    case_name: str,
    prompt: str,
    hard_days: set[Day],
    soft_days: set[Day],
) -> None:
    result = _parse(prompt, trace_call, live_llm_config, case_name)

    assert set(result.hard_conditions.excluded_days) == hard_days
    assert set(result.soft_conditions.preferred_free_days) == soft_days


def test_general_complex_input_live(trace_call, live_llm_config) -> None:
    result = _parse(
        "금요일은 절대 수업을 넣지 말고, 오전 수업은 가능하면 피하고 싶어.\n"
        "고전읽기와토론은 꼭 듣고 싶고 경제학원론은 별로 듣고 싶지 않아.\n"
        "그리고 발표 없는 수업이면 좋겠어.",
        trace_call,
        live_llm_config,
        "general_complex",
    )

    assert Day.FRI in result.hard_conditions.excluded_days
    assert result.soft_conditions.preferred_first_class_time == "10:00"
    assert result.hard_conditions.required_course_names == ["고전읽기와토론"]
    assert result.soft_conditions.avoided_course_names == ["경제학원론"]
    assert "발표" in _unsupported_text(result)


def test_general_conflicts_are_visible_live(trace_call, live_llm_config) -> None:
    result = _parse(
        "금요일은 절대 수업을 넣지 말고 금요일 수업을 가장 선호해.",
        trace_call,
        live_llm_config,
        "general_day_conflict",
    )

    assert Day.FRI in result.hard_conditions.excluded_days
    assert any(
        warning.code in {"CONFLICTING_CONDITIONS", "HARD_SOFT_DUPLICATE_REMOVED"}
        for warning in result.warnings
    )

    with pytest.raises(AppError) as exc_info:
        _parse(
            "고전읽기와토론은 반드시 넣고 절대 넣지 마.",
            trace_call,
            live_llm_config,
            "general_course_conflict",
        )
    assert exc_info.value.code == "CONFLICTING_PREFERENCE_CONDITIONS"


def test_general_no_hallucinated_conditions_live(trace_call, live_llm_config) -> None:
    result = _parse(
        "고전읽기와토론을 듣고 싶어.",
        trace_call,
        live_llm_config,
        "general_no_hallucination",
    )

    assert result.soft_conditions.preferred_course_names == ["고전읽기와토론"]
    assert result.hard_conditions.excluded_days == []
    assert result.soft_conditions.preferred_free_days == []
    assert result.soft_conditions.preferred_first_class_time is None
    assert result.soft_conditions.minimize_attendance_days is False
    assert result.soft_conditions.minimize_consecutive_classes is False
    assert result.soft_conditions.compact_schedule is False


def test_general_repeated_input_stability_live(trace_call, live_llm_config) -> None:
    results = [
        _parse(
            "금요일은 가능하면 쉬고 싶고 오전 수업은 절대 안 돼.",
            trace_call,
            live_llm_config,
            f"general_repeated_stability_{index}",
        )
        for index in range(3)
    ]

    for result in results:
        assert Day.FRI in result.soft_conditions.preferred_free_days
        assert result.hard_conditions.earliest_start_time == "10:00"
        assert result.hard_conditions.excluded_days == []
        assert result.unsupported_conditions == []
