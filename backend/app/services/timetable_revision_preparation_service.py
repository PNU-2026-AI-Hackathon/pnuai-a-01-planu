"""Deterministic preparation for selected-timetable revisions."""

from __future__ import annotations

from ..models import PlanuSessionState, time_to_minutes
from ..models.timetable_generation import SectionSource, TimetableGenerationRequest
from ..models.timetable_revision import (
    TimetableRevisionPreparationResult,
    TimetableRevisionRequest,
)
from ..repositories import CatalogRepository
from .session_service import SessionService


class TimetableRevisionPreparationService:
    """Prepare a generation request without doing generation, ranking, or NLP."""

    def __init__(
        self,
        *,
        session_service: SessionService,
        catalog_repository: CatalogRepository,
    ) -> None:
        self._session_service = session_service
        self._catalog_repository = catalog_repository

    def prepare(
        self,
        request: TimetableRevisionRequest,
    ) -> TimetableRevisionPreparationResult:
        state = self._session_service.get_session(request.session_id)
        selected = state.selected_timetable
        if selected is None:
            return TimetableRevisionPreparationResult(
                success=False,
                session_id=request.session_id,
                needs_confirmation=True,
                confirmation_reasons=["현재 선택된 시간표가 없습니다."],
                errors=["selected timetable is required"],
                message="선택된 시간표가 없어 revision을 준비할 수 없습니다.",
            )
        if (
            request.base_candidate_id is not None
            and request.base_candidate_id != selected.candidate_id
        ):
            return TimetableRevisionPreparationResult(
                success=False,
                session_id=request.session_id,
                base_candidate_id=selected.candidate_id,
                needs_confirmation=True,
                confirmation_reasons=["요청한 base_candidate_id가 현재 선택 후보와 다릅니다."],
                errors=["base_candidate_id mismatch"],
                message="현재 선택된 시간표를 다시 확인해야 합니다.",
            )

        hard = state.hard_constraints
        replace_section_ids = set(request.replace_section_ids)
        excluded_section_ids = set(request.excluded_section_ids)
        replace_course_ids = set(request.replace_course_ids)
        excluded_course_ids = set(request.excluded_course_ids)
        fixed_section_ids = set(selected.fixed_section_ids)
        source_by_section_id = {source.section_id: source for source in selected.section_sources}
        course_by_section_id = self._course_by_section_id(selected.section_sources)

        locked_sources: list[SectionSource] = []
        locked_section_ids: list[str] = []
        replaceable_section_ids: list[str] = []
        confirmation_reasons: list[str] = []
        for section_id in selected.section_ids:
            course_id = course_by_section_id.get(section_id)
            source = source_by_section_id.get(section_id)
            targeted = (
                section_id in replace_section_ids
                or section_id in excluded_section_ids
                or (course_id is not None and course_id in replace_course_ids)
                or (course_id is not None and course_id in excluded_course_ids)
            )
            violates_hard = source is not None and self._violates_hard(source, hard)
            if targeted and section_id in fixed_section_ids:
                confirmation_reasons.append(
                    "\ud655\uc815 \uc804\uacf5 \uacfc\ubaa9\uc740 \ubd80\ubd84 \uc218\uc815\uc73c\ub85c \uad50\uccb4\ud560 \uc218 \uc5c6\uc2b5\ub2c8\ub2e4. "
                    "\uc804\uacf5 \uad6c\uc131\uc744 \ubcc0\uacbd\ud558\ub824\uba74 \uc804\uacf5 \uc120\ud0dd\uc744 \ub2e4\uc2dc \uc124\uc815\ud574 \uc8fc\uc138\uc694."
                )
            if violates_hard and section_id in fixed_section_ids:
                confirmation_reasons.append(
                    f"\ud655\uc815 \uc804\uacf5 \ubd84\ubc18 {section_id}\uc774 \ud604\uc7ac Hard \uc870\uac74\uacfc \ucda9\ub3cc\ud569\ub2c8\ub2e4. "
                    "\uc804\uacf5 \uc120\ud0dd \ub610\ub294 \uc804\uccb4 \uc870\uac74\uc744 \ub2e4\uc2dc \ud655\uc778\ud574 \uc8fc\uc138\uc694."
                )
            if targeted and section_id not in fixed_section_ids:
                replaceable_section_ids.append(section_id)
                continue
            if violates_hard and section_id not in fixed_section_ids:
                replaceable_section_ids.append(section_id)
                continue
            if source is not None:
                locked_sources.append(source)
            locked_section_ids.append(section_id)

        generation_request = None
        if not confirmation_reasons:
            generation_request = TimetableGenerationRequest(
                session_id=request.session_id,
                fixed_section_sources=locked_sources,
                required_course_ids=list(dict.fromkeys(request.required_course_ids)),
                excluded_course_ids=list(
                    dict.fromkeys(
                        [
                            *state.hard_constraints.excluded_course_ids,
                            *request.excluded_course_ids,
                        ]
                    )
                ),
                required_free_days=list(hard.required_free_days),
                earliest_start_time=hard.earliest_start_time,
                latest_end_time=hard.latest_end_time,
                department=state.department,
                target_additional_course_count=request.target_additional_course_count,
                max_results=request.max_results,
            )

        additional_discovery = self._additional_discovery(
            state,
            request,
            replaceable_section_ids,
            course_by_section_id,
        )
        return TimetableRevisionPreparationResult(
            success=not confirmation_reasons,
            session_id=request.session_id,
            base_candidate_id=selected.candidate_id,
            selected_timetable_status=(
                None
                if state.selected_timetable_status is None
                else state.selected_timetable_status.value
            ),
            locked_section_ids=locked_section_ids,
            locked_section_sources=locked_sources,
            replaceable_section_ids=replaceable_section_ids,
            excluded_section_ids=list(dict.fromkeys([*excluded_section_ids, *replaceable_section_ids])),
            excluded_course_ids=list(dict.fromkeys(request.excluded_course_ids)),
            required_course_ids=list(dict.fromkeys(request.required_course_ids)),
            additional_discovery=additional_discovery,
            generation_request=generation_request,
            needs_confirmation=bool(confirmation_reasons),
            confirmation_reasons=confirmation_reasons,
            message=(
                "revision 준비에 확인이 필요합니다."
                if confirmation_reasons
                else "revision 생성을 위한 준비가 완료되었습니다."
            ),
        )

    def _course_by_section_id(self, sources: list[SectionSource]) -> dict[str, str]:
        mapping: dict[str, str] = {}
        for source in sources:
            try:
                section = self._catalog_repository.get_section(
                    source.catalog_id,
                    source.section_id,
                )
            except Exception:
                continue
            mapping[source.section_id] = section.course_id
        return mapping

    def _violates_hard(self, source: SectionSource, hard) -> bool:
        try:
            section = self._catalog_repository.get_section(source.catalog_id, source.section_id)
        except Exception:
            return False
        if section.course_id in hard.excluded_course_ids:
            return True
        if any(time.day in hard.required_free_days for time in section.class_times):
            return True
        if hard.earliest_start_time is not None:
            earliest = time_to_minutes(hard.earliest_start_time)
            if any(time_to_minutes(time.start) < earliest for time in section.class_times):
                return True
        if hard.latest_end_time is not None:
            latest = time_to_minutes(hard.latest_end_time)
            if any(time_to_minutes(time.end) > latest for time in section.class_times):
                return True
        return False

    def _additional_discovery(
        self,
        state: PlanuSessionState,
        request: TimetableRevisionRequest,
        replaceable_section_ids: list[str],
        course_by_section_id: dict[str, str],
    ) -> list[dict[str, object]]:
        if not replaceable_section_ids and not request.required_course_ids:
            return []
        catalog_id = state.elective_catalog_id
        if catalog_id is None:
            return [{"reason": "elective_catalog_id_required"}]
        course_ids = [
            course_by_section_id[section_id]
            for section_id in replaceable_section_ids
            if section_id in course_by_section_id
        ]
        return [
            {
                "catalog_id": catalog_id,
                "replace_course_ids": list(dict.fromkeys([*request.replace_course_ids, *course_ids])),
                "excluded_course_ids": list(dict.fromkeys(request.excluded_course_ids)),
                "excluded_section_ids": list(dict.fromkeys([*request.excluded_section_ids, *replaceable_section_ids])),
            }
        ]
