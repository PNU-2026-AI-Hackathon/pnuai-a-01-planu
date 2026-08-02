"""Repository contracts and shared repository errors."""

from .exceptions import (
    CatalogAlreadyExistsError,
    CatalogNotFoundError,
    CatalogRepositoryError,
    CourseNotFoundError,
    SectionNotFoundError,
    SessionAlreadyExistsError,
    SessionNotFoundError,
    SessionRepositoryError,
)
from .catalog_repository import CatalogRepository
from .in_memory_catalog_repository import InMemoryCatalogRepository
from .in_memory_session_repository import InMemorySessionRepository
from .session_repository import SessionRepository

__all__ = [
    "CatalogAlreadyExistsError",
    "CatalogNotFoundError",
    "CatalogRepository",
    "CatalogRepositoryError",
    "CourseNotFoundError",
    "InMemorySessionRepository",
    "InMemoryCatalogRepository",
    "SectionNotFoundError",
    "SessionAlreadyExistsError",
    "SessionNotFoundError",
    "SessionRepository",
    "SessionRepositoryError",
]
