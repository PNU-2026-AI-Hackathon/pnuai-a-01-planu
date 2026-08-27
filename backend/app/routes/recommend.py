"""Timetable generation and recommendation routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..core.errors import AppError
from ..deps import get_timetable_generation_service, get_timetable_ranking_service
from ..schemas.recommend_schema import (
    RankedTimetableResponse,
    TimetableGenerationRequest,
    TimetableGenerationResponse,
    TimetableRankingRequest,
    TimetableRankingResponse,
)
from ..models.timetable import Timetable
from ..services.timetable_generation_service import TimetableGenerationService, legacy_candidate_id_for_courses
from ..services.ranking_template_service import normalize_ranking_template
from ..services.session_store import SessionNotFoundError
from ..services.timetable_ranking_service import (
    InvalidRankingSessionStageError,
    NoGeneratedCandidatesError,
    NoRankableCandidatesError,
    TimetableRankingError,
    TimetableRankingService,
)


router = APIRouter(prefix="/recommend", tags=["recommend"])


@router.post("/generate", response_model=TimetableGenerationResponse)
def generate_timetable_candidates(
    request: TimetableGenerationRequest,
    service: TimetableGenerationService = Depends(get_timetable_generation_service),
) -> TimetableGenerationResponse:
    result = service.generate_for_session(
        session_id=request.session_id,
        course_load_target=request.course_load_target(),
        hard_conditions=request.hard_conditions,
        preference_prompt=request.preference_prompt,
        max_candidates=request.max_candidates,
    )
    session = service.store.get(request.session_id, touch=False)
    return TimetableGenerationResponse.model_validate(
        {**result.model_dump(), "session_stage": session.session_stage}
    )


@router.post("/rank", response_model=TimetableRankingResponse)
def rank_timetable_candidates(
    request: TimetableRankingRequest,
    service: TimetableRankingService = Depends(get_timetable_ranking_service),
) -> TimetableRankingResponse:
    _validate_top_n(request.top_n)
    try:
        template = normalize_ranking_template(request.template)
    except ValueError as exc:
        raise AppError(
            "UNKNOWN_RANKING_TEMPLATE",
            "지원하지 않는 랭킹 템플릿입니다.",
            status_code=400,
        ) from exc

    try:
        result = service.rank_for_session(
            session_id=request.session_id,
            template=template,
            top_n=request.top_n,
        )
        session = service.store.get(request.session_id, touch=False)
        template_definition = service.template_service.get_definition(result.template)
    except SessionNotFoundError as exc:
        raise AppError(
            "SESSION_NOT_FOUND",
            "세션을 찾을 수 없거나 만료되었습니다.",
            status_code=404,
        ) from exc
    except InvalidRankingSessionStageError as exc:
        raise AppError(
            "INVALID_SESSION_STAGE",
            "시간표 후보 생성이 완료된 세션에서만 랭킹할 수 있습니다.",
            status_code=409,
        ) from exc
    except NoGeneratedCandidatesError as exc:
        raise AppError(
            "NO_GENERATED_CANDIDATES",
            "랭킹할 시간표 후보가 세션에 없습니다.",
            status_code=409,
        ) from exc
    except NoRankableCandidatesError as exc:
        raise AppError(
            "NO_RANKABLE_CANDIDATES",
            "하드 조건을 통과한 랭킹 가능 후보가 없습니다.",
            status_code=409,
        ) from exc
    except ValueError as exc:
        raise AppError(
            "RANKING_FAILED",
            "시간표 후보 랭킹에 실패했습니다.",
            status_code=500,
        ) from exc
    except TimetableRankingError as exc:
        raise AppError(
            "RANKING_FAILED",
            "시간표 후보 랭킹에 실패했습니다.",
            status_code=500,
        ) from exc

    candidate_ids_by_sections = _candidate_ids_by_sections(session.generated_timetable_candidates)
    ranked_candidates = [
        RankedTimetableResponse(
            candidate_id=_ranked_candidate_id(item.timetable, candidate_ids_by_sections),
            rank=item.timetable.rank,
            timetable=item.timetable,
            raw_score=item.raw_score,
            score_components=item.score_components,
            load_satisfaction=item.load_satisfaction,
        )
        for item in result.ranked_candidates
    ]
    return TimetableRankingResponse(
        session_id=request.session_id,
        template=result.template,
        template_name=template_definition.name,
        template_description=template_definition.description,
        ranked_candidates=ranked_candidates,
        requested_top_n=request.top_n,
        returned_count=len(ranked_candidates),
        total_candidate_count=result.total_candidate_count,
        diagnostics=result.diagnostics,
        unsupported_conditions=session.preference_unsupported_conditions,
        warnings=session.preference_warnings,
        session_stage=session.session_stage,
    )


def _validate_top_n(top_n: int) -> None:
    if not 1 <= top_n <= 10:
        raise AppError(
            "INVALID_TOP_N",
            "top_n은 1 이상 10 이하로 요청해 주세요.",
            status_code=400,
        )


def _candidate_ids_by_sections(candidates: list[object]) -> dict[tuple[str, ...], str]:
    result: dict[tuple[str, ...], str] = {}
    for candidate in candidates:
        section_ids = getattr(candidate, "section_ids", None)
        candidate_id = getattr(candidate, "candidate_id", None)
        if not section_ids or not candidate_id:
            continue
        result[tuple(sorted(str(section_id) for section_id in section_ids))] = str(candidate_id)
    return result


def _ranked_candidate_id(
    timetable: Timetable,
    candidate_ids_by_sections: dict[tuple[str, ...], str],
) -> str:
    section_ids = [_course_section_identity(course) for course in timetable.courses]
    return candidate_ids_by_sections.get(
        tuple(sorted(section_ids)),
        legacy_candidate_id_for_courses(section_ids),
    )


def _course_section_identity(course: object) -> str:
    course_id = str(getattr(course, "course_id"))
    division = str(getattr(course, "division", "") or "")
    return f"{course_id}:{division}" if division else course_id
