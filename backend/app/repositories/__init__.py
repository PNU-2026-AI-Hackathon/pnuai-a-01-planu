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
    SessionVersionConflictError,
)
from .catalog_repository import CatalogRepository
from .in_memory_catalog_repository import InMemoryCatalogRepository
from .in_memory_session_repository import InMemorySessionRepository
from .session_repository import SessionRepository
from .session_store_catalog_repository import SessionStoreCatalogRepository
from .session_store_repository import SessionStoreRepository

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
    "SessionStoreCatalogRepository",
    "SessionStoreRepository",
    "SessionVersionConflictError",
]
