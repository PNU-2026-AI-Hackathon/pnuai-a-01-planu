"""Helpers for comparing logical course ids across legacy and agent models."""

from __future__ import annotations

from collections.abc import Iterable


def logical_course_id(course_id: str, division: str | None = None) -> str:
    """Return the catalog-level course id, preserving section ids otherwise."""

    normalized = str(course_id).strip()
    normalized_division = str(division or "").strip()
    suffix = f"-{normalized_division}"
    if normalized_division and normalized.endswith(suffix):
        return normalized[: -len(suffix)]
    return normalized


def logical_course_id_from_requested(
    requested_id: str,
    *,
    candidate_course_id: str,
    candidate_division: str | None = None,
) -> str:
    """Normalize a requested id with the candidate's actual division context."""

    normalized = str(requested_id).strip()
    division = str(candidate_division or "").strip()
    candidate_logical = logical_course_id(candidate_course_id, division)
    if division and normalized == f"{candidate_logical}-{division}":
        return candidate_logical
    return logical_course_id(normalized, division)


def normalize_requested_course_ids(
    course_ids: Iterable[str],
    sections: Iterable[object],
) -> set[str]:
    """Normalize request ids using available section divisions without blind split."""

    section_values = list(sections)
    normalized: set[str] = set()
    for course_id in course_ids:
        if not section_values:
            normalized.add(str(course_id).strip())
            continue
        for section in section_values:
            normalized.add(
                logical_course_id_from_requested(
                    course_id,
                    candidate_course_id=str(getattr(section, "course_id")),
                    candidate_division=str(getattr(section, "division", "") or ""),
                )
            )
    return normalized


def logical_course_ids_for_objects(courses: Iterable[object]) -> set[str]:
    return {
        logical_course_id(
            str(getattr(course, "course_id")),
            str(getattr(course, "division", "") or ""),
        )
        for course in courses
    }
