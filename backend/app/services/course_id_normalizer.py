"""Helpers for comparing logical course ids across legacy and agent models."""

from __future__ import annotations


def logical_course_id(course_id: str, division: str | None = None) -> str:
    """Return the catalog-level course id, preserving section ids otherwise."""

    normalized = str(course_id).strip()
    normalized_division = str(division or "").strip()
    suffix = f"-{normalized_division}"
    if normalized_division and normalized.endswith(suffix):
        return normalized[: -len(suffix)]
    return normalized


def logical_course_ids_for_objects(courses: object) -> set[str]:
    return {
        logical_course_id(
            str(getattr(course, "course_id")),
            str(getattr(course, "division", "") or ""),
        )
        for course in courses
    }
