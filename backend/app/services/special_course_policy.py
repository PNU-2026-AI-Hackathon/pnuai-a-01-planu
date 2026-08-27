"""Shared policy for courses whose eligibility cannot be inferred locally."""

from __future__ import annotations

from typing import Any


ENGLISH_PLACEMENT_COURSE_NAMES = frozenset({"대학영어", "고급영어"})
ENGLISH_PLACEMENT_COURSE_CODES = frozenset({"ZE1000113"})
ENGLISH_PLACEMENT_NOTICE = (
    "대학영어/고급영어는 수능 성적 등 개인 자격 조건에 따라 신청 가능 여부가 "
    "달라질 수 있습니다. 학교 홈페이지의 수강 안내를 확인해 주세요."
)
ENGLISH_PLACEMENT_NOTICE_CODE = "ENGLISH_PLACEMENT_ELIGIBILITY"


def normalize_course_code(value: str | None) -> str:
    text = (value or "").strip()
    return text.rsplit("-", 1)[0] if "-" in text else text


def is_english_placement_course(course: Any) -> bool:
    course_name = getattr(course, "course_name", None)
    course_code = getattr(course, "course_code", None)
    course_id = getattr(course, "course_id", None)
    return is_english_placement_ref(
        course_id=course_id,
        course_name=course_name,
        course_code=course_code,
    )


def is_english_placement_ref(
    *,
    course_id: str | None = None,
    course_name: str | None = None,
    course_code: str | None = None,
) -> bool:
    if (course_name or "").strip() in ENGLISH_PLACEMENT_COURSE_NAMES:
        return True
    return normalize_course_code(course_code or course_id) in ENGLISH_PLACEMENT_COURSE_CODES
