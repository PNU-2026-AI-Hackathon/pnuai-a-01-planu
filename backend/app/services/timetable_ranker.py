"""Filter hard user rules, score valid candidates, and rank them."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable

from ..models.course import ClassTime, Course, Day, time_to_minutes
from ..models.preference import ExcludedTimeRange, PreferenceRules
from ..models.timetable import ScoreDetail, Timetable, TimetableCandidate


class TimetableRanker:
    """Turn generated candidates into deterministic recommendations."""

    def __init__(self, *, top_n: int = 3) -> None:
        if top_n <= 0:
            raise ValueError("top_n must be positive")
        self.top_n = top_n

    def rank(
        self,
        candidates: Iterable[TimetableCandidate],
        *,
        preferences: PreferenceRules | None = None,
        top_n: int | None = None,
    ) -> list[Timetable]:
        rules = preferences or PreferenceRules()
        limit = self.top_n if top_n is None else top_n
        if limit <= 0:
            raise ValueError("top_n must be positive")

        hard_filtered = self.apply_hard_filters(candidates, preferences=rules)
        scored = [self._score_candidate(candidate, rules) for candidate in hard_filtered]
        scored.sort(
            key=lambda item: (
                -item.score,
                item.total_credit or 0,
                self._first_start_minutes(item),
                self._course_id_key(item),
            )
        )

        return [
            candidate.model_copy(update={"rank": index})
            for index, candidate in enumerate(scored[:limit], start=1)
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
    ) -> Timetable:
        details = [
            ScoreDetail(
                key="valid_candidate",
                label="유효한 시간표 후보",
                value=70,
            )
        ]
        reasons: list[str] = []
        warnings = list(candidate.warnings)

        free_days = self._free_days(candidate.courses)
        if preferences.preferred_free_days:
            satisfied = [
                day for day in preferences.preferred_free_days if day in free_days
            ]
            missing = [
                day for day in preferences.preferred_free_days if day not in free_days
            ]
            if satisfied:
                value = 8 * len(satisfied)
                details.append(ScoreDetail(
                    key="preferred_free_day",
                    label=f"{self._day_labels(satisfied)} 공강 선호 만족",
                    value=value,
                ))
                reasons.append(f"{self._day_labels(satisfied)} 공강 선호를 만족합니다.")
            if missing:
                value = -5 * len(missing)
                details.append(ScoreDetail(
                    key="preferred_free_day_missing",
                    label=f"{self._day_labels(missing)} 공강 선호 미충족",
                    value=value,
                ))
                warnings.append(
                    f"{self._day_labels(missing)} 공강 선호는 만족하지 못했습니다."
                )

        if preferences.preferred_first_class_time is not None:
            first_start = self._first_meeting_start_minutes(candidate.courses)
            preferred = time_to_minutes(preferences.preferred_first_class_time)
            value = self._preferred_first_class_value(first_start, preferred)
            details.append(ScoreDetail(
                key="preferred_first_class_time",
                label=(
                    f"첫 수업 시작 {self._minutes_to_clock(first_start)} "
                    f"(선호 {preferences.preferred_first_class_time} 이후)"
                ),
                value=value,
            ))
            if first_start >= preferred:
                reasons.append(
                    f"첫 수업이 {preferences.preferred_first_class_time} 이후에 시작합니다."
                )
            else:
                warnings.append(
                    f"첫 수업이 선호 시간({preferences.preferred_first_class_time})보다 일찍 시작합니다."
                )

        if preferences.preferred_free_time_ranges:
            satisfied = [
                time_range
                for time_range in preferences.preferred_free_time_ranges
                if not self._candidate_overlaps_time_range(candidate, time_range)
            ]
            missing = [
                time_range
                for time_range in preferences.preferred_free_time_ranges
                if time_range not in satisfied
            ]
            details.append(ScoreDetail(
                key="preferred_free_time_ranges",
                label=(
                    f"선호 공강 시간 {len(satisfied)}/"
                    f"{len(preferences.preferred_free_time_ranges)}개 만족"
                ),
                value=0,
            ))
            if missing:
                warnings.append(
                    "선호 공강 시간 일부는 만족하지 못했습니다. TODO: 점수 가중치 조정 필요."
                )

        course_names = {course.course_name for course in candidate.courses}
        preferred_courses = [
            name for name in preferences.preferred_course_names if name in course_names
        ]
        avoided_courses = [
            name for name in preferences.avoided_course_names if name in course_names
        ]
        if preferences.preferred_course_names:
            details.append(ScoreDetail(
                key="preferred_course_names",
                label=f"선호 과목 {len(preferred_courses)}/{len(preferences.preferred_course_names)}개 포함",
                value=0,
            ))
            if preferred_courses:
                reasons.append(
                    f"선호 과목이 포함되었습니다: {', '.join(preferred_courses)}. TODO: 점수 가중치 조정 필요."
                )
        if preferences.avoided_course_names:
            details.append(ScoreDetail(
                key="avoided_course_names",
                label=f"회피 선호 과목 {len(avoided_courses)}개 포함",
                value=0,
            ))
            if avoided_courses:
                warnings.append(
                    f"가능하면 피하고 싶은 과목이 포함되었습니다: {', '.join(avoided_courses)}. TODO: 점수 가중치 조정 필요."
                )

        if preferences.minimize_attendance_days:
            attendance_days = len(self._meetings_by_day(candidate.courses))
            value = self._attendance_days_value(attendance_days)
            details.append(ScoreDetail(
                key="attendance_days",
                label=f"등교일 {attendance_days}일",
                value=value,
            ))

        consecutive_count = self._consecutive_class_count(candidate.courses)
        if preferences.minimize_consecutive_classes:
            if consecutive_count == 0:
                details.append(ScoreDetail(
                    key="consecutive_classes",
                    label="연강 없음",
                    value=5,
                ))
                reasons.append("연강이 없습니다.")
            else:
                details.append(ScoreDetail(
                    key="consecutive_classes",
                    label=f"연강 구간 {consecutive_count}개",
                    value=-3 * consecutive_count,
                ))
                warnings.append(f"연강 구간이 {consecutive_count}개 있습니다.")

        if preferences.compact_schedule:
            idle_minutes = self._idle_minutes(candidate.courses)
            value = self._compact_schedule_value(idle_minutes)
            details.append(ScoreDetail(
                key="compact_schedule",
                label=f"수업 사이 총 빈 시간 {idle_minutes}분",
                value=value,
            ))

        data = candidate.model_dump()
        data.update({
            "score_details": details,
            "reasons": self._unique(reasons),
            "warnings": self._unique(warnings),
        })
        return Timetable.model_validate(data)

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

    @staticmethod
    def _compact_schedule_value(idle_minutes: int) -> float:
        if idle_minutes <= 60:
            return 4
        if idle_minutes <= 180:
            return 2
        return -2

    @staticmethod
    def _attendance_days_value(attendance_days: int) -> float:
        if attendance_days <= 3:
            return 6
        if attendance_days == 4:
            return 2
        return -4

    @staticmethod
    def _late_start_value(first_start: int) -> float:
        if first_start >= time_to_minutes("11:00"):
            return 6
        if first_start >= time_to_minutes("10:00"):
            return 3
        if first_start < time_to_minutes("09:00"):
            return -4
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
        return ", ".join(labels[day] for day in sorted(days, key=lambda day: day.order))

    @staticmethod
    def _unique(values: Iterable[str]) -> list[str]:
        return list(dict.fromkeys(value for value in values if value))


def rank_timetables(
    candidates: Iterable[TimetableCandidate],
    *,
    preferences: PreferenceRules | None = None,
    top_n: int = 3,
) -> list[Timetable]:
    """Functional convenience API for recommendation route handlers."""

    return TimetableRanker(top_n=top_n).rank(
        candidates,
        preferences=preferences,
        top_n=top_n,
    )
