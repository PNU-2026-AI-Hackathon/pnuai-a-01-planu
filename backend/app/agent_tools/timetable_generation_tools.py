"""Agent tool adapters for timetable generation and validation."""

from __future__ import annotations

from collections.abc import Mapping

from pydantic import ValidationError

from ..models.timetable_generation import (
    GenerationFailureCode,
    GenerationFailureReason,
    TimetableGenerationError,
    TimetableGenerationRequest,
    TimetableGenerationResult,
    TimetableValidationRequest,
    TimetableValidationResult,
    TimetableViolation,
    TimetableViolationCode,
)
from ..services.timetable_candidate_generation_service import (
    TimetableCandidateGenerationService,
)
from ..services.timetable_candidate_validation_service import (
    TimetableCandidateValidationService,
)


class TimetableGenerationTools:
    """Thin adapters over timetable generation services for PlaNU agents."""

    def __init__(
        self,
        *,
        generation_service: TimetableCandidateGenerationService,
        validation_service: TimetableCandidateValidationService,
    ) -> None:
        self._generation_service = generation_service
        self._validation_service = validation_service

    def generate_timetable_candidates(
        self,
        data: TimetableGenerationRequest | Mapping[str, object],
    ) -> TimetableGenerationResult:
        """Generate candidates from fixed sections and structured candidates.

        Use when combining fixed major sections with candidate general-course
        sections. This tool does not accept the user's whole natural-language
        request, excludes combinations that violate Hard constraints, does not
        calculate Soft preference scores, applies result and search limits, and
        never saves generated candidates to session state.
        """

        try:
            request = TimetableGenerationRequest.model_validate(data)
        except ValidationError as exc:
            message = str(exc.errors()[0]["msg"])
            return TimetableGenerationResult(
                success=False,
                candidates=[],
                total_candidates_found=0,
                search_nodes_visited=0,
                search_truncated=False,
                failure_reasons=[
                    GenerationFailureReason(
                        code=GenerationFailureCode.INVALID_GENERATION_REQUEST,
                        message=message,
                        constraint=".".join(str(part) for part in exc.errors()[0]["loc"]),
                    )
                ],
                message=message,
                error=TimetableGenerationError(
                    code=GenerationFailureCode.INVALID_GENERATION_REQUEST,
                    message=message,
                ),
            )
        return self._generation_service.generate(request)

    def validate_timetable_candidate(
        self,
        data: TimetableValidationRequest | Mapping[str, object],
    ) -> TimetableValidationResult:
        """Validate one candidate section combination against Hard rules.

        Use for an existing candidate or user-selected section combination. It
        returns validation only, does not mutate session/catalog state, and does
        not treat Soft preference mismatches as failures.
        """

        try:
            request = TimetableValidationRequest.model_validate(data)
        except ValidationError as exc:
            return TimetableValidationResult(
                valid=False,
                violations=[
                    TimetableViolation(
                        code=TimetableViolationCode.MISSING_REQUIRED_COURSE,
                        message=str(exc.errors()[0]["msg"]),
                        constraint=".".join(str(part) for part in exc.errors()[0]["loc"]),
                    )
                ],
                checked_section_ids=[],
            )
        return self._validation_service.validate(request)
