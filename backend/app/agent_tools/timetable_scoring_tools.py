"""Agent tool adapters for timetable scoring and ranking."""

from __future__ import annotations

from collections.abc import Mapping

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ..models.session_preferences import SoftPreferences
from ..models.timetable_generation import GeneratedTimetableCandidate, ResolvedSection
from ..models.timetable_scoring import (
    ScoredTimetableCandidate,
    ScoringErrorCode,
    TimetableRankingResult,
    TimetableScoringError,
    TimetableScoringPolicy,
    TimetableScoringRequest,
)
from ..services.timetable_scoring_service import (
    TimetableScoringService,
    scoring_error_from_exception,
)
from ..services.timetable_soft_ranking_service import TimetableRankingService


class _Model(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )


class ScoreTimetableCandidateRequest(_Model):
    candidate: GeneratedTimetableCandidate
    sections: list[ResolvedSection] = Field(default_factory=list)
    soft_preferences: SoftPreferences = Field(default_factory=SoftPreferences)
    scoring_policy: TimetableScoringPolicy = Field(default_factory=TimetableScoringPolicy)


class TimetableScoringTools:
    """Thin adapters over scoring services; they never mutate session state."""

    def __init__(
        self,
        *,
        scoring_service: TimetableScoringService | None = None,
        ranking_service: TimetableRankingService | None = None,
    ) -> None:
        self._scoring_service = scoring_service or TimetableScoringService()
        self._ranking_service = ranking_service or TimetableRankingService(
            scoring_service=self._scoring_service
        )

    def score_timetable_candidate(
        self,
        data: ScoreTimetableCandidateRequest | Mapping[str, object],
    ) -> ScoredTimetableCandidate | TimetableScoringError:
        """Evaluate one Hard-valid candidate using structured Soft preferences."""

        try:
            request = ScoreTimetableCandidateRequest.model_validate(data)
            return self._scoring_service.score_candidate(
                candidate=request.candidate,
                soft_preferences=request.soft_preferences,
                sections=request.sections,
                policy=request.scoring_policy,
            )
        except ValidationError as exc:
            return TimetableScoringError(
                code=ScoringErrorCode.INVALID_SCORING_REQUEST,
                message=str(exc.errors()[0]["msg"]),
            )
        except Exception as exc:
            return scoring_error_from_exception(exc)

    def rank_timetable_candidates(
        self,
        data: TimetableScoringRequest | Mapping[str, object],
    ) -> TimetableRankingResult:
        """Rank multiple Hard-valid candidates without choosing or saving one."""

        try:
            request = TimetableScoringRequest.model_validate(data)
        except ValidationError as exc:
            message = str(exc.errors()[0]["msg"])
            return TimetableRankingResult(
                success=False,
                ranked_candidates=[],
                total_candidates=0,
                returned_candidates=0,
                message=message,
                error=TimetableScoringError(
                    code=ScoringErrorCode.INVALID_SCORING_REQUEST,
                    message=message,
                ),
            )
        return self._ranking_service.rank_candidates(request)
