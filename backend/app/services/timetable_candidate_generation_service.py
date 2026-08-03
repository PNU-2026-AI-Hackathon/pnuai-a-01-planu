"""Agent-callable timetable candidate generation from prepared section ids."""

from __future__ import annotations

from collections import Counter

from ..models.course_discovery import CourseSection
from ..models.timetable_generation import (
    GeneratedTimetableCandidate,
    GenerationFailureCode,
    GenerationFailureReason,
    SearchTerminationReason,
    SectionSource,
    TimetableGenerationError,
    TimetableGenerationRequest,
    TimetableGenerationResult,
    TimetableValidationResult,
    TimetableViolationCode,
)
from ..repositories.catalog_repository import CatalogRepository
from ..repositories.exceptions import CatalogNotFoundError, SectionNotFoundError
from .timetable_validation_service import TimetableValidationService


class TimetableCandidateGenerationService:
    """Generate concrete section combinations using hard-rule backtracking."""

    def __init__(
        self,
        *,
        catalog_repository: CatalogRepository,
        validation_service: TimetableValidationService | None = None,
        max_failure_examples_per_code: int = 3,
    ) -> None:
        self.catalog_repository = catalog_repository
        self.validation_service = validation_service or TimetableValidationService()
        self.max_failure_examples_per_code = max_failure_examples_per_code

    def generate(
        self,
        request: TimetableGenerationRequest,
    ) -> TimetableGenerationResult:
        failures = _FailureCollector(self.max_failure_examples_per_code)
        try:
            fixed_sections = self._resolve_sources(request.fixed_section_sources)
            candidates_by_course = self._resolve_candidate_sections(request)
        except (CatalogNotFoundError, SectionNotFoundError, ValueError) as exc:
            failures.add(
                GenerationFailureCode.INVALID_GENERATION_REQUEST,
                str(exc),
                constraint="section_sources",
            )
            return self._result(
                candidates=[],
                nodes=0,
                termination_reason=SearchTerminationReason.SEARCH_EXHAUSTED,
                failures=failures,
                error=TimetableGenerationError(
                    code=GenerationFailureCode.INVALID_GENERATION_REQUEST,
                    message=str(exc),
                ),
            )

        fixed_validation = self.validation_service.validate_sections(
            fixed_sections,
            required_course_ids=[],
            excluded_course_ids=request.excluded_course_ids,
            required_free_days=request.required_free_days,
            earliest_start_time=request.earliest_start_time,
            latest_end_time=request.latest_end_time,
            department=request.department,
        )
        if not fixed_validation.valid:
            for violation in fixed_validation.violations:
                failures.add(
                    _failure_code_for_violation(violation.code, fixed=True),
                    violation.message,
                    course_id=violation.course_id,
                    section_id=violation.section_id,
                    conflicting_section_ids=violation.conflicting_section_ids,
                    constraint=violation.constraint,
                )
            return self._result(
                candidates=[],
                nodes=0,
                termination_reason=SearchTerminationReason.SEARCH_EXHAUSTED,
                failures=failures,
                error=TimetableGenerationError(
                    code=GenerationFailureCode.FIXED_TIMETABLE_CONFLICT,
                    message="고정 분반 시간표가 Hard 조건을 만족하지 않습니다.",
                ),
            )

        fixed_course_ids = {section.course_id for section in fixed_sections}
        required_course_ids = set(request.required_course_ids)
        unresolved_required = required_course_ids - fixed_course_ids
        available_course_ids = set(candidates_by_course)
        missing_required = unresolved_required - available_course_ids
        for course_id in sorted(missing_required):
            failures.add(
                GenerationFailureCode.REQUIRED_COURSE_UNAVAILABLE,
                "필수 과목이 고정 분반 또는 후보 분반 목록에 없습니다.",
                course_id=course_id,
                constraint="required_course_ids",
            )
        if missing_required:
            return self._result(
                candidates=[],
                nodes=0,
                termination_reason=SearchTerminationReason.SEARCH_EXHAUSTED,
                failures=failures,
                error=TimetableGenerationError(
                    code=GenerationFailureCode.REQUIRED_COURSE_UNAVAILABLE,
                    message="필수 과목을 생성 요청에서 해결할 수 없습니다.",
                ),
            )

        candidates_by_course = {
            course_id: sections
            for course_id, sections in candidates_by_course.items()
            if course_id not in request.excluded_course_ids
            and course_id not in fixed_course_ids
        }
        ordered_course_ids = [
            course_id
            for course_id in request.ordered_candidate_course_ids
            if course_id in candidates_by_course
        ]
        # Explore constrained courses first while keeping the order deterministic.
        ordered_course_ids.sort(
            key=lambda course_id: (
                course_id not in unresolved_required,
                len(candidates_by_course[course_id]),
                course_id,
            )
        )

        target_count = request.target_additional_course_count
        if target_count is None and request.target_additional_credits is None:
            target_count = 1
        if target_count is not None and len(ordered_course_ids) < target_count:
            failures.add(
                GenerationFailureCode.INSUFFICIENT_CANDIDATE_COURSES,
                "목표 과목 수보다 후보 과목 수가 적습니다.",
                constraint="target_additional_course_count",
                count=target_count - len(ordered_course_ids),
            )

        results: list[GeneratedTimetableCandidate] = []
        seen_candidate_ids: set[str] = set()
        nodes = 0
        termination_reason = SearchTerminationReason.SEARCH_EXHAUSTED

        def backtrack(
            index: int,
            selected: list[CourseSection],
            selected_course_ids: set[str],
        ) -> None:
            nonlocal nodes, termination_reason
            if termination_reason is not SearchTerminationReason.SEARCH_EXHAUSTED:
                return
            if nodes >= request.max_search_nodes:
                termination_reason = SearchTerminationReason.MAX_SEARCH_NODES_REACHED
                failures.add(
                    GenerationFailureCode.SEARCH_LIMIT_REACHED,
                    "탐색 노드 제한에 도달해 생성을 중단했습니다.",
                    constraint="max_search_nodes",
                    count=request.max_search_nodes,
                )
                return

            selected_credits = sum(section.credit for section in selected)
            remaining_courses = ordered_course_ids[index:]
            unreachable_reason = _get_unreachable_target_reason(
                selected_count=len(selected),
                selected_credits=selected_credits,
                remaining_sections_by_course=[
                    candidates_by_course[course_id] for course_id in remaining_courses
                ],
                target_count=target_count,
                target_credits=request.target_additional_credits,
            )
            if unreachable_reason is not None:
                message, constraint = _unreachable_target_message(unreachable_reason)
                failures.add(
                    unreachable_reason,
                    message,
                    constraint=constraint,
                )
                return

            unresolved = unresolved_required - selected_course_ids
            if not unresolved:
                if _targets_met(
                    selected,
                    target_count=target_count,
                    target_credits=request.target_additional_credits,
                ):
                    self._append_candidate(
                        results,
                        seen_candidate_ids=seen_candidate_ids,
                        fixed_sections=fixed_sections,
                        added_sections=selected,
                        request=request,
                    )
                    if len(results) >= request.max_results:
                        termination_reason = SearchTerminationReason.MAX_RESULTS_REACHED
                        return
                    if target_count is not None and len(selected) >= target_count:
                        return
                elif index >= len(ordered_course_ids):
                    code = _unmet_target_reason(
                        selected,
                        target_count=target_count,
                        target_credits=request.target_additional_credits,
                    )
                    message, constraint = _unreachable_target_message(code)
                    failures.add(
                        code,
                        message,
                        constraint=constraint,
                    )
                if index >= len(ordered_course_ids):
                    return

            if index >= len(ordered_course_ids):
                if unresolved:
                    for course_id in sorted(unresolved):
                        failures.add(
                            GenerationFailureCode.REQUIRED_COURSE_UNAVAILABLE,
                            "필수 과목의 모든 분반이 Hard 조건에 의해 제외되었습니다.",
                            course_id=course_id,
                        )
                return

            course_id = ordered_course_ids[index]
            must_take = course_id in unresolved_required
            if not must_take:
                backtrack(index + 1, selected, selected_course_ids)
                if termination_reason is not SearchTerminationReason.SEARCH_EXHAUSTED:
                    return

            accepted_branch = False
            for section in candidates_by_course[course_id]:
                if termination_reason is not SearchTerminationReason.SEARCH_EXHAUSTED:
                    return
                if nodes >= request.max_search_nodes:
                    termination_reason = SearchTerminationReason.MAX_SEARCH_NODES_REACHED
                    failures.add(
                        GenerationFailureCode.SEARCH_LIMIT_REACHED,
                        "탐색 노드 제한에 도달해 생성을 중단했습니다.",
                        constraint="max_search_nodes",
                        count=request.max_search_nodes,
                    )
                    return
                nodes += 1
                validation = self.validation_service.can_add_section(
                    [*fixed_sections, *selected],
                    section,
                    required_course_ids=[],
                    excluded_course_ids=request.excluded_course_ids,
                    required_free_days=request.required_free_days,
                    earliest_start_time=request.earliest_start_time,
                    latest_end_time=request.latest_end_time,
                    department=request.department,
                )
                if not validation.valid:
                    for violation in validation.violations:
                        if (
                            violation.section_id == section.section_id
                            or section.section_id in violation.conflicting_section_ids
                        ):
                            failures.add(
                                _failure_code_for_violation(violation.code),
                                violation.message,
                                course_id=section.course_id,
                                section_id=section.section_id,
                                conflicting_section_ids=violation.conflicting_section_ids,
                                constraint=violation.constraint,
                            )
                    if nodes >= request.max_search_nodes:
                        termination_reason = SearchTerminationReason.MAX_SEARCH_NODES_REACHED
                        failures.add(
                            GenerationFailureCode.SEARCH_LIMIT_REACHED,
                            "탐색 노드 제한에 도달해 생성을 중단했습니다.",
                            constraint="max_search_nodes",
                            count=request.max_search_nodes,
                        )
                        return
                    continue
                accepted_branch = True
                backtrack(
                    index + 1,
                    [*selected, section],
                    {*selected_course_ids, course_id},
                )
                if termination_reason is not SearchTerminationReason.SEARCH_EXHAUSTED:
                    return
            if must_take and not accepted_branch:
                failures.add(
                    GenerationFailureCode.REQUIRED_COURSE_UNAVAILABLE,
                    "필수 과목의 모든 분반이 Hard 조건에 의해 제외되었습니다.",
                    course_id=course_id,
                    constraint="required_course_ids",
                )

        backtrack(0, [], set())
        if not results and not failures.has_errors:
            failures.add(
                GenerationFailureCode.TARGET_COURSE_COUNT_UNREACHABLE,
                "조건을 만족하는 시간표 후보가 없습니다.",
                constraint="target",
            )
        return self._result(
            candidates=results,
            nodes=nodes,
            termination_reason=termination_reason,
            failures=failures,
            error=None,
        )

    def _resolve_sources(self, sources: list[SectionSource]) -> list[CourseSection]:
        sections = [
            self.catalog_repository.get_section(source.catalog_id, source.section_id)
            for source in sources
        ]
        return sorted(sections, key=lambda section: (section.course_id, section.section_id))

    def _resolve_candidate_sections(
        self,
        request: TimetableGenerationRequest,
    ) -> dict[str, list[CourseSection]]:
        result: dict[str, list[CourseSection]] = {}
        for course_id in request.ordered_candidate_course_ids:
            sections = self._resolve_sources(
                request.candidate_section_sources_by_course[course_id]
            )
            for section in sections:
                if section.course_id != course_id:
                    raise ValueError(
                        f"section {section.section_id} belongs to {section.course_id}, not {course_id}"
                    )
            result[course_id] = sorted(
                sections,
                key=lambda section: (
                    min(
                        (meeting.day.value, meeting.start_minutes)
                        for meeting in section.class_times
                    ),
                    section.section_id,
                ),
            )
        return result

    def _append_candidate(
        self,
        results: list[GeneratedTimetableCandidate],
        *,
        seen_candidate_ids: set[str],
        fixed_sections: list[CourseSection],
        added_sections: list[CourseSection],
        request: TimetableGenerationRequest,
    ) -> None:
        all_sections = [*fixed_sections, *added_sections]
        validation = self.validation_service.validate_sections(
            all_sections,
            required_course_ids=request.required_course_ids,
            excluded_course_ids=request.excluded_course_ids,
            required_free_days=request.required_free_days,
            earliest_start_time=request.earliest_start_time,
            latest_end_time=request.latest_end_time,
            department=request.department,
        )
        if not validation.valid:
            return
        ordered_added_sections = sorted(
            added_sections,
            key=lambda section: (section.course_id, section.section_id),
        )
        ordered_sections = [*fixed_sections, *ordered_added_sections]
        section_ids = [section.section_id for section in ordered_sections]
        candidate_id = GeneratedTimetableCandidate.build_id(section_ids)
        if candidate_id in seen_candidate_ids:
            return
        seen_candidate_ids.add(candidate_id)
        results.append(GeneratedTimetableCandidate(
            candidate_id=candidate_id,
            section_ids=section_ids,
            fixed_section_ids=[section.section_id for section in fixed_sections],
            added_section_ids=[section.section_id for section in ordered_added_sections],
            course_ids=[section.course_id for section in ordered_sections],
            total_credits=sum(section.credit for section in all_sections),
            validation=validation,
            generation_order=len(results) + 1,
        ))

    @staticmethod
    def _result(
        *,
        candidates: list[GeneratedTimetableCandidate],
        nodes: int,
        termination_reason: SearchTerminationReason,
        failures: "_FailureCollector",
        error: TimetableGenerationError | None,
    ) -> TimetableGenerationResult:
        success = bool(candidates) and error is None
        message = (
            f"{len(candidates)}개 시간표 후보를 생성했습니다."
            if candidates
            else "조건을 만족하는 시간표 후보를 생성하지 못했습니다."
        )
        return TimetableGenerationResult(
            success=success,
            candidates=candidates,
            total_candidates_found=len(candidates),
            search_nodes_visited=nodes,
            search_truncated=termination_reason
            is not SearchTerminationReason.SEARCH_EXHAUSTED,
            termination_reason=termination_reason,
            failure_reasons=failures.reasons(),
            message=message,
            error=error,
        )


