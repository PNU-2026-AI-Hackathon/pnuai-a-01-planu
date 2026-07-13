"""Score and rank valid timetable candidates."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable

from ..models.course import ClassTime, Course, Day, time_to_minutes
from ..models.preference import PreferenceRules
from ..models.timetable import Timetable, TimetableCandidate


class TimetableRanker:
    """Turn valid candidates into the top recommendations returned by the API."""

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

        scored = [self._score_candidate(candidate, rules) for candidate in candidates]
        scored.sort(
            key=lambda item: (
                -item.score,
                item.total_credit or 0,
                self._first_start_minutes(item),
                self._course_id_key(item),
            )
        )

        ranked: list[Timetable] = []
        for index, candidate in enumerate(scored[:limit], start=1):
            ranked.append(
                candidate.model_copy(
                    update={
                        "rank": index,
                        "score": round(candidate.score, 2),
                    }
                )
            )
        return ranked

    def _score_candidate(
        self, candidate: TimetableCandidate, preferences: PreferenceRules
    ) -> Timetable:
        score = 70.0
        reasons = ["전공 수업과 시간 충돌이 없습니다.", "연강 이동 위험이 없습니다."]
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
                score += 8 * len(satisfied)
                reasons.append(
                    f"{self._day_labels(satisfied)} 공강 조건을 만족합니다."
                )
            if missing:
                score -= 5 * len(missing)
                warnings.append(
                    f"{self._day_labels(missing)} 공강 선호는 만족하지 못했습니다."
                )

        if preferences.avoid_morning_classes:
            morning_count = self._morning_class_count(candidate.courses, preferences)
            if morning_count == 0:
                score += 8
                reasons.append("오전 수업 회피 조건을 만족합니다.")
            else:
                score -= 4 * morning_count
                warnings.append(f"오전 수업이 {morning_count}개 포함되어 있습니다.")

        consecutive_count = self._consecutive_class_count(candidate.courses)
        if preferences.minimize_consecutive_classes:
            if consecutive_count == 0:
                score += 5
                reasons.append("연강이 적은 시간표입니다.")
            else:
                score -= 3 * consecutive_count
                warnings.append(f"연강 구간이 {consecutive_count}개 있습니다.")

        if preferences.max_consecutive_classes is not None:
            longest = self._longest_consecutive_chain(candidate.courses)
            if longest <= preferences.max_consecutive_classes:
                score += 4
                reasons.append("최대 연강 개수 조건을 만족합니다.")
            else:
                score -= 8 * (longest - preferences.max_consecutive_classes)
                warnings.append(
                    f"최대 {longest}개 연강 구간이 포함되어 있습니다."
                )

        score += self._compactness_bonus(candidate.courses)
        score = max(0.0, min(100.0, score))
        return candidate.model_copy(
            update={
                "score": score,
                "reasons": self._unique(reasons),
                "warnings": self._unique(warnings),
            }
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

    @staticmethod
    def _morning_class_count(
        courses: Iterable[Course], preferences: PreferenceRules
    ) -> int:
        threshold = time_to_minutes(preferences.morning_end_time)
        return sum(
            1
            for course in courses
            for meeting in course.class_times
            if meeting.start_minutes < threshold
        )

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

    def _compactness_bonus(self, courses: Iterable[Course]) -> float:
        """Small deterministic bonus for schedules with less idle time."""

        idle_minutes = 0
        for meetings in self._meetings_by_day(courses).values():
            for previous, following in zip(meetings, meetings[1:]):
                idle_minutes += max(0, following.start_minutes - previous.end_minutes)
        if idle_minutes <= 60:
            return 4
        if idle_minutes <= 180:
            return 2
        return 0

    @staticmethod
    def _first_start_minutes(candidate: Timetable) -> int:
        starts = [time_to_minutes(item.start) for item in candidate.schedule_items]
        return min(starts) if starts else 24 * 60

    @staticmethod
    def _course_id_key(candidate: Timetable) -> tuple[str, ...]:
        return tuple(course.course_id for course in candidate.courses)

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
