"""Session-aware timetable ranking orchestration."""

from __future__ import annotations

from datetime import datetime, timezone

from ..models.preference import PreferenceRules, PreferenceTemplate
from ..models.timetable import (
    RankingDiagnostic,
    RankingTemplate,
    TimetableRankingResult,
)
from .ranking_template_service import RankingTemplateService, normalize_ranking_template
from .session_store import SessionStage, SessionStore, session_store
from .timetable_ranker import TimetableRanker


class TimetableRankingError(RuntimeError):
    """Base class for expected ranking orchestration failures."""


class InvalidRankingSessionStageError(TimetableRankingError):
    pass


class NoGeneratedCandidatesError(TimetableRankingError):
    pass


class TimetableRankingService:
    """Rank already-generated candidates stored in a session."""

    ranking_ready_stages = {
        SessionStage.CANDIDATES_GENERATED,
        SessionStage.RANKING_COMPLETED,
    }

    def __init__(
        self,
        store: SessionStore = session_store,
        *,
        template_service: RankingTemplateService | None = None,
        ranker: TimetableRanker | None = None,
    ) -> None:
        self.store = store
        self.template_service = template_service or RankingTemplateService()
        self.ranker = ranker or TimetableRanker(template_service=self.template_service)

    def rank_for_session(
        self,
        *,
        session_id: str,
        template: RankingTemplate | PreferenceTemplate | str = RankingTemplate.BALANCED,
        top_n: int | None = None,
    ) -> TimetableRankingResult:
        session = self.store.get(session_id)
        if session.session_stage not in self.ranking_ready_stages:
            raise InvalidRankingSessionStageError(
                "generated candidates are required before ranking"
            )
        if not session.generated_candidates:
            raise NoGeneratedCandidatesError("session has no generated timetable candidates")

        ranking_template = normalize_ranking_template(template)
        definition = self.template_service.get_definition(ranking_template)
        candidates = list(session.generated_candidates)
        diagnostics = []
        deduped_candidates = self.ranker._dedupe_candidates(candidates)
        duplicate_count = len(candidates) - len(deduped_candidates)
        if duplicate_count:
            diagnostics.append(
                RankingDiagnostic(
                    code="DUPLICATE_CANDIDATE_REMOVED",
                    message="동일한 과목/분반 조합의 중복 후보가 제거되었습니다.",
                    details={"removed_count": duplicate_count},
                )
            )
        hard_filtered = self.ranker.apply_hard_filters(
            deduped_candidates,
            preferences=session.ranking_preferences,
        )
        hard_removed_count = len(deduped_candidates) - len(hard_filtered)
        if hard_removed_count:
            diagnostics.append(
                RankingDiagnostic(
                    code="HARD_CONDITION_CANDIDATE_DETECTED",
                    message="하드 조건을 위반한 후보가 랭킹 대상에서 제외되었습니다.",
                    details={"removed_count": hard_removed_count},
                )
            )

        ranking_limit = len(hard_filtered) if top_n is None else top_n
        if ranking_limit <= 0:
            raise ValueError("top_n must be positive")

        context = self.ranker._build_context(ranking_template, session.ranking_preferences)
        ranked = self.ranker.rank_filtered_candidates(
            hard_filtered,
            preferences=session.ranking_preferences,
            context=context,
            top_n=ranking_limit,
        )
        if len(ranked) < len(hard_filtered):
            diagnostics.append(
                RankingDiagnostic(
                    code="RANKING_RESULT_TRUNCATED",
                    message="랭킹 결과가 요청한 개수로 잘렸습니다.",
                    details={"top_n": top_n, "rankable_count": len(hard_filtered)},
                )
            )

        result = TimetableRankingResult(
            ranked_candidates=ranked,
            template=definition.template,
            total_candidate_count=len(candidates),
            diagnostics=[
                *diagnostics,
                RankingDiagnostic(
                    code="RANKING_WEIGHTS_APPLIED",
                    message="랭킹 템플릿 가중치가 적용되었습니다.",
                    details={
                        "template": definition.template.value,
                        "template_name": definition.name,
                        "ranked_at": datetime.now(timezone.utc).isoformat(),
                        "weights": definition.weights.__dict__,
                    },
                ),
            ],
        )
        self.store.update_ranking_result(session_id, result)
        return result

def rank_timetables_for_session(
    *,
    session_id: str,
    template: RankingTemplate | PreferenceTemplate | str = RankingTemplate.BALANCED,
    top_n: int | None = None,
    preferences: PreferenceRules | None = None,
    store: SessionStore = session_store,
) -> TimetableRankingResult:
    if preferences is not None:
        store.update(session_id, ranking_preferences=preferences)
    return TimetableRankingService(store).rank_for_session(
        session_id=session_id,
        template=template,
        top_n=top_n,
    )