class _FailureCollector:
    def __init__(self, example_limit: int) -> None:
        self.example_limit = example_limit
        self.counts: Counter[GenerationFailureCode] = Counter()
        self.examples: dict[GenerationFailureCode, list[GenerationFailureReason]] = {}

    @property
    def has_errors(self) -> bool:
        return bool(self.counts)

    def add(
        self,
        code: GenerationFailureCode,
        message: str,
        *,
        course_id: str | None = None,
        section_id: str | None = None,
        conflicting_section_ids: list[str] | None = None,
        constraint: str | None = None,
        count: int = 1,
    ) -> None:
        self.counts[code] += count
        examples = self.examples.setdefault(code, [])
        if len(examples) < self.example_limit:
            examples.append(GenerationFailureReason(
                code=code,
                message=message,
                course_id=course_id,
                section_id=section_id,
                conflicting_section_ids=conflicting_section_ids or [],
                constraint=constraint,
                count=count,
            ))

    def reasons(self) -> list[GenerationFailureReason]:
        reasons: list[GenerationFailureReason] = []
        for code in sorted(self.counts, key=lambda item: item.value):
            examples = self.examples.get(code) or [
                GenerationFailureReason(
                    code=code,
                    message=code.value,
                    count=self.counts[code],
                )
            ]
            for index, example in enumerate(examples):
                reasons.append(
                    example.model_copy(
                        update={"count": self.counts[code] if index == 0 else example.count}
                    )
                )
        return reasons


