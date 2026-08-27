"""Generate valid timetable candidates from fixed majors and general courses."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from itertools import combinations, product
from math import ceil, floor
from time import perf_counter

from ..models.course import Category, Course
from ..models.course_load import CourseLoadTarget
from ..models.preference import PreferenceRules
from ..models.timetable import (
    CourseLoadSatisfaction,
    GenerationDiagnostic,
    Timetable,
    TimetableCandidate,
    TimetableGenerationCandidate,
    TimetableGenerationResult,
)
from .campus_rule_engine import CampusRuleEngine
from .timetable_ranker import TimetableRanker
from .timetable_validator import TimetableValidator


class TimetableGenerator:
    """Backtracking-style generator for PlaNU recommendation candidates."""

    def __init__(
        self,
        validator: TimetableValidator | None = None,
        *,
        campus_rule_engine: CampusRuleEngine | None = None,
        max_candidates: int = 200,
        min_credit: float | None = None,
        min_credit_inclusive: bool = True,
        max_credit: float | None = None,
        max_credit_inclusive: bool = True,
    ) -> None:
        if max_candidates <= 0:
            raise ValueError("max_candidates must be positive")
        self.validator = validator or TimetableValidator(
            campus_rule_engine,
            min_credit=min_credit,
            min_credit_inclusive=min_credit_inclusive,
            max_credit=max_credit,
            max_credit_inclusive=max_credit_inclusive,
        )
        self.max_candidates = max_candidates

    def generate(
        self,
        *,
        fixed_courses: Iterable[Course],
        general_required_candidates: Iterable[Course] = (),
        general_elective_candidates: Iterable[Course] = (),
        required_general_count: int = 0,
        elective_general_count: int = 0,
        max_candidates: int | None = None,
        min_credit: float | None = None,
        min_credit_inclusive: bool = True,
        max_credit: float | None = None,
        max_credit_inclusive: bool = True,
    ) -> list[TimetableCandidate]:
        if required_general_count < 0 or elective_general_count < 0:
            raise ValueError("general course counts must not be negative")

        fixed = list(fixed_courses)
        required_candidates = self._dedupe_by_course_identity(
            general_required_candidates
        )
        elective_candidates = self._dedupe_by_course_identity(
            general_elective_candidates
        )
        limit = self.max_candidates if max_candidates is None else max_candidates
        if limit <= 0:
            raise ValueError("max_candidates must be positive")

        candidates: list[TimetableCandidate] = []
        for required_group in combinations(required_candidates, required_general_count):
            if not self.validator.is_valid(required_group, fixed_courses=fixed):
                continue
            for elective_group in combinations(
                elective_candidates, elective_general_count
            ):
                selected = [*required_group, *elective_group]
                result = self.validator.validate(
                    selected,
                    fixed_courses=fixed,
                    min_credit=min_credit,
                    min_credit_inclusive=min_credit_inclusive,
                    max_credit=max_credit,
                    max_credit_inclusive=max_credit_inclusive,
                )
                if not result.valid:
                    continue
                candidates.append(Timetable(courses=[*fixed, *selected]))
                if len(candidates) >= limit:
                    return candidates
        return candidates

    def generate_detailed(
        self,
        *,
        fixed_major_courses: Iterable[Course],
        required_general_candidates: Iterable[Course] = (),
        elective_general_candidates: Iterable[Course] = (),
        course_load_target: CourseLoadTarget | None = None,
        hard_conditions: PreferenceRules | None = None,
        min_credit: float | None = None,
        min_credit_inclusive: bool = True,
        max_credit: float | None = None,
        max_credit_inclusive: bool = True,
        max_candidates: int | None = None,
    ) -> TimetableGenerationResult:
        """Generate valid candidates and objective load metadata.

        This method intentionally does not calculate template scores or choose
        final top recommendations. It returns a broad valid candidate set for
        the ranking stage to evaluate later.
        """

        target = course_load_target or CourseLoadTarget.mvp_default_policy()
        fixed = list(fixed_major_courses)
        required_candidates = self._dedupe_by_course_identity(
            required_general_candidates
        )
        required_groups = self._group_required_candidates(required_candidates)
        elective_candidates = self._dedupe_by_course_identity(
            elective_general_candidates
        )
        limit = self.max_candidates if max_candidates is None else max_candidates
        if limit <= 0:
            raise ValueError("max_candidates must be positive")

        diagnostics: list[GenerationDiagnostic] = []
        stats: Counter[str] = Counter()
        started_at = perf_counter()

        fixed_result = self.validator.validate(
            fixed,
            max_credit=max_credit,
            max_credit_inclusive=max_credit_inclusive,
        )
        if not fixed_result.valid:
            return TimetableGenerationResult(
                diagnostics=[
                    GenerationDiagnostic(
                        reason_code="FIXED_MAJOR_INTEGRITY_ERROR",
                        reason="확정 전공 과목끼리 충돌하거나 유효하지 않습니다.",
                        count=len(fixed_result.issues),
                    )
                ]
            )

        fixed_credits = self.validator.calculate_total_credit(fixed)
        if (
            target.target_total_credits is not None
            and fixed_credits > target.target_total_credits
        ):
            return TimetableGenerationResult(
                diagnostics=[
                    GenerationDiagnostic(
                        reason_code="MAJOR_CREDITS_EXCEED_TARGET",
                        reason=(
                            f"확정 전공 학점 {fixed_credits:g}이 목표 총학점 "
                            f"{target.target_total_credits:g}을 초과합니다."
                        ),
                        count=1,
                    )
                ]
            )
        credit_ceiling = self._credit_ceiling(target, max_credit)

        if not required_candidates:
            diagnostics.append(GenerationDiagnostic(
                reason_code="NO_REQUIRED_GENERAL_CANDIDATE",
                reason="사용 가능한 교양필수 후보가 없습니다.",
                count=0,
            ))
        if target.additional_elective_count and not elective_candidates:
            diagnostics.append(GenerationDiagnostic(
                reason_code="INSUFFICIENT_ELECTIVE_CANDIDATES",
                reason="요청한 교양선택 개수를 채울 후보가 없습니다.",
                count=0,
            ))

        hard_filter = TimetableRanker()
        required_sizes = range(len(required_groups), -1, -1)
        candidates: list[TimetableGenerationCandidate] = []
        seen_timetables: set[tuple[tuple[str, str], ...]] = set()
        truncated = False

        for required_count in required_sizes:
            for required_group_candidates in self._required_group_combinations(
                required_groups,
                required_count,
                base_credits=fixed_credits,
                credit_ceiling=credit_ceiling,
            ):
                selected_required = list(required_group_candidates)
                if self._has_duplicate_logical_course(fixed + selected_required):
                    stats["DUPLICATE_LOGICAL_COURSE"] += 1
                    continue
                required_credit = self.validator.calculate_total_credit(
                    selected_required
                )
                if self._exceeds_target(fixed_credits + required_credit, target):
                    stats["CREDIT_ABOVE_TARGET"] += 1
                    continue
                validation = self.validator.validate(
                    selected_required,
                    fixed_courses=fixed,
                    max_credit=credit_ceiling,
                    max_credit_inclusive=max_credit_inclusive,
                )
                if not validation.valid:
                    self._count_validation_issues(stats, validation)
                    continue

                elective_sizes = self._elective_sizes(
                    target,
                    elective_candidates,
                    base_credits=fixed_credits + required_credit,
                    min_credit=min_credit,
                    min_credit_inclusive=min_credit_inclusive,
                    max_credit=credit_ceiling,
                    max_credit_inclusive=max_credit_inclusive,
                )
                for elective_count in elective_sizes:
                    for elective_group in combinations(elective_candidates, elective_count):
                        selected = [*selected_required, *elective_group]
                        all_courses = [*fixed, *selected]
                        stats["COMBINATIONS_EVALUATED"] += 1

                        if self._has_duplicate_logical_course(all_courses):
                            stats["DUPLICATE_LOGICAL_COURSE"] += 1
                            continue
                        if self._exceeds_target(
                            self.validator.calculate_total_credit(all_courses),
                            target,
                        ):
                            stats["CREDIT_ABOVE_TARGET"] += 1
                            continue

                        validation = self.validator.validate(
                            selected,
                            fixed_courses=fixed,
                            min_credit=min_credit,
                            min_credit_inclusive=min_credit_inclusive,
                            max_credit=credit_ceiling,
                            max_credit_inclusive=max_credit_inclusive,
                        )
                        if not validation.valid:
                            self._count_validation_issues(stats, validation)
                            continue

                        timetable = Timetable(courses=all_courses)
                        if hard_conditions is not None and not hard_filter.apply_hard_filters(
                            [timetable],
                            preferences=hard_conditions,
                        ):
                            stats["HARD_CONDITION_FAILED"] += 1
                            continue

                        key = tuple(
                            sorted(
                                (course.course_id, course.division)
                                for course in all_courses
                            )
                        )
                        if key in seen_timetables:
                            stats["DUPLICATE_TIMETABLE"] += 1
                            continue
                        seen_timetables.add(key)

                        candidates.append(TimetableGenerationCandidate(
                            timetable=timetable,
                            load_satisfaction=self._load_satisfaction(
                                timetable.courses,
                                target=target,
                            ),
                        ))
                        if len(candidates) >= limit:
                            truncated = True
                            break
                    if truncated:
                        break
                if truncated:
                    break
            if truncated:
                break

        candidates.sort(
            key=lambda item: self._objective_key(item.load_satisfaction),
            reverse=True,
        )
        elapsed_ms = int((perf_counter() - started_at) * 1000)
        diagnostics.extend(self._build_diagnostics(
            stats,
            candidates,
            target,
            elapsed_ms=elapsed_ms,
        ))
        if truncated:
            diagnostics.append(GenerationDiagnostic(
                reason_code="GENERATION_TRUNCATED",
                reason="후보 생성 개수 제한에 도달해 탐색을 중단했습니다.",
                count=limit,
            ))

        return TimetableGenerationResult(
            candidates=candidates,
            diagnostics=diagnostics,
            truncated=truncated,
        )

    @staticmethod
    def _dedupe_by_course_identity(courses: Iterable[Course]) -> list[Course]:
        deduped: list[Course] = []
        seen: set[tuple[str, str]] = set()
        for course in courses:
            key = (course.course_id, course.division)
            if key in seen:
                continue
            deduped.append(course)
            seen.add(key)
        return deduped

    @staticmethod
    def _dedupe_by_course_id(courses: Iterable[Course]) -> list[Course]:
        """Backward-compatible alias; division is part of candidate identity."""

        return TimetableGenerator._dedupe_by_course_identity(courses)

    @classmethod
    def _group_required_candidates(cls, courses: Iterable[Course]) -> list[list[Course]]:
        groups_by_key: dict[str, list[Course]] = {}
        for course in courses:
            groups_by_key.setdefault(cls._logical_course_key(course), []).append(course)
        return list(groups_by_key.values())

    @staticmethod
    def _required_group_combinations(
        groups: list[list[Course]],
        count: int,
        *,
        base_credits: float,
        credit_ceiling: float | None,
    ) -> Iterable[tuple[Course, ...]]:
        if count == 0:
            yield ()
            return
        for selected_groups in combinations(groups, count):
            if credit_ceiling is not None:
                minimum_group_credits = sum(
                    min(course.credit for course in group)
                    for group in selected_groups
                )
                if base_credits + minimum_group_credits > credit_ceiling:
                    continue
            yield from product(*selected_groups)

    @staticmethod
    def _elective_sizes(
        target: CourseLoadTarget,
        elective_candidates: list[Course],
        *,
        base_credits: float = 0,
        min_credit: float | None = None,
        min_credit_inclusive: bool = True,
        max_credit: float | None = None,
        max_credit_inclusive: bool = True,
    ) -> range:
        if not elective_candidates:
            return range(0, -1, -1)

        credits = [course.credit for course in elective_candidates]
        requested_count = target.additional_elective_count or 0
        max_count = requested_count

        minimum_credit = min(credits)
        if min_credit is not None and base_credits < min_credit:
            credit_gap = min_credit - base_credits
            count_for_boundary = ceil(credit_gap / minimum_credit)
            if (
                not min_credit_inclusive
                and abs(base_credits + count_for_boundary * minimum_credit - min_credit) < 1e-9
            ):
                count_for_boundary += 1
            max_count = max(max_count, count_for_boundary)
        elif target.target_total_credits is not None:
            remaining = max(target.target_total_credits - base_credits, 0)
            max_count = max(max_count, floor(remaining / minimum_credit))

        if max_credit is not None:
            remaining = max(max_credit - base_credits, 0)
            ceiling_count = floor(remaining / minimum_credit)
            if (
                not max_credit_inclusive
                and abs(base_credits + ceiling_count * minimum_credit - max_credit) < 1e-9
            ):
                ceiling_count -= 1
            max_count = min(max_count, max(0, ceiling_count))

        max_count = min(max_count, len(elective_candidates))
        return range(max_count, -1, -1)

    @staticmethod
    def _credit_ceiling(
        target: CourseLoadTarget,
        max_credit: float | None,
    ) -> float | None:
        limits = [
            value
            for value in (target.target_total_credits, max_credit)
            if value is not None
        ]
        return min(limits) if limits else None

    @staticmethod
    def _exceeds_target(total_credits: float, target: CourseLoadTarget) -> bool:
        return (
            target.target_total_credits is not None
            and total_credits > target.target_total_credits
        )

    @staticmethod
    def _logical_course_key(course: Course) -> str:
        return " ".join(course.course_name.casefold().split())

    @classmethod
    def _has_duplicate_logical_course(cls, courses: Iterable[Course]) -> bool:
        keys = [cls._logical_course_key(course) for course in courses]
        return len(keys) != len(set(keys))

    @staticmethod
    def _count_validation_issues(
        stats: Counter[str],
        validation: object,
    ) -> None:
        for issue in validation.issues:
            stats[issue.code] += 1

    @staticmethod
    def _load_satisfaction(
        courses: Iterable[Course],
        *,
        target: CourseLoadTarget,
    ) -> CourseLoadSatisfaction:
        values = list(courses)
        final_total = sum(course.credit for course in values)
        required = [
            course for course in values
            if course.category == Category.GENERAL_REQUIRED
        ]
        elective = [
            course for course in values
            if course.category == Category.GENERAL_ELECTIVE
        ]
        credit_gap = (
            None
            if target.target_total_credits is None
            else target.target_total_credits - final_total
        )
        elective_gap = (
            None
            if target.additional_elective_count is None
            else target.additional_elective_count - len(elective)
        )
        if elective_gap is not None:
            elective_gap = max(elective_gap, 0)
        return CourseLoadSatisfaction(
            final_total_credits=final_total,
            target_total_credits=target.target_total_credits,
            required_general_count=len(required),
            required_general_credits=sum(course.credit for course in required),
            elective_count=len(elective),
            requested_elective_count=target.additional_elective_count,
            credit_gap=credit_gap,
            elective_count_gap=elective_gap,
            within_credit_limit=(
                None
                if target.target_total_credits is None
                else final_total <= target.target_total_credits
            ),
            elective_count_met=(
                None
                if target.additional_elective_count is None
                else len(elective) == target.additional_elective_count
            ),
        )

    @staticmethod
    def _objective_key(load: CourseLoadSatisfaction) -> tuple[float, float, float, float]:
        elective_gap = 0 if load.elective_count_gap is None else abs(load.elective_count_gap)
        credit_gap = 0 if load.credit_gap is None else abs(load.credit_gap)
        return (
            load.required_general_count,
            load.required_general_credits,
            -elective_gap,
            -credit_gap,
        )

    @staticmethod
    def _build_diagnostics(
        stats: Counter[str],
        candidates: list[TimetableGenerationCandidate],
        target: CourseLoadTarget,
        *,
        elapsed_ms: int,
    ) -> list[GenerationDiagnostic]:
        diagnostics: list[GenerationDiagnostic] = [
            GenerationDiagnostic(
                reason_code="COMBINATIONS_EVALUATED",
                reason="탐색한 교양 조합 수입니다.",
                count=stats["COMBINATIONS_EVALUATED"],
            ),
            GenerationDiagnostic(
                reason_code="VALID_CANDIDATES",
                reason="생성된 유효 시간표 후보 수입니다.",
                count=len(candidates),
            ),
            GenerationDiagnostic(
                reason_code="GENERATION_ELAPSED_MS",
                reason="시간표 후보 생성에 걸린 시간(ms)입니다.",
                count=elapsed_ms,
            ),
        ]
        code_map = {
            "TIME_CONFLICT": (
                "ALL_CANDIDATES_TIME_CONFLICT",
                "시간 충돌로 제외된 조합이 있습니다.",
            ),
            "TRAVEL_NOT_POSSIBLE": (
                "ALL_CANDIDATES_MOVEMENT_INVALID",
                "연강 이동 규칙으로 제외된 조합이 있습니다.",
            ),
            "HARD_CONDITION_FAILED": (
                "ALL_CANDIDATES_HARD_CONDITION_FAILED",
                "하드 조건 위반으로 제외된 조합이 있습니다.",
            ),
            "CREDIT_ABOVE_TARGET": (
                "CREDIT_TARGET_PRUNED",
                "목표 총학점 상한을 초과해 제외된 조합이 있습니다.",
            ),
            "DUPLICATE_LOGICAL_COURSE": (
                "DUPLICATE_LOGICAL_COURSE",
                "같은 과목의 여러 분반이 동시에 선택되어 제외된 조합이 있습니다.",
            ),
        }
        for source_code, (reason_code, reason) in code_map.items():
            if stats[source_code]:
                diagnostics.append(GenerationDiagnostic(
                    reason_code=reason_code,
                    reason=reason,
                    count=stats[source_code],
                ))

        if not candidates and stats["COMBINATIONS_EVALUATED"]:
            diagnostics.append(GenerationDiagnostic(
                reason_code="NO_VALID_TIMETABLE",
                reason="조건을 만족하는 유효한 시간표 후보가 없습니다.",
                count=0,
            ))

        if target.additional_elective_count is not None and candidates:
            best_elective = max(
                candidate.load_satisfaction.elective_count
                for candidate in candidates
            )
            if best_elective < target.additional_elective_count:
                diagnostics.append(GenerationDiagnostic(
                    reason_code="ELECTIVE_TARGET_NOT_MET",
                    reason="요청한 교양선택 개수를 모두 채우지 못했습니다.",
                    count=target.additional_elective_count - best_elective,
                ))

        if target.target_total_credits is not None and candidates:
            best_credit = max(
                candidate.load_satisfaction.final_total_credits
                for candidate in candidates
            )
            if best_credit < target.target_total_credits:
                diagnostics.append(GenerationDiagnostic(
                    reason_code="CREDIT_TARGET_NOT_REACHED",
                    reason="목표 총학점을 초과하지 않는 범위에서 가장 가까운 후보를 유지했습니다.",
                    count=int(target.target_total_credits - best_credit),
                ))

        return diagnostics


def generate_timetables(
    *,
    fixed_courses: Iterable[Course],
    general_required_candidates: Iterable[Course] = (),
    general_elective_candidates: Iterable[Course] = (),
    required_general_count: int = 0,
    elective_general_count: int = 0,
    campus_rule_engine: CampusRuleEngine | None = None,
    max_candidates: int = 200,
    min_credit: float | None = None,
    max_credit: float | None = None,
) -> list[TimetableCandidate]:
    """Functional convenience API for recommendation route handlers."""

    return TimetableGenerator(
        campus_rule_engine=campus_rule_engine,
        max_candidates=max_candidates,
        min_credit=min_credit,
        max_credit=max_credit,
    ).generate(
        fixed_courses=fixed_courses,
        general_required_candidates=general_required_candidates,
        general_elective_candidates=general_elective_candidates,
        required_general_count=required_general_count,
        elective_general_count=elective_general_count,
        min_credit=min_credit,
        max_credit=max_credit,
    )
