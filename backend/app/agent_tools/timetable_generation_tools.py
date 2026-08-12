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
from ..repositories.recent_timetable_candidate_repository import RecentTimetableCandidateRepository
from ..services.condition_summary_service import ConditionSummaryService
from ..services.session_service import SessionService


class TimetableGenerationTools:
    """Thin adapters over timetable generation services for PlaNU agents."""

    def __init__(
        self,
        *,
        generation_service: TimetableCandidateGenerationService,
        validation_service: TimetableCandidateValidationService,
        recent_candidate_repository: RecentTimetableCandidateRepository | None = None,
        session_service: SessionService | None = None,
        condition_summary_service: ConditionSummaryService | None = None,
    ) -> None:
        self._generation_service = generation_service
        self._validation_service = validation_service
        self._recent_candidate_repository = recent_candidate_repository
        self._session_service = session_service
        self._condition_summary_service = condition_summary_service

    def generate_timetable_candidates(
        self,
        data: TimetableGenerationRequest | Mapping[str, object],
    ) -> TimetableGenerationResult:
        """Generate candidates from fixed sections and structured candidates.

        Use when combining fixed major sections with candidate general-course
        sections. This tool does not accept the user's whole natural-language
        request, excludes combinations that violate Hard constraints, does not
        calculate Soft preference scores, applies result and search limits, and
        stores generated candidates only in the server-side recent-candidate cache when session_id is supplied; it never selects a candidate.
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
        gate_failure = self._generation_gate_failure(request)
        if gate_failure is not None:
            return gate_failure
        if request.session_id is not None and self._recent_candidate_repository is not None:
            self._recent_candidate_repository.clear_candidates(request.session_id)
        result = self._generation_service.generate(request)
        if (
            request.session_id is not None
            and result.success
            and self._recent_candidate_repository is not None
        ):
            self._recent_candidate_repository.save_candidates(
                request.session_id,
                result.candidates,
            )
        return result

    def _generation_gate_failure(
        self,
        request: TimetableGenerationRequest,
    ) -> TimetableGenerationResult | None:
        if request.session_id is None or self._session_service is None or self._condition_summary_service is None:
            return None
        state = self._session_service.get_session(request.session_id)
        readiness = self._condition_summary_service.summarize(state).generation_readiness
        if not readiness.ready:
            return self._failed_generation(
                GenerationFailureCode.TIMETABLE_GENERATION_NOT_READY,
                "시간표 생성에 필요한 정보가 아직 부족합니다.",
            )
        if not readiness.generation_confirmed:
            return self._failed_generation(
                GenerationFailureCode.TIMETABLE_CONDITIONS_NOT_CONFIRMED,
                "현재 조건 확인 후 시간표를 생성할 수 있습니다.",
            )
        return None

    @staticmethod
    def _failed_generation(
        code: GenerationFailureCode,
        message: str,
    ) -> TimetableGenerationResult:
        reason = GenerationFailureReason(code=code, message=message)
        return TimetableGenerationResult(
            success=False,
            candidates=[],
            total_candidates_found=0,
            search_nodes_visited=0,
            search_truncated=False,
            failure_reasons=[reason],
            message=message,
            error=TimetableGenerationError(code=code, message=message),
        )

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
                        code=TimetableViolationCode.INVALID_VALIDATION_REQUEST,
                        message=str(exc.errors()[0]["msg"]),
                        constraint=".".join(str(part) for part in exc.errors()[0]["loc"]),
                    )
                ],
                checked_section_ids=[],
            )
        return self._validation_service.validate(request)
