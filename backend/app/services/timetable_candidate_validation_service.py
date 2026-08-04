"""Resolve validation requests and delegate to deterministic timetable validation."""

from __future__ import annotations

from ..models.timetable_generation import (
    ResolvedSection,
    TimetableValidationRequest,
    TimetableValidationResult,
    TimetableViolation,
    TimetableViolationCode,
)
from ..repositories.catalog_repository import CatalogRepository
from ..repositories.exceptions import CatalogNotFoundError, SectionNotFoundError
from .timetable_validation_service import TimetableValidationService


class TimetableCandidateValidationService:
    """Thin service boundary for validating section-source based requests."""

    def __init__(
        self,
        *,
        catalog_repository: CatalogRepository,
        validation_service: TimetableValidationService | None = None,
    ) -> None:
        self.catalog_repository = catalog_repository
        self.validation_service = validation_service or TimetableValidationService()

    def validate(
        self,
        request: TimetableValidationRequest,
    ) -> TimetableValidationResult:
        try:
            sections = [
                ResolvedSection(
                    catalog_id=source.catalog_id,
                    section=self.catalog_repository.get_section(
                        source.catalog_id,
                        source.section_id,
                    ),
                )
                for source in request.section_sources
            ]
        except (CatalogNotFoundError, SectionNotFoundError):
            return TimetableValidationResult(
                valid=False,
                violations=[
                    TimetableViolation(
                        code=TimetableViolationCode.INVALID_VALIDATION_REQUEST,
                        message="요청한 catalog 또는 section을 찾을 수 없습니다.",
                        constraint="section_sources",
                    )
                ],
                checked_section_ids=[],
            )
        return self.validation_service.validate_sections(
            sections,
            required_course_ids=request.required_course_ids,
            excluded_course_ids=request.excluded_course_ids,
            required_free_days=request.required_free_days,
            earliest_start_time=request.earliest_start_time,
            latest_end_time=request.latest_end_time,
            department=request.department,
        )
