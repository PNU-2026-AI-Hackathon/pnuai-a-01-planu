"""Filter hard user rules, score valid candidates, and rank them."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Callable

from ..models.course import Category, ClassTime, Course, Day, time_to_minutes
from ..models.preference import ExcludedTimeRange, PreferenceRules, PreferenceTemplate
from ..models.timetable import (
    RankingResult,
    RankingTemplate,
    ScoreComponent,
    Timetable,
    TimetableCandidate,
)
from .ranking_template_service import (
    LEGACY_TEMPLATE_WEIGHT_PROFILES,
    RankingTemplateService,
    RankingWeights,
    normalize_ranking_template,
    weights_for_template as ranking_template_weights_for_template,
)
from .course_name_matcher import course_name_matches


TEMPLATE_WEIGHT_PROFILES: dict[PreferenceTemplate, RankingWeights] = (
    LEGACY_TEMPLATE_WEIGHT_PROFILES
)

MovementChecker = Callable[[Course, ClassTime, Course, ClassTime], bool]


@dataclass(frozen=True)
class RankingContext:
    template: RankingTemplate
    weights: RankingWeights
    explicit_template: bool


@dataclass(frozen=True)
class ConsecutiveClassSummary:
    total_count: int
    movable_count: int
    difficult_count: int


def weights_for_template(
    template: RankingTemplate | PreferenceTemplate | str | None,
) -> RankingWeights:
    if template is None:
        return RankingWeights()
    if isinstance(template, PreferenceTemplate):
        return TEMPLATE_WEIGHT_PROFILES[template]
    return ranking_template_weights_for_template(template)


def build_ranking_weights(preferences: PreferenceRules | None = None) -> RankingWeights:
    """Create weights from the selected single template, or defaults if absent."""

    rules = preferences or PreferenceRules()
    return weights_for_template(rules.selected_template)


class TimetableRanker:
    """Apply hard filters, then sort by soft-condition score components."""

    def __init__(
        self,
        *,
        top_n: int = 3,
        weights: RankingWeights | None = None,
        template_service: RankingTemplateService | None = None,
        movement_checker: MovementChecker | None = None,
    ) -> None:
        if top_n <= 0:
            raise ValueError("top_n must be positive")
        self.top_n = top_n
        self._explicit_weights = weights
        self.template_service = template_service or RankingTemplateService()
        self.movement_checker = movement_checker

    def rank(
        self,
        candidates: Iterable[TimetableCandidate],
        *,
        preferences: PreferenceRules | None = None,
        template: RankingTemplate | PreferenceTemplate | str | None = None,
        top_n: int | None = None,
    ) -> list[RankingResult]:
        rules = preferences or PreferenceRules()
        limit = self.top_n if top_n is None else top_n
        if limit <= 0:
            raise ValueError("top_n must be positive")

        context = self.build_context(template, rules)
        deduped = self.dedupe_candidates(candidates)
        hard_filtered = self.apply_hard_filters(deduped, preferences=rules)
        return self.rank_filtered_candidates(
            hard_filtered,
            preferences=rules,
            context=context,
            top_n=limit,
        )

    def rank_filtered_candidates(
        self,
        candidates: Iterable[TimetableCandidate],
        *,
        preferences: PreferenceRules | None = None,
        context: RankingContext,
        top_n: int,
    ) -> list[RankingResult]:
        if top_n <= 0:
            raise ValueError("top_n must be positive")

        rules = preferences or PreferenceRules()
        scored = [
            self._score_candidate(candidate, rules, context)
            for candidate in candidates
        ]
        scored.sort(
            key=lambda item: (
                -item.load_satisfaction.required_group_sort_count,
                item.load_satisfaction.elective_count_sort_gap,
                item.load_satisfaction.credit_sort_gap,
                -item.raw_score,
                self._idle_minutes(item.timetable.courses),
                len(self._meetings_by_day(item.timetable.courses)),
                self._morning_class_count(item.timetable.courses),
                self._course_id_key(item.timetable),
            )
        )

        return [
            result.model_copy(
                update={"timetable": result.timetable.model_copy(update={"rank": index})}
            )
            for index, result in enumerate(scored[:top_n], start=1)
        ]

    def build_context(
        self,
        template: RankingTemplate | PreferenceTemplate | str | None,
        preferences: PreferenceRules,
    ) -> RankingContext:
        selected_template = template if template is not None else preferences.selected_template
        ranking_template = normalize_ranking_template(selected_template)
        weights = self._explicit_weights or self.template_service.get_weights(
            selected_template
        )
        return RankingContext(
            template=ranking_template,
            weights=weights,
            explicit_template=template is not None,
        )

    def _build_context(
        self,
        template: RankingTemplate | PreferenceTemplate | str | None,
        preferences: PreferenceRules,
    ) -> RankingContext:
        return self.build_context(template, preferences)

    def apply_hard_filters(
        self,
        candidates: Iterable[TimetableCandidate],
        *,
        preferences: PreferenceRules | None = None,
    ) -> list[TimetableCandidate]:
        rules = preferences or PreferenceRules()
        return [
            candidate
            for candidate in candidates
            if not self._violates_hard_conditions(candidate, rules)
        ]

    def _violates_hard_conditions(
        self, candidate: TimetableCandidate, preferences: PreferenceRules
    ) -> bool:
        meetings = [
            (meeting, course)
            for course in candidate.courses
            for meeting in course.class_times
        ]

        if preferences.excluded_days and any(
            meeting.day in preferences.excluded_days for meeting, _ in meetings
        ):
            return True

        occupied_days = {meeting.day for meeting, _ in meetings}
        if any(day in occupied_days for day in preferences.required_free_days):
            return True

        if preferences.earliest_start_time is not None:
            earliest = time_to_minutes(preferences.earliest_start_time)
            if any(meeting.start_minutes < earliest for meeting, _ in meetings):
                return True

        if preferences.latest_end_time is not None:
            latest = time_to_minutes(preferences.latest_end_time)
            if any(meeting.end_minutes > latest for meeting, _ in meetings):
                return True

        if preferences.excluded_time_ranges and any(
            self._overlaps_excluded_range(meeting, excluded)
            for meeting, _ in meetings
            for excluded in preferences.excluded_time_ranges
        ):
            return True

        course_names = [course.course_name for _, course in meetings]
        if preferences.required_course_names and not all(
            self._has_matching_course(name, course_names)
            for name in preferences.required_course_names
        ):
            return True
        if preferences.excluded_course_names and any(
            self._has_matching_course(name, course_names)
            for name in preferences.excluded_course_names
        ):
            return True

        excluded_professors = {
            professor.casefold() for professor in preferences.excluded_professors
        }
        if excluded_professors and any(
            course.professor.casefold() in excluded_professors
            for _, course in meetings
        ):
            return True

        if preferences.max_consecutive_classes is not None:
            longest = self._longest_consecutive_chain(candidate.courses)
            if longest > preferences.max_consecutive_classes:
                return True

        return False

    def _score_candidate(
        self,
        candidate: TimetableCandidate,
        preferences: PreferenceRules,
        context: RankingContext,
    ) -> RankingResult:
        components = [self._valid_candidate_component(context)]
        reasons = [components[0].reason]
        warnings = list(candidate.warnings)

        components.extend(
            self._preferred_free_day_components(candidate, preferences, context)
        )
        component = self._preferred_first_class_component(
            candidate,
            preferences,
            context,
        )
        if component is not None:
            components.append(component)
        components.extend(
            self._preferred_free_time_range_components(candidate, preferences, context)
        )
        components.extend(self._preferred_course_components(candidate, preferences, context))
        components.extend(self._avoided_course_components(candidate, preferences, context))
        components.extend(
            self._preferred_elective_area_components(candidate, preferences, context)
        )

        if context.explicit_template or preferences.minimize_attendance_days:
            components.append(self._attendance_days_component(candidate, context))
        if context.explicit_template or preferences.minimize_consecutive_classes:
            components.append(self._consecutive_classes_component(candidate, context))

        if context.explicit_template or preferences.compact_schedule:
            components.append(self._compact_schedule_component(candidate, context))
        if context.explicit_template:
            components.append(self._daily_first_start_component(candidate, context))

        for component in components[1:]:
            if component.value > 0:
                reasons.append(component.reason)
            elif component.value < 0:
                warnings.append(component.reason)

        data = candidate.model_dump()
        data.update({
            "score_details": components,
            "reasons": self._unique(reasons),
            "warnings": self._unique(warnings),
        })
        return RankingResult(
            score_components=components,
            timetable=Timetable.model_validate(data),
            load_satisfaction=candidate.load_satisfaction,
            template=context.template,
        )

    def _valid_candidate_component(self, context: RankingContext) -> ScoreComponent:
        return ScoreComponent(
            key="valid_candidate",
            label="유효한 시간표 후보",
            value=context.weights.valid_candidate,
            reason="하드 조건을 모두 통과한 유효한 시간표 후보입니다.",
        )

    def _preferred_free_day_components(
        self,
        candidate: TimetableCandidate,
        preferences: PreferenceRules,
        context: RankingContext,
    ) -> list[ScoreComponent]:
        if not preferences.preferred_free_days:
            return []

        free_days = self._free_days(candidate.courses)
        satisfied = [day for day in preferences.preferred_free_days if day in free_days]
        missing = [day for day in preferences.preferred_free_days if day not in free_days]
        components: list[ScoreComponent] = []
        if satisfied:
            day_labels = self._day_labels(satisfied)
            components.append(ScoreComponent(
                key="preferred_free_day",
                label=f"{day_labels} 공강 선호 만족",
                value=context.weights.preferred_free_day * len(satisfied),
                reason=f"{day_labels} 공강 선호를 만족합니다.",
            ))
        if missing:
            day_labels = self._day_labels(missing)
            components.append(ScoreComponent(
                key="preferred_free_day_missing",
                label=f"{day_labels} 공강 선호 미충족",
                value=context.weights.preferred_free_day_missing * len(missing),
                reason=f"{day_labels} 공강 선호는 만족하지 못했습니다.",
            ))
        return components

    def _preferred_first_class_component(
        self,
        candidate: TimetableCandidate,
        preferences: PreferenceRules,
        context: RankingContext,
    ) -> ScoreComponent | None:
        if preferences.preferred_first_class_time is None:
            return None

        first_start = self._first_meeting_start_minutes(candidate.courses)
        preferred = time_to_minutes(preferences.preferred_first_class_time)
        value = self._preferred_first_class_value(first_start, preferred, context)
        if first_start >= preferred:
            reason = f"첫 수업이 {preferences.preferred_first_class_time} 이후에 시작합니다."
        else:
            reason = (
                f"첫 수업이 선호 시간({preferences.preferred_first_class_time})보다 "
                "일찍 시작합니다."
            )
        return ScoreComponent(
            key="preferred_first_class_time",
            label=(
                f"첫 수업 시작 {self._minutes_to_clock(first_start)} "
                f"(선호 {preferences.preferred_first_class_time} 이후)"
            ),
            value=value,
            reason=reason,
        )

    def _preferred_free_time_range_components(
        self,
        candidate: TimetableCandidate,
        preferences: PreferenceRules,
        context: RankingContext,
    ) -> list[ScoreComponent]:
        if not preferences.preferred_free_time_ranges:
            return []

        satisfied = [
            time_range
            for time_range in preferences.preferred_free_time_ranges
            if not self._candidate_overlaps_time_range(candidate, time_range)
        ]
        missing_count = len(preferences.preferred_free_time_ranges) - len(satisfied)
        total = len(preferences.preferred_free_time_ranges)
        components: list[ScoreComponent] = []
        if satisfied:
            components.append(ScoreComponent(
                key="preferred_free_time_range",
                label=f"선호 공강 시간 {len(satisfied)}/{total}개 만족",
                value=context.weights.preferred_free_time_range * len(satisfied),
                reason=f"선호 공강 시간 {len(satisfied)}개를 만족합니다.",
            ))
        if missing_count:
            components.append(ScoreComponent(
                key="preferred_free_time_range_missing",
                label=f"선호 공강 시간 {missing_count}/{total}개 미충족",
                value=context.weights.preferred_free_time_range_missing * missing_count,
                reason=f"선호 공강 시간 {missing_count}개는 만족하지 못했습니다.",
            ))
        return components

    def _preferred_course_components(
        self,
        candidate: TimetableCandidate,
        preferences: PreferenceRules,
        context: RankingContext,
    ) -> list[ScoreComponent]:
        if not preferences.preferred_course_names:
            return []

        course_names = [course.course_name for course in candidate.courses]
        preferred_courses = [
            name
            for name in preferences.preferred_course_names
            if self._has_matching_course(name, course_names)
        ]
        missing_courses = [
            name
            for name in preferences.preferred_course_names
            if not self._has_matching_course(name, course_names)
        ]
        components: list[ScoreComponent] = []
        if preferred_courses:
            components.append(ScoreComponent(
                key="preferred_course",
                label=f"선호 과목 {len(preferred_courses)}개 포함",
                value=context.weights.preferred_course * len(preferred_courses),
                reason=f"선호 과목이 포함되었습니다: {', '.join(preferred_courses)}.",
            ))
        if missing_courses:
            components.append(ScoreComponent(
                key="preferred_course_missing",
                label=f"선호 과목 {len(missing_courses)}개 미포함",
                value=context.weights.preferred_course_missing * len(missing_courses),
                reason=(
                    "선호 과목이 포함되지 않아 감점되었습니다: "
                    f"{', '.join(missing_courses)}."
                ),
            ))
        return components

    def _avoided_course_components(
        self,
        candidate: TimetableCandidate,
        preferences: PreferenceRules,
        context: RankingContext,
    ) -> list[ScoreComponent]:
        if not preferences.avoided_course_names:
            return []

        course_names = [course.course_name for course in candidate.courses]
        avoided_courses = [
            name
            for name in preferences.avoided_course_names
            if self._has_matching_course(name, course_names)
        ]
        absent_courses = [
            name
            for name in preferences.avoided_course_names
            if not self._has_matching_course(name, course_names)
        ]
        components: list[ScoreComponent] = []
        if avoided_courses:
            components.append(ScoreComponent(
                key="avoided_course",
                label=f"회피 선호 과목 {len(avoided_courses)}개 포함",
                value=context.weights.avoided_course * len(avoided_courses),
                reason=(
                    "가능하면 피하고 싶은 과목이 포함되었습니다: "
                    f"{', '.join(avoided_courses)}."
                ),
            ))
        if absent_courses:
            components.append(ScoreComponent(
                key="avoided_course_absent",
                label=f"회피 선호 과목 {len(absent_courses)}개 미포함",
                value=context.weights.avoided_course_absent * len(absent_courses),
                reason=f"회피 선호 과목이 포함되지 않았습니다: {', '.join(absent_courses)}.",
            ))
        return components

    @staticmethod
    def _has_matching_course(name: str, course_names: Iterable[str]) -> bool:
        return any(course_name_matches(name, course_name) for course_name in course_names)

    def _preferred_elective_area_components(
        self,
        candidate: TimetableCandidate,
        preferences: PreferenceRules,
        context: RankingContext,
    ) -> list[ScoreComponent]:
        if not preferences.preferred_elective_areas:
            return []

        candidate_areas = {
            course.area
            for course in candidate.courses
            if course.category == Category.GENERAL_ELECTIVE and course.area is not None
        }
        preferred_areas = set(preferences.preferred_elective_areas)
        satisfied = sorted(candidate_areas & preferred_areas)
        missing = [
            area for area in preferences.preferred_elective_areas if area not in candidate_areas
        ]

        components: list[ScoreComponent] = []
        if satisfied:
            labels = ", ".join(f"{area}영역" for area in satisfied)
            components.append(ScoreComponent(
                key="preferred_elective_area",
                label=f"선호 교양 영역 {len(satisfied)}/{len(preferences.preferred_elective_areas)}개 포함",
                value=context.weights.preferred_elective_area * len(satisfied),
                reason=f"선호 교양 영역이 포함되었습니다: {labels}.",
            ))
        if missing:
            labels = ", ".join(f"{area}영역" for area in missing)
            components.append(ScoreComponent(
                key="preferred_elective_area_missing",
                label=f"선호 교양 영역 {len(missing)}개 미포함",
                value=context.weights.preferred_elective_area_missing * len(missing),
                reason=f"선호 교양 영역은 포함되지 않았습니다: {labels}.",
            ))
        return components

    def _attendance_days_component(
        self,
        candidate: TimetableCandidate,
        context: RankingContext,
    ) -> ScoreComponent:
        attendance_days = len(self._meetings_by_day(candidate.courses))
        value = self._attendance_days_value(attendance_days, context)
        if value > 0:
            reason = f"등교일이 {attendance_days}일로 적습니다."
        elif value < 0:
            reason = f"등교일이 {attendance_days}일로 많습니다."
        else:
            reason = f"등교일이 {attendance_days}일입니다."
        return ScoreComponent(
            key="attendance_days",
            label=f"등교일 {attendance_days}일",
            value=value,
            reason=reason,
        )

    def _consecutive_classes_component(
        self,
        candidate: TimetableCandidate,
        context: RankingContext,
    ) -> ScoreComponent:
        summary = self._consecutive_class_summary(candidate.courses)
        if summary.total_count == 0:
            return ScoreComponent(
                key="consecutive_classes",
                label="연강 없음",
                value=context.weights.no_consecutive_classes,
                reason="연강이 없습니다.",
            )
        if summary.difficult_count == 0:
            return ScoreComponent(
                key="consecutive_classes",
                label=f"이동 어려운 연강 0개 / 전체 {summary.total_count}개",
                value=0,
                reason=(
                    f"연강 {summary.total_count}개가 있으며 모두 이동 가능한 구간입니다."
                ),
            )
        return ScoreComponent(
            key="consecutive_classes",
            label=(
                f"이동 어려운 연강 {summary.difficult_count}개 / "
                f"전체 {summary.total_count}개"
            ),
            value=context.weights.consecutive_class * summary.difficult_count,
            reason=(
                f"연강 {summary.total_count}개 중 {summary.difficult_count}개는 "
                "이동이 어려운 구간입니다."
            ),
        )

    def _compact_schedule_component(
        self,
        candidate: TimetableCandidate,
        context: RankingContext,
    ) -> ScoreComponent:
        idle_minutes = self._idle_minutes(candidate.courses)
        multi_class_day_count = self._multi_class_day_count(candidate.courses)
        attendance_days = len(self._meetings_by_day(candidate.courses))
        value = self._compact_schedule_value(
            idle_minutes,
            multi_class_day_count=multi_class_day_count,
            context=context,
        )
        if value > 0:
            reason = (
                f"수업이 2개 이상 있는 {multi_class_day_count}일의 "
                f"수업 사이 총 빈 시간이 {idle_minutes}분으로 짧습니다."
            )
        elif value < 0:
            reason = (
                f"수업이 2개 이상 있는 {multi_class_day_count}일의 "
                f"수업 사이 총 빈 시간이 {idle_minutes}분으로 깁니다."
            )
        else:
            reason = (
                f"{attendance_days}개 등교일 중 수업이 2개 이상인 날은 "
                f"{multi_class_day_count}일이며, 수업 사이 총 빈 시간은 "
                f"{idle_minutes}분입니다."
            )
        return ScoreComponent(
            key="compact_schedule",
            label=f"수업 사이 총 빈 시간 {idle_minutes}분",
            value=value,
            reason=reason,
        )

    def _daily_first_start_component(
        self,
        candidate: TimetableCandidate,
        context: RankingContext,
    ) -> ScoreComponent:
        first_starts = self._daily_first_start_minutes(candidate.courses)
        daily_values = [
            self._late_start_value(start, context)
            for start in first_starts
        ]
        if not daily_values:
            value = 0
        elif context.template is RankingTemplate.NO_MORNING_PRIORITY:
            value = sum(daily_values)
        else:
            value = sum(daily_values) / len(daily_values)
        late_days = sum(1 for start in first_starts if start >= time_to_minutes("10:00"))
        very_late_days = sum(1 for start in first_starts if start >= time_to_minutes("11:00"))
        early_days = sum(1 for start in first_starts if start < time_to_minutes("09:00"))
        attendance_days = len(first_starts)
        return ScoreComponent(
            key="daily_first_start",
            label=f"요일별 첫 수업 시작 평가 {attendance_days}일",
            value=value,
            reason=(
                f"{attendance_days}개 등교일의 요일별 첫 수업을 평가했습니다. "
                f"{late_days}일은 첫 수업이 10시 이후이며, "
                f"그중 {very_late_days}일은 11시 이후입니다. "
                f"{early_days}일은 9시 이전에 시작합니다."
            ),
        )

    @staticmethod
    def _overlaps_excluded_range(
        meeting: ClassTime, excluded: ExcludedTimeRange
    ) -> bool:
        return (
            meeting.day == excluded.day
            and meeting.start_minutes < excluded.end_minutes
            and excluded.start_minutes < meeting.end_minutes
        )

    @staticmethod
    def _meetings_by_day(courses: Iterable[Course]) -> dict[Day, list[ClassTime]]:
        by_day: dict[Day, list[ClassTime]] = defaultdict(list)
        for course in courses:
            for meeting in course.class_times:
                by_day[meeting.day].append(meeting)
        for meetings in by_day.values():
            meetings.sort(key=lambda item: item.start_minutes)
        return dict(by_day)

    def _free_days(self, courses: Iterable[Course]) -> set[Day]:
        occupied = set(self._meetings_by_day(courses))
        return set(Day) - occupied

    def _consecutive_class_count(self, courses: Iterable[Course]) -> int:
        return self._consecutive_class_summary(courses).difficult_count

    def _consecutive_class_summary(
        self,
        courses: Iterable[Course],
    ) -> ConsecutiveClassSummary:
        total_count = 0
        movable_count = 0
        difficult_count = 0
        for meetings in self._course_meetings_by_day(courses).values():
            for (previous, previous_course), (following, following_course) in zip(
                meetings,
                meetings[1:],
            ):
                if following.start_minutes != previous.end_minutes:
                    continue
                total_count += 1
                if self.movement_checker is not None:
                    if self.movement_checker(
                        previous_course,
                        previous,
                        following_course,
                        following,
                    ):
                        movable_count += 1
                    else:
                        difficult_count += 1
                    continue
                difficult_count += 1
        return ConsecutiveClassSummary(
            total_count=total_count,
            movable_count=movable_count,
            difficult_count=difficult_count,
        )

    def _longest_consecutive_chain(self, courses: Iterable[Course]) -> int:
        longest = 1
        for meetings in self._meetings_by_day(courses).values():
            current = 1
            for previous, following in zip(meetings, meetings[1:]):
                if following.start_minutes == previous.end_minutes:
                    current += 1
                    longest = max(longest, current)
                else:
                    current = 1
        return longest

    def _idle_minutes(self, courses: Iterable[Course]) -> int:
        idle_minutes = 0
        for meetings in self._meetings_by_day(courses).values():
            for previous, following in zip(meetings, meetings[1:]):
                idle_minutes += max(0, following.start_minutes - previous.end_minutes)
        return idle_minutes

    def _multi_class_day_count(self, courses: Iterable[Course]) -> int:
        return sum(
            1
            for meetings in self._meetings_by_day(courses).values()
            if len(meetings) >= 2
        )

    def _morning_class_count(self, courses: Iterable[Course]) -> int:
        morning_end = time_to_minutes("12:00")
        return sum(
            1
            for course in courses
            for meeting in course.class_times
            if meeting.start_minutes < morning_end
        )

    def _compact_schedule_value(
        self,
        idle_minutes: int,
        *,
        multi_class_day_count: int,
        context: RankingContext,
    ) -> float:
        if multi_class_day_count == 0:
            return 0
        if idle_minutes <= 60:
            return context.weights.compact_idle_short
        if idle_minutes <= 180:
            return context.weights.compact_idle_medium
        return context.weights.compact_idle_long

    def _attendance_days_value(
        self,
        attendance_days: int,
        context: RankingContext,
    ) -> float:
        if attendance_days <= 3:
            return context.weights.attendance_days_low
        if attendance_days == 4:
            return context.weights.attendance_days_medium
        return context.weights.attendance_days_high

    def _late_start_value(self, first_start: int, context: RankingContext) -> float:
        if first_start >= time_to_minutes("11:00"):
            return context.weights.late_start_11_or_later
        if first_start >= time_to_minutes("10:00"):
            return context.weights.late_start_10_or_later
        if first_start < time_to_minutes("09:00"):
            return context.weights.early_start_before_9
        return 0

    def _preferred_first_class_value(
        self,
        first_start: int,
        preferred: int,
        context: RankingContext,
    ) -> float:
        if first_start >= preferred:
            return self._late_start_value(first_start, context)
        return self._late_start_value(first_start, context) - self._late_start_value(
            preferred,
            context,
        )

    @staticmethod
    def _candidate_overlaps_time_range(
        candidate: TimetableCandidate, time_range: ExcludedTimeRange
    ) -> bool:
        return any(
            TimetableRanker._overlaps_excluded_range(meeting, time_range)
            for course in candidate.courses
            for meeting in course.class_times
        )

    @staticmethod
    def _first_start_minutes(candidate: Timetable) -> int:
        starts = [time_to_minutes(item.start) for item in candidate.schedule_items]
        return min(starts) if starts else 24 * 60

    @staticmethod
    def _first_meeting_start_minutes(courses: Iterable[Course]) -> int:
        starts = [
            meeting.start_minutes
            for course in courses
            for meeting in course.class_times
        ]
        return min(starts) if starts else 24 * 60

    def _daily_first_start_minutes(self, courses: Iterable[Course]) -> list[int]:
        return [
            meetings[0].start_minutes
            for _, meetings in sorted(
                self._meetings_by_day(courses).items(),
                key=lambda item: list(Day).index(item[0]),
            )
        ]

    @staticmethod
    def _course_meetings_by_day(
        courses: Iterable[Course],
    ) -> dict[Day, list[tuple[ClassTime, Course]]]:
        by_day: dict[Day, list[tuple[ClassTime, Course]]] = defaultdict(list)
        for course in courses:
            for meeting in course.class_times:
                by_day[meeting.day].append((meeting, course))
        for meetings in by_day.values():
            meetings.sort(key=lambda item: item[0].start_minutes)
        return dict(by_day)

    @staticmethod
    def _course_id_key(candidate: Timetable) -> tuple[tuple[str, str], ...]:
        return tuple(sorted((course.course_id, course.division) for course in candidate.courses))

    @classmethod
    def dedupe_candidates(
        cls,
        candidates: Iterable[TimetableCandidate],
    ) -> list[TimetableCandidate]:
        deduped: list[TimetableCandidate] = []
        seen: set[tuple[tuple[str, str], ...]] = set()
        for candidate in candidates:
            key = cls._course_id_key(candidate)
            if key in seen:
                continue
            deduped.append(candidate)
            seen.add(key)
        return deduped

    @classmethod
    def _dedupe_candidates(
        cls,
        candidates: Iterable[TimetableCandidate],
    ) -> list[TimetableCandidate]:
        return cls.dedupe_candidates(candidates)

    @staticmethod
    def _minutes_to_clock(value: int) -> str:
        if value >= 24 * 60:
            return "미정"
        return f"{value // 60:02d}:{value % 60:02d}"

    @staticmethod
    def _day_labels(days: Iterable[Day]) -> str:
        labels = {
            Day.MON: "월요일",
            Day.TUE: "화요일",
            Day.WED: "수요일",
            Day.THU: "목요일",
            Day.FRI: "금요일",
        }
        return ", ".join(labels[day] for day in sorted(days, key=lambda day: list(Day).index(day)))

    @staticmethod
    def _unique(values: Iterable[str]) -> list[str]:
        return list(dict.fromkeys(value for value in values if value))


def rank_timetables(
    candidates: Iterable[TimetableCandidate],
    *,
    preferences: PreferenceRules | None = None,
    template: RankingTemplate | PreferenceTemplate | str | None = None,
    top_n: int = 3,
    weights: RankingWeights | None = None,
) -> list[RankingResult]:
    """Functional convenience API for recommendation route handlers."""

    return TimetableRanker(top_n=top_n, weights=weights).rank(
        candidates,
        preferences=preferences,
        template=template,
        top_n=top_n,
    )
