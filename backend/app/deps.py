"""FastAPI dependency providers."""

from __future__ import annotations

from .services.major_confirm_service import MajorConfirmService
from .services.major_preview_service import MajorPreviewService
from .services.major_selection_parser import MajorSelectionParser
from .services.session_store import SessionStore, session_store


def get_session_store() -> SessionStore:
    return session_store


def get_major_selection_parser() -> MajorSelectionParser:
    return MajorSelectionParser()


def get_major_preview_service() -> MajorPreviewService:
    return MajorPreviewService(
        store=get_session_store(),
        parser=get_major_selection_parser(),
    )


def get_major_confirm_service() -> MajorConfirmService:
    return MajorConfirmService(store=get_session_store())
