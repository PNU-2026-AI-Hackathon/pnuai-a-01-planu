"""Load department restriction rules from generated restriction JSON."""

from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path
from typing import Any

from .general_course_pool_service import DepartmentRestrictionRule


class CourseRestrictionLoadError(ValueError):
    """Raised when course_restrictions.json cannot be loaded safely."""


def load_department_restriction_rules(path: str | Path) -> list[DepartmentRestrictionRule]:
    source = Path(path)
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CourseRestrictionLoadError("course_restrictions.json을 읽을 수 없습니다.") from exc
    if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
        raise CourseRestrictionLoadError("course_restrictions.json은 객체 배열이어야 합니다.")

    allowed_by_key: dict[tuple[str, str], set[str]] = defaultdict(set)
    blocked_by_key: dict[tuple[str, str], set[str]] = defaultdict(set)

    for index, item in enumerate(payload, start=1):
        row = _row_data(item)
        if _text(row.get("제한구분")) != "학과":
            continue

        course_code = _required_text(row, "교과목번호", index)
        division = _required_text(row, "분반", index)
        availability = _required_text(row, "수강여부", index)
        department = _required_text(row, "학과명", index)
        key = (course_code, division)

        if availability == "수강가능":
            allowed_by_key[key].add(department)
        elif availability == "수강불가":
            blocked_by_key[key].add(department)
        else:
            raise CourseRestrictionLoadError(
                f"{index}번째 제한 행의 수강여부를 처리할 수 없습니다: {availability}"
            )

    return [
        DepartmentRestrictionRule(
            course_code=course_code,
            division=division,
            allowed_departments=frozenset(allowed_by_key[key]),
            blocked_departments=frozenset(blocked_by_key[key]),
        )
        for key in sorted(allowed_by_key.keys() | blocked_by_key.keys())
        for course_code, division in [key]
    ]


def _row_data(item: dict[str, Any]) -> dict[str, Any]:
    data = item.get("data", item)
    if not isinstance(data, dict):
        raise CourseRestrictionLoadError("제한 행의 data 필드는 객체여야 합니다.")
    return data


def _required_text(row: dict[str, Any], field: str, index: int) -> str:
    value = _text(row.get(field))
    if not value:
        raise CourseRestrictionLoadError(f"{index}번째 제한 행의 {field} 값이 비어 있습니다.")
    return value


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()
