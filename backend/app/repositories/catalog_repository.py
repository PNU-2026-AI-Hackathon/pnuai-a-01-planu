"""Protocol for parsed course catalog persistence."""

from __future__ import annotations

from typing import Protocol

from ..models.course import Course
from ..models.course_discovery import CatalogKind, CatalogRecord, CourseSection


class CatalogRepository(Protocol):
    """Storage boundary for parsed course catalog sections.

    Implementations connect a catalog id to already parsed, structured course
    sections. They must not perform natural-language search, recommendation,
    session lookup, timetable generation, conflict checks, or scoring.
    """

    def register(
        self,
        catalog_id: str,
        *,
        kind: CatalogKind,
        courses: list[Course],
        department: str | None = None,
    ) -> CatalogRecord:
        """Register parsed courses under ``catalog_id``.

        Raises:
            CatalogAlreadyExistsError: If ``catalog_id`` is already present.
        """

    def exists(self, catalog_id: str) -> bool:
        """Return whether ``catalog_id`` is registered."""

    def list_sections(self, catalog_id: str) -> list[CourseSection]:
        """Return every stored section in the catalog."""

    def get_course_sections(self, catalog_id: str, course_id: str) -> list[CourseSection]:
        """Return all sections belonging to one course-level id."""

    def get_section(self, catalog_id: str, section_id: str) -> CourseSection:
        """Return one concrete section by id."""

    def delete(self, catalog_id: str) -> None:
        """Delete a catalog idempotently."""
