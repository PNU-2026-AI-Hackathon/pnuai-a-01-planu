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
    candidate_section_id: str | None = None,
) -> str:
    """Normalize a requested id only when it matches the candidate context."""

    normalized = str(requested_id).strip()
    if course_id_matches(
        normalized,
        candidate_course_id=candidate_course_id,
        candidate_division=candidate_division,
        candidate_section_id=candidate_section_id,
    ):
        return logical_course_id(candidate_course_id, candidate_division)
    return normalized


def course_id_matches(
    requested_id: str,
    *,
    candidate_course_id: str,
    candidate_division: str | None = None,
    candidate_section_id: str | None = None,
) -> bool:
    """Return whether a requested id points at the candidate's logical course."""

    normalized = str(requested_id).strip()
    course_id = str(candidate_course_id).strip()
    section_id = str(candidate_section_id or "").strip()
    logical_id = logical_course_id(course_id, candidate_division)
    division = str(candidate_division or "").strip()

    if normalized in {course_id, logical_id}:
        return True
    if section_id and normalized == section_id:
        return True
    if division and normalized == f"{logical_id}-{division}":
        return True
    return False


def normalize_requested_course_ids(
    course_ids: Iterable[str],
    sections: Iterable[object],
) -> set[str]:
    """Normalize each request id once using a matching section context.

    A request id is folded to a logical course id only when an available section
    actually matches it by logical id, raw course id, section id, or the exact
    ``-{division}`` legacy suffix. Unmatched ids are preserved as-is instead of
    being expanded through unrelated section divisions.
    """

    section_values = list(sections)
    normalized: set[str] = set()
    for course_id in course_ids:
        requested = str(course_id).strip()
        matched = False
        for section in section_values:
            candidate_course_id = str(getattr(section, "course_id"))
            candidate_division = str(getattr(section, "division", "") or "")
            candidate_section_id = getattr(section, "section_id", None)
            if not course_id_matches(
                requested,
                candidate_course_id=candidate_course_id,
                candidate_division=candidate_division,
                candidate_section_id=None if candidate_section_id is None else str(candidate_section_id),
            ):
                continue
            normalized.add(logical_course_id(candidate_course_id, candidate_division))
            matched = True
            break
        if not matched:
            normalized.add(requested)
    return normalized


def logical_course_ids_for_objects(courses: Iterable[object]) -> set[str]:
    return {
        logical_course_id(
            str(getattr(course, "course_id")),
            str(getattr(course, "division", "") or ""),
        )
        for course in courses
    }
