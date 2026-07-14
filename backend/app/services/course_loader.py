"""Load the generated PlaNU course catalog JSON into backend models."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ..models.course import Category, ClassTime, Course, Day


class CourseCatalogLoadError(ValueError):
    """Raised when the generated course catalog JSON cannot be loaded safely."""


DAY_MAP = {
    "월": Day.MON,
    "화": Day.TUE,
    "수": Day.WED,
    "목": Day.THU,
    "금": Day.FRI,
    "MON": Day.MON,
    "TUE": Day.TUE,
    "WED": Day.WED,
    "THU": Day.THU,
    "FRI": Day.FRI,
}


def _building_code(classroom: str) -> str:
    match = re.search(r"(?:^|\s)([가-힣A-Za-z]*\d{3}|[가-힣A-Za-z]+M\d{2})(?=-|\s|$)", classroom)
    if match:
        return match.group(1)
    token = classroom.split("-", 1)[0].strip().split()[-1:] or ["미정"]
    return token[0] or "미정"


def _clock(value: Any) -> str:
    if not isinstance(value, str):
        raise CourseCatalogLoadError("시간 값은 문자열이어야 합니다.")
    hour_text, minute_text = value.split(":")
    return f"{int(hour_text):02d}:{int(minute_text):02d}"


def _add_minutes(value: str, minutes: int) -> str:
    hour, minute = (int(part) for part in value.split(":"))
    total = hour * 60 + minute + minutes
    if not 0 <= total < 24 * 60:
        raise CourseCatalogLoadError(f"잘못된 수업 시간입니다: {value}({minutes})")
    return f"{total // 60:02d}:{total % 60:02d}"


def _class_time_from_schedule(schedule: dict[str, Any]) -> ClassTime:
    day_value = schedule.get("day")
    if not isinstance(day_value, str) or day_value.upper() not in DAY_MAP:
        raise CourseCatalogLoadError("지원하지 않는 요일 값입니다.")

    start = _clock(schedule.get("startTime"))
    end_value = schedule.get("endTime")
    if end_value:
        end = _clock(end_value)
    else:
        duration = schedule.get("durationMinutes")
        if not isinstance(duration, int):
            raise CourseCatalogLoadError("endTime 또는 durationMinutes가 필요합니다.")
        end = _add_minutes(start, duration)

    classroom = str(schedule.get("room") or "미정").strip() or "미정"
    return ClassTime(
        day=DAY_MAP[day_value.upper()],
        start=start,
        end=end,
        classroom=classroom,
        building_code=_building_code(classroom),
    )


def _course_from_catalog_item(item: dict[str, Any]) -> Course | None:
    schedules = item.get("schedules")
    if not isinstance(schedules, list) or not schedules:
        return None

    try:
        class_times = [_class_time_from_schedule(schedule) for schedule in schedules if isinstance(schedule, dict)]
    except CourseCatalogLoadError:
        return None
    class_times = _dedupe_class_times(class_times)
    if not class_times:
        return None

    category = Category(str(item.get("category")))
    course_code = str(item.get("courseCode") or "").strip()
    section = str(item.get("section") or "").strip()
    if not course_code or not section:
        raise CourseCatalogLoadError("courseCode와 section은 필수입니다.")

    return Course(
        course_id=f"{course_code}-{section}",
        course_name=str(item.get("courseName") or "").strip(),
        category=category,
        area=item.get("area"),
        credit=float(item.get("credits")),
        division=section,
        professor=str(item.get("professor") or "미정").strip() or "미정",
        class_times=class_times,
    )


def _dedupe_class_times(class_times: list[ClassTime]) -> list[ClassTime]:
    deduped: list[ClassTime] = []
    seen: set[tuple[Day, str, str]] = set()
    for class_time in class_times:
        key = (class_time.day, class_time.start, class_time.end)
        if key in seen:
            continue
        deduped.append(class_time)
        seen.add(key)
    return deduped


def load_course_catalog(path: str | Path) -> list[dict[str, Any]]:
    """Load the generated full catalog JSON without converting its shape."""

    source = Path(path)
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CourseCatalogLoadError("course_catalog.json을 읽을 수 없습니다.") from exc
    if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
        raise CourseCatalogLoadError("course_catalog.json은 객체 배열이어야 합니다.")
    return payload


def load_courses(path: str | Path, *, category: Category | None = None) -> list[Course]:
    """Load schedulable courses from ``course_catalog.json``.

    Rows without parsed schedules are preserved in the source catalog but skipped
    here because the timetable engine can only place courses with concrete times.
    """

    courses: list[Course] = []
    seen: set[str] = set()
    for item in load_course_catalog(path):
        if category is not None and item.get("category") != category.value:
            continue
        course = _course_from_catalog_item(item)
        if course is None or course.course_id in seen:
            continue
        courses.append(course)
        seen.add(course.course_id)
    return courses


def load_default_catalogs(path: str | Path) -> dict[str, list[Course]]:
    """Return default general courses grouped for the recommendation engine."""

    return {
        "general_required": load_courses(path, category=Category.GENERAL_REQUIRED),
        "general_elective": load_courses(path, category=Category.GENERAL_ELECTIVE),
    }