def _failure_code_for_violation(
    code: TimetableViolationCode,
    *,
    fixed: bool = False,
) -> GenerationFailureCode:
    if fixed:
        return GenerationFailureCode.FIXED_TIMETABLE_CONFLICT
    return {
        TimetableViolationCode.INVALID_VALIDATION_REQUEST: GenerationFailureCode.INVALID_GENERATION_REQUEST,
        TimetableViolationCode.TIME_CONFLICT: GenerationFailureCode.TIME_CONFLICT,
        TimetableViolationCode.DUPLICATE_COURSE: GenerationFailureCode.DUPLICATE_COURSE,
        TimetableViolationCode.MISSING_REQUIRED_COURSE: GenerationFailureCode.REQUIRED_COURSE_UNAVAILABLE,
        TimetableViolationCode.EXCLUDED_COURSE_INCLUDED: GenerationFailureCode.INVALID_GENERATION_REQUEST,
        TimetableViolationCode.REQUIRED_FREE_DAY_VIOLATION: GenerationFailureCode.REQUIRED_FREE_DAY_VIOLATION,
        TimetableViolationCode.EARLIEST_START_VIOLATION: GenerationFailureCode.EARLIEST_START_VIOLATION,
        TimetableViolationCode.LATEST_END_VIOLATION: GenerationFailureCode.LATEST_END_VIOLATION,
        TimetableViolationCode.DEPARTMENT_INELIGIBLE: GenerationFailureCode.DEPARTMENT_INELIGIBLE,
        TimetableViolationCode.CAMPUS_MOVEMENT_VIOLATION: GenerationFailureCode.CAMPUS_MOVEMENT_VIOLATION,
    }[code]


