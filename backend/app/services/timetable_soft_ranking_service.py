"""Rank generated timetable candidates by Soft-preference scores."""

from __future__ import annotations

import logging
from collections.abc import Iterable

from ..models.session_preferences import SoftPreferences
from ..models.timetable_generation import GeneratedTimetableCandidate, ResolvedSection
from ..models.timetable_scoring import (
    ScoredTimetableCandidate,
    TimetableRankingResult,
    TimetableScoringError,
    TimetableScoringPolicy,
    TimetableScoringRequest,
)
from .timetable_scoring_service import TimetableScoringService, scoring_error_from_exception

logger = logging.getLogger(__name__)


class TimetableRankingService:
    """Apply scoring service to candidates and assign deterministic ranks."""

    def __init__(
        self,
        *,
        scoring_service: TimetableScoringService | None = None,
        policy: TimetableScoringPolicy | None = None,
    ) -> None:
        self.policy = policy or TimetableScoringPolicy()
        self.scoring_service = scoring_service or TimetableScoringService(policy=self.policy)

    def rank_candidates(
        self,
        request: TimetableScoringRequest,
    ) -> TimetableRankingResult:
        if not request.candidates:
            return TimetableRankingResult(
                success=True,
                ranked_candidates=[],
                total_candidates=0,
                returned_candidates=0,
                scoring_policy=request.scoring_policy,
                message="유효한 시간표 후보 0개를 Soft 선호 기준으로 평가하고 상위 0개를 반환했습니다.",
            )

        try:
            scored = [
                self.scoring_service.score_candidate(
                    candidate=candidate,
                    soft_preferences=request.soft_preferences,
                    sections=request.sections,
                    policy=request.scoring_policy,
                )
                for candidate in request.candidates
            ]
        except Exception as exc:
            return TimetableRankingResult(
                success=False,
                ranked_candidates=[],
                total_candidates=len(request.candidates),
                returned_candidates=0,
                scoring_policy=request.scoring_policy,
                message="시간표 후보 점수화에 실패했습니다.",
                error=scoring_error_from_exception(exc),
            )

        ranked = self._assign_ranks(scored)[: request.max_ranked_results]
        logger.info(
            "ranked timetable candidates",
            extra={
                "candidate_count": len(request.candidates),
                "returned_count": len(ranked),
                "policy_id": request.scoring_policy.policy_id,
                "scores": {item.candidate_id: item.total_score for item in ranked},
            },
        )
        return TimetableRankingResult(
            success=True,
            ranked_candidates=ranked,
            total_candidates=len(request.candidates),
            returned_candidates=len(ranked),
            scoring_policy=request.scoring_policy,
            message=(
                f"유효한 시간표 후보 {len(request.candidates)}개를 Soft 선호 기준으로 "
                f"평가하고 상위 {len(ranked)}개를 반환했습니다."
            ),
        )

    def rank(
        self,
        *,
        candidates: Iterable[GeneratedTimetableCandidate],
        sections: Iterable[ResolvedSection],
        soft_preferences: SoftPreferences,
        max_ranked_results: int = 3,
        scoring_policy: TimetableScoringPolicy | None = None,
    ) -> TimetableRankingResult:
        return self.rank_candidates(
            TimetableScoringRequest(
                candidates=list(candidates),
                sections=list(sections),
                soft_preferences=soft_preferences,
                max_ranked_results=max_ranked_results,
                scoring_policy=scoring_policy or self.policy,
            )
        )

    @staticmethod
    def _assign_ranks(
        candidates: list[ScoredTimetableCandidate],
    ) -> list[ScoredTimetableCandidate]:
        ranked = sorted(
            candidates,
            key=lambda item: (
                -item.total_score,
                -int(item.tie_breaker.get("satisfied_count", 0)),
                int(item.tie_breaker.get("disliked_course_count", 0)),
                int(item.tie_breaker.get("total_gap_minutes", 0)),
                int(item.tie_breaker.get("latest_end_minutes", 0)),
                item.candidate_id,
            ),
        )
        return [
            item.model_copy(update={"rank": index})
            for index, item in enumerate(ranked, start=1)
        ]
