"""Common exceptions raised by session repository implementations."""

from __future__ import annotations


class SessionRepositoryError(RuntimeError):
    """Base class for expected session repository failures."""

    def __init__(self, session_id: str, message: str | None = None) -> None:
        self.session_id = session_id
        super().__init__(message or f"session repository error: {session_id}")


class SessionAlreadyExistsError(SessionRepositoryError):
    """Raised when creating a session with an existing session id."""

    def __init__(self, session_id: str) -> None:
        super().__init__(session_id, f"session already exists: {session_id}")


class SessionNotFoundError(SessionRepositoryError):
    """Raised when updating a session id that does not exist."""

    def __init__(self, session_id: str) -> None:
        super().__init__(session_id, f"session not found: {session_id}")


class CatalogRepositoryError(RuntimeError):
    """Base class for expected catalog repository failures."""

    def __init__(self, catalog_id: str, message: str | None = None) -> None:
        self.catalog_id = catalog_id
        super().__init__(message or f"catalog repository error: {catalog_id}")


class CatalogAlreadyExistsError(CatalogRepositoryError):
    """Raised when registering an already existing catalog id."""

    def __init__(self, catalog_id: str) -> None:
        super().__init__(catalog_id, f"catalog already exists: {catalog_id}")


class CatalogNotFoundError(CatalogRepositoryError):
    """Raised when a catalog id is not registered."""

    def __init__(self, catalog_id: str) -> None:
        super().__init__(catalog_id, f"catalog not found: {catalog_id}")


class CourseNotFoundError(CatalogRepositoryError):
    """Raised when a course id is not present in a catalog."""

    def __init__(self, catalog_id: str, course_id: str) -> None:
        self.course_id = course_id
        super().__init__(catalog_id, f"course not found in {catalog_id}: {course_id}")


class SectionNotFoundError(CatalogRepositoryError):
    """Raised when a section id is not present in a catalog."""

    def __init__(self, catalog_id: str, section_id: str) -> None:
        self.section_id = section_id
        super().__init__(catalog_id, f"section not found in {catalog_id}: {section_id}")
