"""CatalogRepository adapter over catalog data stored in SessionStore."""

from __future__ import annotations

from ..models.course import Course
from ..models.course_discovery import CatalogKind, CatalogRecord, CourseSection
from ..services.session_store import SessionNotFoundError as StoreSessionNotFoundError, SessionStore
from .exceptions import CatalogAlreadyExistsError, CatalogNotFoundError, CourseNotFoundError, SectionNotFoundError


class SessionStoreCatalogRepository:
    """Expose parsed courses already held by ``SessionStore`` as catalogs."""

    def __init__(self, store: SessionStore) -> None:
        self._store = store

    def register(
        self,
        catalog_id: str,
        *,
        kind: CatalogKind,
        courses: list[Course],
        department: str | None = None,
    ) -> CatalogRecord:
        session_id, bucket = _split_catalog_id(catalog_id)
        try:
            data = self._store.get(session_id, touch=False)
        except StoreSessionNotFoundError as exc:
            raise CatalogNotFoundError(catalog_id) from exc

        if bucket == "major":
            if data.major_candidates:
                raise CatalogAlreadyExistsError(catalog_id)
            data = self._store.update(
                session_id,
                major_candidates=courses,
                major_catalog_id=catalog_id,
                department=department,
            )
        else:
            if data.elective_candidates:
                raise CatalogAlreadyExistsError(catalog_id)
            data = self._store.update(
                session_id,
                elective_candidates=courses,
                elective_catalog_id=catalog_id,
                department=department,
            )
        return CatalogRecord(
            catalog_id=catalog_id,
            kind=kind,
            sections=_sections_for_bucket(data, bucket),
        )

    def exists(self, catalog_id: str) -> bool:
        try:
            self.list_sections(catalog_id)
        except CatalogNotFoundError:
            return False
        return True

    def list_sections(self, catalog_id: str) -> list[CourseSection]:
        session_id, bucket = _split_catalog_id(catalog_id)
        try:
            data = self._store.get(session_id, touch=False)
        except StoreSessionNotFoundError as exc:
            raise CatalogNotFoundError(catalog_id) from exc
        sections = _sections_for_bucket(data, bucket)
        if not sections:
            raise CatalogNotFoundError(catalog_id)
        return [section.model_copy(deep=True) for section in sections]

    def get_course_sections(self, catalog_id: str, course_id: str) -> list[CourseSection]:
        sections = [
            section for section in self.list_sections(catalog_id)
            if section.course_id == course_id
        ]
        if not sections:
            raise CourseNotFoundError(catalog_id, course_id)
        return sections

    def get_section(self, catalog_id: str, section_id: str) -> CourseSection:
        for section in self.list_sections(catalog_id):
            if section.section_id == section_id:
                return section
        raise SectionNotFoundError(catalog_id, section_id)

    def delete(self, catalog_id: str) -> None:
        session_id, bucket = _split_catalog_id(catalog_id)
        try:
            if bucket == "major":
                self._store.update(session_id, major_candidates=[], major_catalog_id="")
            else:
                self._store.update(session_id, elective_candidates=[], elective_catalog_id="")
        except StoreSessionNotFoundError:
            return


def _split_catalog_id(catalog_id: str) -> tuple[str, str]:
    if catalog_id.endswith(":major"):
        return catalog_id[:-6], "major"
    if catalog_id.endswith(":elective"):
        return catalog_id[:-9], "elective"
    if catalog_id.endswith(":general"):
        return catalog_id[:-8], "general"
    raise CatalogNotFoundError(catalog_id)


def _sections_for_bucket(data, bucket: str) -> list[CourseSection]:
    if bucket == "major":
        courses = data.major_candidates
    elif bucket == "elective":
        courses = data.elective_candidates
    else:
        courses = [
            *data.general_required_candidates,
            *data.general_elective_candidates,
        ]
    return [
        CourseSection.from_course(course, department=data.department)
        for course in courses
    ]