def _targets_met(
    selected: list[CourseSection],
    *,
    target_count: int | None,
    target_credits: float | None,
) -> bool:
    if target_count is not None and len(selected) != target_count:
        return False
    if target_credits is not None and sum(section.credit for section in selected) < target_credits:
        return False
    return True


def _get_unreachable_target_reason(
    *,
    selected_count: int,
    selected_credits: float,
    remaining_sections_by_course: list[list[CourseSection]],
    target_count: int | None,
    target_credits: float | None,
) -> GenerationFailureCode | None:
    if target_count is not None and selected_count > target_count:
        return GenerationFailureCode.TARGET_COURSE_COUNT_UNREACHABLE
    if target_count is not None and selected_count + len(remaining_sections_by_course) < target_count:
        return GenerationFailureCode.TARGET_COURSE_COUNT_UNREACHABLE
    if target_credits is not None:
        max_remaining = sum(
            max((section.credit for section in sections), default=0)
            for sections in remaining_sections_by_course
        )
        if selected_credits + max_remaining < target_credits:
            return GenerationFailureCode.TARGET_CREDITS_UNREACHABLE
    return None


def _unmet_target_reason(
    selected: list[CourseSection],
    *,
    target_count: int | None,
    target_credits: float | None,
) -> GenerationFailureCode:
    if target_count is not None and len(selected) != target_count:
        return GenerationFailureCode.TARGET_COURSE_COUNT_UNREACHABLE
    if target_credits is not None and sum(section.credit for section in selected) < target_credits:
        return GenerationFailureCode.TARGET_CREDITS_UNREACHABLE
    return GenerationFailureCode.TARGET_COURSE_COUNT_UNREACHABLE


def _unreachable_target_message(
    code: GenerationFailureCode,
) -> tuple[str, str]:
    if code is GenerationFailureCode.TARGET_CREDITS_UNREACHABLE:
        return (
            "남은 후보의 최대 학점을 포함해도 목표 학점을 만족할 수 없습니다.",
            "target_additional_credits",
        )
    return (
        "남은 후보로 목표 과목 수를 만족할 수 없습니다.",
        "target_additional_course_count",
    )
