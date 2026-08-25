"""Deterministic condition summary and generation readiness service."""

from __future__ import annotations

from collections.abc import Iterable

from ..models import Day, PlanuSessionState
from ..repositories import CatalogNotFoundError, CourseNotFoundError
from ..repositories.session_store_catalog_repository import SessionStoreCatalogRepository
from ..schemas.condition_summary_schema import (
    ConditionCourseRefDto,
    ConditionItemStatus,
    ConditionSummaryDto,
    ConditionSummaryItemDto,
    GenerationReadinessDto,
    MissingGenerationRequirementDto,
)


_DAY_LABELS = {
    Day.MON: "월요일",
    Day.TUE: "화요일",
    Day.WED: "수요일",
    Day.THU: "목요일",
    Day.FRI: "금요일",
    Day.SAT: "토요일",
    Day.SUN: "일요일",
}


class ConditionSummaryService:
    """Build frontend-ready condition summaries from persisted session state."""

    def __init__(self, catalog_repository: SessionStoreCatalogRepository | None = None) -> None:
        self._catalog_repository = catalog_repository

    def summarize(self, state: PlanuSessionState) -> ConditionSummaryDto:
        course_refs = self._course_refs(state)
        readiness = self._generation_readiness(state)
        return ConditionSummaryDto(
            hard_constraints=self._hard_constraints(state, course_refs),
            soft_preferences=self._soft_preferences(state, course_refs),
            selected_major_courses=self._refs_for_ids(
                state.selected_major_course_ids,
                course_refs,
            ),
            generation_readiness=readiness,
        )

    def _hard_constraints(
        self,
        state: PlanuSessionState,
        course_refs: dict[str, ConditionCourseRefDto],
    ) -> list[ConditionSummaryItemDto]:
        hard = state.hard_constraints
        return [
            self._course_item(
                "required_course_ids",
                "필수 과목",
                hard.required_course_ids,
                course_refs,
                empty_label="없음",
            ),
            self._course_item(
                "excluded_course_ids",
                "제외 과목",
                hard.excluded_course_ids,
                course_refs,
                empty_label="없음",
            ),
            self._days_item("required_free_days", "공강 요일", hard.required_free_days),
            self._time_item(
                "earliest_start_time",
                "시작 시간 제한",
                hard.earliest_start_time,
                suffix=" 이후",
            ),
            self._time_item(
                "latest_end_time",
                "종료 시간 제한",
                hard.latest_end_time,
                suffix=" 이전",
            ),
            self._credit_item(
                "min_credit",
                "최소 학점",
                hard.min_credit,
                inclusive=hard.min_credit_inclusive,
                lower_bound=True,
            ),
            self._credit_item(
                "max_credit",
                "최대 학점",
                hard.max_credit,
                inclusive=hard.max_credit_inclusive,
                lower_bound=False,
            ),
            self._areas_item(
                "excluded_elective_areas",
                "제외 교양 영역",
                hard.excluded_elective_areas,
            ),
        ]

    def _soft_preferences(
        self,
        state: PlanuSessionState,
        course_refs: dict[str, ConditionCourseRefDto],
    ) -> list[ConditionSummaryItemDto]:
        soft = state.soft_preferences
        compact = soft.compact_schedule
        if compact is None:
            compact_status = ConditionItemStatus.UNSET
            compact_display = None
        else:
            compact_status = ConditionItemStatus.SET
            compact_display = "몰아듣기 선호" if compact else "연강 회피"
        return [
            self._days_item("preferred_free_days", "선호 공강", soft.preferred_free_days),
            self._time_item(
                "preferred_earliest_start_time",
                "늦은 시작",
                soft.preferred_earliest_start_time,
                suffix=" 이후 선호",
            ),
            self._time_item(
                "preferred_latest_end_time",
                "이른 종료",
                soft.preferred_latest_end_time,
                suffix=" 이전 선호",
            ),
            self._course_item(
                "preferred_course_ids",
                "선호 과목",
                soft.preferred_course_ids,
                course_refs,
            ),
            self._course_item(
                "disliked_course_ids",
                "비선호 과목",
                soft.disliked_course_ids,
                course_refs,
            ),
            ConditionSummaryItemDto(
                key="compact_schedule",
                label="몰아듣기",
                status=compact_status,
                display_value=compact_display,
                raw_value=compact,
            ),
        ]

    def _generation_readiness(self, state: PlanuSessionState) -> GenerationReadinessDto:
        missing: list[MissingGenerationRequirementDto] = []
        if state.department is None:
            missing.append(
                MissingGenerationRequirementDto(
                    code="DEPARTMENT_REQUIRED",
                    message="학과 설정이 필요합니다.",
                )
            )
        if state.major_catalog_id is None:
            missing.append(
                MissingGenerationRequirementDto(
                    code="MAJOR_CATALOG_REQUIRED",
                    message="전공 수강편람이 필요합니다.",
                )
            )
        elif self._catalog_repository is not None and not self._catalog_repository.exists(state.major_catalog_id):
            missing.append(
                MissingGenerationRequirementDto(
                    code="MAJOR_CATALOG_NOT_FOUND",
                    message="전공 수강편람 데이터를 찾을 수 없습니다.",
                )
            )
        if not state.selected_major_course_ids:
            missing.append(
                MissingGenerationRequirementDto(
                    code="MAJOR_SELECTION_REQUIRED",
                    message="전공 과목 선택이 필요합니다.",
                )
            )
        elif state.major_catalog_id is not None and self._catalog_repository is not None:
            for course_id in state.selected_major_course_ids:
                try:
                    self._catalog_repository.get_course_sections(state.major_catalog_id, course_id)
                except (CatalogNotFoundError, CourseNotFoundError):
                    missing.append(
                        MissingGenerationRequirementDto(
                            code="SELECTED_MAJOR_SECTION_REQUIRED",
                            message=f"선택한 전공 과목의 분반 정보가 필요합니다: {course_id}",
                        )
                    )
        if (
            state.elective_catalog_id is not None
            and self._catalog_repository is not None
            and not self._catalog_repository.exists(state.elective_catalog_id)
        ):
            missing.append(
                MissingGenerationRequirementDto(
                    code="ELECTIVE_CATALOG_NOT_FOUND",
                    message="교양 수강편람 데이터를 찾을 수 없습니다.",
                )
            )
        generation_confirmed = state.generation_preferences_confirmed_at is not None
        return GenerationReadinessDto(
            ready=not missing,
            generation_confirmed=generation_confirmed,
            confirmed_at=state.generation_preferences_confirmed_at,
            confirmed_version=state.generation_preferences_confirmed_version,
            current_version=state.version,
            missing_requirements=missing,
        )

    def _course_refs(self, state: PlanuSessionState) -> dict[str, ConditionCourseRefDto]:
        ids = set(state.selected_major_course_ids)
        ids.update(state.hard_constraints.required_course_ids)
        ids.update(state.hard_constraints.excluded_course_ids)
        ids.update(state.soft_preferences.preferred_course_ids)
        ids.update(state.soft_preferences.disliked_course_ids)
        refs = {course_id: ConditionCourseRefDto(course_id=course_id) for course_id in ids}
        if self._catalog_repository is None:
            return refs
        for catalog_id in [state.major_catalog_id, state.elective_catalog_id, f"{state.session_id}:general"]:
            if catalog_id is None:
                continue
            try:
                sections = self._catalog_repository.list_sections(catalog_id)
            except CatalogNotFoundError:
                continue
            for section in sections:
                if section.course_id in refs and refs[section.course_id].course_name is None:
                    refs[section.course_id] = ConditionCourseRefDto(
                        course_id=section.course_id,
                        course_name=section.course_name,
                        course_code=section.course_code,
                    )
        return refs

    @staticmethod
    def _course_item(
        key: str,
        label: str,
        course_ids: Iterable[str],
        course_refs: dict[str, ConditionCourseRefDto],
        *,
        empty_label: str | None = None,
    ) -> ConditionSummaryItemDto:
        ids = list(course_ids)
        refs = ConditionSummaryService._refs_for_ids(ids, course_refs)
        if not ids:
            status = ConditionItemStatus.EMPTY if empty_label is not None else ConditionItemStatus.UNSET
            return ConditionSummaryItemDto(
                key=key,
                label=label,
                status=status,
                display_value=empty_label,
                course_refs=[],
                raw_value=[],
            )
        return ConditionSummaryItemDto(
            key=key,
            label=label,
            status=ConditionItemStatus.SET,
            display_value=", ".join(ref.course_name or ref.course_id for ref in refs),
            course_refs=refs,
            raw_value=ids,
        )

    @staticmethod
    def _days_item(key: str, label: str, days: Iterable[Day]) -> ConditionSummaryItemDto:
        values = list(days)
        if not values:
            return ConditionSummaryItemDto(
                key=key,
                label=label,
                status=ConditionItemStatus.UNSET,
                display_value=None,
                raw_value=[],
            )
        return ConditionSummaryItemDto(
            key=key,
            label=label,
            status=ConditionItemStatus.SET,
            display_value=", ".join(_DAY_LABELS[day] for day in values),
            raw_value=[day.value for day in values],
        )

    @staticmethod
    def _time_item(key: str, label: str, value: str | None, *, suffix: str) -> ConditionSummaryItemDto:
        if value is None:
            return ConditionSummaryItemDto(
                key=key,
                label=label,
                status=ConditionItemStatus.UNSET,
                display_value=None,
            )
        return ConditionSummaryItemDto(
            key=key,
            label=label,
            status=ConditionItemStatus.SET,
            display_value=f"{value}{suffix}",
            raw_value=value,
        )

    @staticmethod
    def _credit_item(
        key: str,
        label: str,
        value: float | None,
        *,
        inclusive: bool = True,
        lower_bound: bool = True,
    ) -> ConditionSummaryItemDto:
        if value is None:
            return ConditionSummaryItemDto(
                key=key,
                label=label,
                status=ConditionItemStatus.UNSET,
                display_value=None,
            )
        return ConditionSummaryItemDto(
            key=key,
            label=label,
            status=ConditionItemStatus.SET,
            display_value=f"{value:g}학점 {'이상' if lower_bound and inclusive else '초과' if lower_bound else '이하' if inclusive else '미만'}",
            raw_value=value,
            metadata={"inclusive": inclusive},
        )

    @staticmethod
    def _areas_item(key: str, label: str, areas: Iterable[int]) -> ConditionSummaryItemDto:
        values = list(dict.fromkeys(areas))
        if not values:
            return ConditionSummaryItemDto(
                key=key,
                label=label,
                status=ConditionItemStatus.UNSET,
                display_value=None,
                raw_value=[],
            )
        return ConditionSummaryItemDto(
            key=key,
            label=label,
            status=ConditionItemStatus.SET,
            display_value=", ".join(f"{area}영역" for area in values),
            raw_value=values,
        )

    @staticmethod
    def _refs_for_ids(
        course_ids: Iterable[str],
        course_refs: dict[str, ConditionCourseRefDto],
    ) -> list[ConditionCourseRefDto]:
        return [course_refs.get(course_id, ConditionCourseRefDto(course_id=course_id)) for course_id in course_ids]
