"""In-memory implementation of parsed catalog storage."""

from __future__ import annotations

from threading import RLock

from ..models.course import Course
from ..models.course_discovery import CatalogKind, CatalogRecord, CourseSection
from .exceptions import (
    CatalogAlreadyExistsError,
    CatalogNotFoundError,
    CourseNotFoundError,
    SectionNotFoundError,
)


class InMemoryCatalogRepository:
    """Process-local repository for parsed course catalog sections."""

    def __init__(self) -> None:
        self._catalogs: dict[str, CatalogRecord] = {}
        self._lock = RLock()

    def register(
        self,
        catalog_id: str,
        *,
        kind: CatalogKind,
        courses: list[Course],
        department: str | None = None,
    ) -> CatalogRecord:
        catalog_id = catalog_id.strip()
        if not catalog_id:
            raise ValueError("catalog_id must not be empty")

        sections = [
            CourseSection.from_course(course, department=department)
            for course in courses
        ]
        record = CatalogRecord(catalog_id=catalog_id, kind=kind, sections=sections)
        with self._lock:
            if catalog_id in self._catalogs:
                raise CatalogAlreadyExistsError(catalog_id)
            stored = record.model_copy(deep=True)
            self._catalogs[catalog_id] = stored
            return stored.model_copy(deep=True)

    def exists(self, catalog_id: str) -> bool:
        with self._lock:
            return catalog_id in self._catalogs

    def list_sections(self, catalog_id: str) -> list[CourseSection]:
        record = self._get_record(catalog_id)
        return record.sections

    def get_course_sections(self, catalog_id: str, course_id: str) -> list[CourseSection]:
        record = self._get_record(catalog_id)
        sections = [section for section in record.sections if section.course_id == course_id]
        if not sections:
            raise CourseNotFoundError(catalog_id, course_id)
        return [section.model_copy(deep=True) for section in sections]

    def get_section(self, catalog_id: str, section_id: str) -> CourseSection:
        record = self._get_record(catalog_id)
        for section in record.sections:
            if section.section_id == section_id:
                return section.model_copy(deep=True)
        raise SectionNotFoundError(catalog_id, section_id)

    def delete(self, catalog_id: str) -> None:
        with self._lock:
            self._catalogs.pop(catalog_id, None)

    def _get_record(self, catalog_id: str) -> CatalogRecord:
        with self._lock:
            record = self._catalogs.get(catalog_id)
            if record is None:
                raise CatalogNotFoundError(catalog_id)
            return record.model_copy(deep=True)
