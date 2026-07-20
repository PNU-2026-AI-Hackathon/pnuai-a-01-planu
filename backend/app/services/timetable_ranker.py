"""Filter hard user rules, score valid candidates, and rank them."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

from ..models.course import Category, ClassTime, Course, Day, time_to_minutes
from ..models.preference import ExcludedTimeRange, PreferenceRules, PreferenceTemplate
from ..models.timetable import RankingResult, ScoreComponent, Timetable, TimetableCandidate


@dataclass(frozen=True)
class RankingWeights:
    """A complete evaluation profile for one timetable direction.

    ``PreferenceRules`` stores concrete user preferences. ``PreferenceTemplate``
    selects one timetable direction. ``RankingWeights`` defines the full set of
    relative scoring priorities for that direction.
    """

    valid_candidate: float = 70
    preferred_free_day: float = 8
    preferred_free_day_missing: float = -5
    preferred_free_time_range: float = 3
    preferred_free_time_range_missing: float = -2
    preferred_course: float = 4
    preferred_course_missing: float = -1
    avoided_course: float = -4
    avoided_course_absent: float = 1
    preferred_elective_area: float = 3
    preferred_elective_area_missing: float = -1
    no_consecutive_classes: float = 5
    consecutive_class: float = -3
    compact_idle_short: float = 4
    compact_idle_medium: float = 2
    compact_idle_long: float = -2
    attendance_days_low: float = 6
    attendance_days_medium: float = 2
    attendance_days_high: float = -4
    late_start_11_or_later: float = 6
    late_start_10_or_later: float = 3
    early_start_before_9: float = -4


TEMPLATE_WEIGHT_PROFILES: dict[PreferenceTemplate, RankingWeights] = {
    PreferenceTemplate.PREFER_FREE_DAY: RankingWeights(
        valid_candidate=70,
        preferred_free_day=14,
        preferred_free_day_missing=-11,
        preferred_free_time_range=8,
        preferred_free_time_range_missing=-7,
        preferred_course=2,
        preferred_course_missing=-0.5,
        avoided_course=-2,
        avoided_course_absent=0.5,
        preferred_elective_area=2,
        preferred_elective_area_missing=-0.5,
        no_consecutive_classes=3,
        consecutive_class=-2,
        compact_idle_short=5,
        compact_idle_medium=3,
        compact_idle_long=-3,
        attendance_days_low=6,
        attendance_days_medium=3,
        attendance_days_high=-4,
        late_start_11_or_later=2,
        late_start_10_or_later=1,
        early_start_before_9=-1,
    ),
    PreferenceTemplate.MINIMIZE_ATTENDANCE_DAYS: RankingWeights(
        valid_candidate=70,
        preferred_free_day=6,
        preferred_free_day_missing=-4,
        preferred_free_time_range=3,
        preferred_free_time_range_missing=-2,
        preferred_course=2,
        preferred_course_missing=-0.5,
        avoided_course=-2,
        avoided_course_absent=0.5,
        preferred_elective_area=2,
        preferred_elective_area_missing=-0.5,
        no_consecutive_classes=3,
        consecutive_class=-2,
        compact_idle_short=5,
        compact_idle_medium=3,
        compact_idle_long=-3,
        attendance_days_low=14,
        attendance_days_medium=7,
        attendance_days_high=-11,
        late_start_11_or_later=2,
        late_start_10_or_later=1,
        early_start_before_9=-1,
    ),
    PreferenceTemplate.MINIMIZE_CONSECUTIVE_CLASSES: RankingWeights(
        valid_candidate=70,
        preferred_free_day=5,
        preferred_free_day_missing=-3,
        preferred_free_time_range=3,
        preferred_free_time_range_missing=-2,
        preferred_course=2,
        preferred_course_missing=-0.5,
        avoided_course=-2,
        avoided_course_absent=0.5,
        preferred_elective_area=2,
        preferred_elective_area_missing=-0.5,
        no_consecutive_classes=14,
        consecutive_class=-10,
        compact_idle_short=4,
        compact_idle_medium=2,
        compact_idle_long=-3,
        attendance_days_low=5,
        attendance_days_medium=3,
        attendance_days_high=-4,
        late_start_11_or_later=2,
        late_start_10_or_later=1,
        early_start_before_9=-1,
    ),
    PreferenceTemplate.COMPACT_SCHEDULE: RankingWeights(
        valid_candidate=70,
        preferred_free_day=5,
        preferred_free_day_missing=-3,
        preferred_free_time_range=3,
        preferred_free_time_range_missing=-2,
        preferred_course=2,
        preferred_course_missing=-0.5,
        avoided_course=-2,
        avoided_course_absent=0.5,
        preferred_elective_area=2,
        preferred_elective_area_missing=-0.5,
        no_consecutive_classes=5,
        consecutive_class=-4,
        compact_idle_short=14,
        compact_idle_medium=8,
        compact_idle_long=-11,
        attendance_days_low=6,
        attendance_days_medium=4,
        attendance_days_high=-5,
        late_start_11_or_later=2,
        late_start_10_or_later=1,
        early_start_before_9=-1,
    ),
    PreferenceTemplate.REQUIRED_FREE_DAY: RankingWeights(
        valid_candidate=70,
        preferred_free_day=12,
        preferred_free_day_missing=-9,
        preferred_free_time_range=7,
        preferred_free_time_range_missing=-6,
        preferred_course=2,
        preferred_course_missing=-0.5,
        avoided_course=-2,
        avoided_course_absent=0.5,
        preferred_elective_area=2,
        preferred_elective_area_missing=-0.5,
        no_consecutive_classes=4,
        consecutive_class=-3,
        compact_idle_short=5,
        compact_idle_medium=3,
        compact_idle_long=-3,
        attendance_days_low=7,
        attendance_days_medium=4,
        attendance_days_high=-5,
        late_start_11_or_later=2,
        late_start_10_or_later=1,
        early_start_before_9=-1,
    ),
}


def weights_for_template(template: PreferenceTemplate | None) -> RankingWeights:
    """Return the complete profile for one template, or defaults when absent."""

    if template is None:
        return RankingWeights()
    return TEMPLATE_WEIGHT_PROFILES[template]


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
    ) -> None:
        if top_n <= 0:
            raise ValueError("top_n must be positive")
        self.top_n = top_n
        self._explicit_weights = weights
        self.weights = weights or RankingWeights()

    def rank(
        self,
        candidates: Iterable[TimetableCandidate],
        *,
        preferences: PreferenceRules | None = None,
        top_n: int | None = None,
    ) -> list[RankingResult]:
        rules = preferences or PreferenceRules()
        limit = self.top_n if top_n is None else top_n
        if limit <= 0:
            raise ValueError("top_n must be positive")

        self.weights = self._explicit_weights or build_ranking_weights(rules)
        hard_filtered = self.apply_hard_filters(candidates, preferences=rules)
        scored = [self._score_candidate(candidate, rules) for candidate in hard_filtered]
        scored.sort(
            key=lambda item: (
                -item.raw_score,
                item.timetable.total_credit or 0,
                self._first_start_minutes(item.timetable),
                self._course_id_key(item.timetable),
            )
        )

        return [
            result.model_copy(
                update={"timetable": result.timetable.model_copy(update={"rank": index})}
            )
            for index, result in enumerate(scored[:limit], start=1)
        ]

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

        course_names = {course.course_name for _, course in meetings}
        if preferences.required_course_names and not set(
            preferences.required_course_names
        ).issubset(course_names):
            return True
        if preferences.excluded_course_names and any(
            name in course_names for name in preferences.excluded_course_names
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
        self, candidate: TimetableCandidate, preferences: PreferenceRules
    ) -> RankingResult:
        components = [self._valid_candidate_component()]
        reasons = [components[0].reason]
        warnings = list(candidate.warnings)

        components.extend(self._preferred_free_day_components(candidate, preferences))
        component = self._preferred_first_class_component(candidate, preferences)
        if component is not None:
            components.append(component)
        components.extend(self._preferred_free_time_range_components(candidate, preferences))
        components.extend(self._preferred_course_components(candidate, preferences))
        components.extend(self._avoided_course_components(candidate, preferences))
        components.extend(self._preferred_elective_area_components(candidate, preferences))

        if preferences.minimize_attendance_days:
            components.append(self._attendance_days_component(candidate))
        if preferences.minimize_consecutive_classes:
            components.append(self._consecutive_classes_component(candidate))

        if preferences.compact_schedule:
            components.append(self._compact_schedule_component(candidate))

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
        )

    def _valid_candidate_component(self) -> ScoreComponent:
        return ScoreComponent(
            key="valid_candidate",
            label="유효한 시간표 후보",
            value=self.weights.valid_candidate,
            reason="하드 조건을 모두 통과한 유효한 시간표 후보입니다.",
        )

    def _preferred_free_day_components(
        self, candidate: TimetableCandidate, preferences: PreferenceRules
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
                value=self.weights.preferred_free_day * len(satisfied),
                reason=f"{day_labels} 공강 선호를 만족합니다.",
            ))
        if missing:
            day_labels = self._day_labels(missing)
            components.append(ScoreComponent(
                key="preferred_free_day_missing",
                label=f"{day_labels} 공강 선호 미충족",
                value=self.weights.preferred_free_day_missing * len(missing),
                reason=f"{day_labels} 공강 선호는 만족하지 못했습니다.",
            ))
        return components

    def _preferred_first_class_component(
        self, candidate: TimetableCandidate, preferences: PreferenceRules
    ) -> ScoreComponent | None:
        if preferences.preferred_first_class_time is None:
            return None

        first_start = self._first_meeting_start_minutes(candidate.courses)
        preferred = time_to_minutes(preferences.preferred_first_class_time)
        value = self._preferred_first_class_value(first_start, preferred)
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
        self, candidate: TimetableCandidate, preferences: PreferenceRules
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
                value=self.weights.preferred_free_time_range * len(satisfied),
                reason=f"선호 공강 시간 {len(satisfied)}개를 만족합니다.",
            ))
        if missing_count:
            components.append(ScoreComponent(
                key="preferred_free_time_range_missing",
                label=f"선호 공강 시간 {missing_count}/{total}개 미충족",
                value=self.weights.preferred_free_time_range_missing * missing_count,
                reason=f"선호 공강 시간 {missing_count}개는 만족하지 못했습니다.",
            ))
        return components

    def _preferred_course_components(
        self, candidate: TimetableCandidate, preferences: PreferenceRules
    ) -> list[ScoreComponent]:
        if not preferences.preferred_course_names:
            return []

        course_names = {course.course_name for course in candidate.courses}
        preferred_courses = [
            name for name in preferences.preferred_course_names if name in course_names
        ]
        missing_courses = [
            name for name in preferences.preferred_course_names if name not in course_names
        ]
        components: list[ScoreComponent] = []
        if preferred_courses:
            components.append(ScoreComponent(
                key="preferred_course",
                label=f"선호 과목 {len(preferred_courses)}개 포함",
                value=self.weights.preferred_course * len(preferred_courses),
                reason=f"선호 과목이 포함되었습니다: {', '.join(preferred_courses)}.",
            ))
        if missing_courses:
            components.append(ScoreComponent(
                key="preferred_course_missing",
                label=f"선호 과목 {len(missing_courses)}개 미포함",
                value=self.weights.preferred_course_missing * len(missing_courses),
                reason=(
                    "선호 과목이 포함되지 않아 감점되었습니다: "
                    f"{', '.join(missing_courses)}."
                ),
            ))
        return components

    def _avoided_course_components(
        self, candidate: TimetableCandidate, preferences: PreferenceRules
    ) -> list[ScoreComponent]:
        if not preferences.avoided_course_names:
            return []

        course_names = {course.course_name for course in candidate.courses}
        avoided_courses = [
            name for name in preferences.avoided_course_names if name in course_names
        ]
        absent_courses = [
            name for name in preferences.avoided_course_names if name not in course_names
        ]
        components: list[ScoreComponent] = []
        if avoided_courses:
            components.append(ScoreComponent(
                key="avoided_course",
                label=f"회피 선호 과목 {len(avoided_courses)}개 포함",
                value=self.weights.avoided_course * len(avoided_courses),
                reason=(
                    "가능하면 피하고 싶은 과목이 포함되었습니다: "
                    f"{', '.join(avoided_courses)}."
                ),
            ))
        if absent_courses:
            components.append(ScoreComponent(
                key="avoided_course_absent",
                label=f"회피 선호 과목 {len(absent_courses)}개 미포함",
                value=self.weights.avoided_course_absent * len(absent_courses),
                reason=f"회피 선호 과목이 포함되지 않았습니다: {', '.join(absent_courses)}.",
            ))
        return components

    def _preferred_elective_area_components(
        self, candidate: TimetableCandidate, preferences: PreferenceRules
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
                value=self.weights.preferred_elective_area * len(satisfied),
                reason=f"선호 교양 영역이 포함되었습니다: {labels}.",
            ))
        if missing:
            labels = ", ".join(f"{area}영역" for area in missing)
            components.append(ScoreComponent(
                key="preferred_elective_area_missing",
                label=f"선호 교양 영역 {len(missing)}개 미포함",
                value=self.weights.preferred_elective_area_missing * len(missing),
                reason=f"선호 교양 영역은 포함되지 않았습니다: {labels}.",
            ))
        return components

    def _attendance_days_component(
        self, candidate: TimetableCandidate
    ) -> ScoreComponent:
        attendance_days = len(self._meetings_by_day(candidate.courses))
        value = self._attendance_days_value(attendance_days)
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
        self, candidate: TimetableCandidate
    ) -> ScoreComponent:
        consecutive_count = self._consecutive_class_count(candidate.courses)
        if consecutive_count == 0:
            return ScoreComponent(
                key="consecutive_classes",
                label="연강 없음",
                value=self.weights.no_consecutive_classes,
                reason="연강이 없습니다.",
            )
        return ScoreComponent(
            key="consecutive_classes",
            label=f"연강 구간 {consecutive_count}개",
            value=self.weights.consecutive_class * consecutive_count,
            reason=f"연강 구간이 {consecutive_count}개 있습니다.",
        )

    def _compact_schedule_component(
        self, candidate: TimetableCandidate
    ) -> ScoreComponent:
        idle_minutes = self._idle_minutes(candidate.courses)
        value = self._compact_schedule_value(idle_minutes)
        if value > 0:
            reason = f"수업 사이 총 빈 시간이 {idle_minutes}분으로 짧습니다."
        elif value < 0:
            reason = f"수업 사이 총 빈 시간이 {idle_minutes}분으로 깁니다."
        else:
            reason = f"수업 사이 총 빈 시간이 {idle_minutes}분입니다."
        return ScoreComponent(
            key="compact_schedule",
            label=f"수업 사이 총 빈 시간 {idle_minutes}분",
            value=value,
            reason=reason,
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
        count = 0
        for meetings in self._meetings_by_day(courses).values():
            for previous, following in zip(meetings, meetings[1:]):
                if following.start_minutes == previous.end_minutes:
                    count += 1
        return count

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

    def _compact_schedule_value(self, idle_minutes: int) -> float:
        if idle_minutes <= 60:
            return self.weights.compact_idle_short
        if idle_minutes <= 180:
            return self.weights.compact_idle_medium
        return self.weights.compact_idle_long

    def _attendance_days_value(self, attendance_days: int) -> float:
        if attendance_days <= 3:
            return self.weights.attendance_days_low
        if attendance_days == 4:
            return self.weights.attendance_days_medium
        return self.weights.attendance_days_high

    def _late_start_value(self, first_start: int) -> float:
        if first_start >= time_to_minutes("11:00"):
            return self.weights.late_start_11_or_later
        if first_start >= time_to_minutes("10:00"):
            return self.weights.late_start_10_or_later
        if first_start < time_to_minutes("09:00"):
            return self.weights.early_start_before_9
        return 0

    def _preferred_first_class_value(self, first_start: int, preferred: int) -> float:
        if first_start >= preferred:
            return self._late_start_value(first_start)
        return self._late_start_value(first_start) - self._late_start_value(preferred)

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

    @staticmethod
    def _course_id_key(candidate: Timetable) -> tuple[tuple[str, str], ...]:
        return tuple((course.course_id, course.division) for course in candidate.courses)

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
    top_n: int = 3,
    weights: RankingWeights | None = None,
) -> list[RankingResult]:
    """Functional convenience API for recommendation route handlers."""

    return TimetableRanker(top_n=top_n, weights=weights).rank(
        candidates,
        preferences=preferences,
        top_n=top_n,
    )
