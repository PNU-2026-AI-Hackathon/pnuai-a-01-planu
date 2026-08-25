"""Deterministic scoring for generated timetable candidates.

The service evaluates only Soft preferences against a complete timetable
candidate, including both fixed and added sections. It does not read sessions,
does not scan catalogs, does not invoke LLMs, and does not normalize scores to
100. Hard invalid candidates are rejected before any score is assigned.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable

from ..models.course import ClassTime, Day, time_to_minutes
from ..models.course_discovery import CourseSection
from ..models.session_preferences import SoftPreferences
from ..models.timetable_generation import (
    GeneratedTimetableCandidate,
    ResolvedSection,
    SectionSource,
)
from .course_id_normalizer import logical_course_id, normalize_requested_course_ids
from ..models.timetable_scoring import (
    PreferenceEvidence,
    PreferenceEvidenceCode,
    ScoreComponent,
    ScoreComponentCode,
    ScoredTimetableCandidate,
    ScoringErrorCode,
    ScoringTradeOff,
    TimetableScoringError,
    TimetableScoringPolicy,
)


class TimetableScoringService:
    """Score one valid generated candidate from supplied section details."""

    def __init__(
        self,
        *,
        policy: TimetableScoringPolicy | None = None,
    ) -> None:
        self.policy = policy or TimetableScoringPolicy()

    def score_candidate(
        self,
        *,
        candidate: GeneratedTimetableCandidate,
        soft_preferences: SoftPreferences,
        sections: Iterable[ResolvedSection],
        policy: TimetableScoringPolicy | None = None,
    ) -> ScoredTimetableCandidate:
        active_policy = policy or self.policy
        if not candidate.validation.valid:
            raise ValueError("Hard invalid candidates cannot be scored")

        resolved_sections = list(sections)
        section_map = {resolved.source.key: resolved.section for resolved in resolved_sections}
        section_id_map = {
            resolved.section.section_id: resolved.section
            for resolved in resolved_sections
        }
        candidate_sections = self._sections_for_candidate(
            candidate,
            section_map,
            section_id_map,
        )
        components: list[ScoreComponent] = []
        satisfied: list[PreferenceEvidence] = []
        unsatisfied: list[PreferenceEvidence] = []
        trade_offs: list[ScoringTradeOff] = []

        self._score_free_days(
            candidate_sections,
            soft_preferences,
            active_policy,
            components,
            satisfied,
            unsatisfied,
        )
        self._score_start_time(
            candidate_sections,
            soft_preferences,
            active_policy,
            components,
            satisfied,
            unsatisfied,
        )
        self._score_end_time(
            candidate_sections,
            soft_preferences,
            active_policy,
            components,
            satisfied,
            unsatisfied,
        )
        self._score_courses(
            candidate_sections,
            soft_preferences,
            active_policy,
            components,
            satisfied,
            unsatisfied,
        )
        self._score_compact_schedule(
            candidate_sections,
            soft_preferences,
            active_policy,
            components,
            satisfied,
            unsatisfied,
            trade_offs,
        )

        if not components:
            trade_offs.append(
                ScoringTradeOff(
                    code=PreferenceEvidenceCode.NO_SOFT_PREFERENCES,
                    values={"message": "No Soft preferences were provided."},
                )
            )

        total_score = round(sum(component.score for component in components), 6)
        gap = self._gap_summary(candidate_sections)
        normalized_disliked_course_ids = normalize_requested_course_ids(
            soft_preferences.disliked_course_ids,
            candidate_sections,
        )
        included_disliked = sorted(
            {logical_course_id(section.course_id, section.division) for section in candidate_sections}
            & normalized_disliked_course_ids
        )
        latest_end = max(
            (meeting.end_minutes for section in candidate_sections for meeting in section.class_times),
            default=0,
        )

        return ScoredTimetableCandidate(
            candidate_id=candidate.candidate_id,
            candidate=candidate,
            total_score=total_score,
            score_components=components,
            satisfied_preferences=satisfied,
            unsatisfied_preferences=unsatisfied,
            trade_offs=trade_offs,
            tie_breaker={
                "satisfied_count": len(satisfied),
                "disliked_course_count": (
                    len(included_disliked)
                    if soft_preferences.disliked_course_ids
                    else 0
                ),
                "total_gap_minutes": (
                    gap["total_gap_minutes"]
                    if soft_preferences.compact_schedule is not None
                    else 0
                ),
                "latest_end_minutes": (
                    latest_end
                    if soft_preferences.preferred_latest_end_time is not None
                    else 0
                ),
            },
        )

    def _sections_for_candidate(
        self,
        candidate: GeneratedTimetableCandidate,
        section_map: dict[str, CourseSection],
        section_id_map: dict[str, CourseSection],
    ) -> list[CourseSection]:
        sections: list[CourseSection] = []
        missing: list[str] = []
        if candidate.section_sources:
            for source in candidate.section_sources:
                section = section_map.get(source.key)
                if section is None:
                    missing.append(source.section_id)
                else:
                    sections.append(section)
        else:
            for section_id in candidate.section_ids:
                section = section_id_map.get(section_id)
                if section is None:
                    missing.append(section_id)
                else:
                    sections.append(section)
        if missing:
            raise LookupError("missing section details: " + ", ".join(sorted(set(missing))))
        return sections

    def _score_free_days(
        self,
        sections: list[CourseSection],
        preferences: SoftPreferences,
        policy: TimetableScoringPolicy,
        components: list[ScoreComponent],
        satisfied: list[PreferenceEvidence],
        unsatisfied: list[PreferenceEvidence],
    ) -> None:
        if not preferences.preferred_free_days:
            return
        occupied = {meeting.day for section in sections for meeting in section.class_times}
        actual_free = [day for day in Day if day not in occupied]
        matched = [day for day in preferences.preferred_free_days if day in actual_free]
        missed = [day for day in preferences.preferred_free_days if day not in actual_free]
        for day in matched:
            satisfied.append(self._evidence(
                PreferenceEvidenceCode.FREE_DAY_PREFERENCE_SATISFIED,
                ScoreComponentCode.PREFERRED_FREE_DAYS,
                preferred_day=day.value,
            ))
        for day in missed:
            class_count = sum(
                1
                for section in sections
                for meeting in section.class_times
                if meeting.day == day
            )
            unsatisfied.append(self._evidence(
                PreferenceEvidenceCode.FREE_DAY_PREFERENCE_UNSATISFIED,
                ScoreComponentCode.PREFERRED_FREE_DAYS,
                preferred_day=day.value,
                class_count=class_count,
            ))
        components.append(ScoreComponent(
            code=ScoreComponentCode.PREFERRED_FREE_DAYS,
            label="Preferred free days",
            score=policy.preferred_free_day_weight * len(matched),
            weight=policy.preferred_free_day_weight,
            satisfied=not missed,
            details={
                "requested_days": [day.value for day in preferences.preferred_free_days],
                "actual_free_days": [day.value for day in actual_free],
                "satisfied_count": len(matched),
                "unsatisfied_count": len(missed),
            },
        ))

    def _score_start_time(
        self,
        sections: list[CourseSection],
        preferences: SoftPreferences,
        policy: TimetableScoringPolicy,
        components: list[ScoreComponent],
        satisfied: list[PreferenceEvidence],
        unsatisfied: list[PreferenceEvidence],
    ) -> None:
        if preferences.preferred_earliest_start_time is None:
            return
        preferred = time_to_minutes(preferences.preferred_earliest_start_time)
        first_by_day = self._first_start_by_day(sections)
        early_deltas = {
            day: max(0, preferred - start)
            for day, start in first_by_day.items()
        }
        violated_days = [
            day
            for day, delta in sorted(
                early_deltas.items(),
                key=lambda item: list(Day).index(item[0]),
            )
            if delta > 0
        ]
        max_delta = max(early_deltas.values(), default=0)
        score = policy.preferred_start_time_weight - (
            policy.early_start_penalty_per_minute * sum(early_deltas.values())
        )
        code = (
            PreferenceEvidenceCode.LATE_START_PREFERENCE_SATISFIED
            if max_delta == 0
            else PreferenceEvidenceCode.LATE_START_PREFERENCE_UNSATISFIED
        )
        evidence = self._evidence(
            code,
            ScoreComponentCode.PREFERRED_START_TIME,
            preferred_time=preferences.preferred_earliest_start_time,
            actual_earliest_time=self._minutes_to_clock(min(first_by_day.values(), default=24 * 60)),
            difference_minutes=max_delta,
        )
        (satisfied if max_delta == 0 else unsatisfied).append(evidence)
        components.append(ScoreComponent(
            code=ScoreComponentCode.PREFERRED_START_TIME,
            label="Preferred earliest start time",
            score=round(score, 6),
            weight=policy.preferred_start_time_weight,
            satisfied=max_delta == 0,
            details={
                "preferred_time": preferences.preferred_earliest_start_time,
                "daily_first_start_times": {
                    day.value: self._minutes_to_clock(value)
                    for day, value in sorted(first_by_day.items(), key=lambda item: list(Day).index(item[0]))
                },
                "total_early_minutes": sum(early_deltas.values()),
                "max_difference_minutes": max_delta,
                "violated_days": [day.value for day in violated_days],
            },
        ))

    def _score_end_time(
        self,
        sections: list[CourseSection],
        preferences: SoftPreferences,
        policy: TimetableScoringPolicy,
        components: list[ScoreComponent],
        satisfied: list[PreferenceEvidence],
        unsatisfied: list[PreferenceEvidence],
    ) -> None:
        if preferences.preferred_latest_end_time is None:
            return
        preferred = time_to_minutes(preferences.preferred_latest_end_time)
        last_by_day = self._last_end_by_day(sections)
        late_deltas = {
            day: max(0, end - preferred)
            for day, end in last_by_day.items()
        }
        violated_days = [
            day
            for day, delta in sorted(
                late_deltas.items(),
                key=lambda item: list(Day).index(item[0]),
            )
            if delta > 0
        ]
        max_delta = max(late_deltas.values(), default=0)
        score = policy.preferred_end_time_weight - (
            policy.late_end_penalty_per_minute * sum(late_deltas.values())
        )
        code = (
            PreferenceEvidenceCode.EARLY_END_PREFERENCE_SATISFIED
            if max_delta == 0
            else PreferenceEvidenceCode.EARLY_END_PREFERENCE_UNSATISFIED
        )
        evidence = self._evidence(
            code,
            ScoreComponentCode.PREFERRED_END_TIME,
            preferred_time=preferences.preferred_latest_end_time,
            actual_latest_time=self._minutes_to_clock(max(last_by_day.values(), default=0)),
            difference_minutes=max_delta,
        )
        (satisfied if max_delta == 0 else unsatisfied).append(evidence)
        components.append(ScoreComponent(
            code=ScoreComponentCode.PREFERRED_END_TIME,
            label="Preferred latest end time",
            score=round(score, 6),
            weight=policy.preferred_end_time_weight,
            satisfied=max_delta == 0,
            details={
                "preferred_time": preferences.preferred_latest_end_time,
                "daily_last_end_times": {
                    day.value: self._minutes_to_clock(value)
                    for day, value in sorted(last_by_day.items(), key=lambda item: list(Day).index(item[0]))
                },
                "total_late_minutes": sum(late_deltas.values()),
                "max_difference_minutes": max_delta,
                "violated_days": [day.value for day in violated_days],
            },
        ))

    def _score_courses(
        self,
        sections: list[CourseSection],
        preferences: SoftPreferences,
        policy: TimetableScoringPolicy,
        components: list[ScoreComponent],
        satisfied: list[PreferenceEvidence],
        unsatisfied: list[PreferenceEvidence],
    ) -> None:
        course_ids = {logical_course_id(section.course_id, section.division) for section in sections}
        if preferences.preferred_course_ids:
            preferred_course_ids = normalize_requested_course_ids(
                preferences.preferred_course_ids,
                sections,
            )
            included = sorted(course_ids & preferred_course_ids)
            missing = sorted(preferred_course_ids - course_ids)
            for course_id in included:
                satisfied.append(self._evidence(
                    PreferenceEvidenceCode.PREFERRED_COURSE_INCLUDED,
                    ScoreComponentCode.PREFERRED_COURSES,
                    course_id=course_id,
                ))
            for course_id in missing:
                unsatisfied.append(self._evidence(
                    PreferenceEvidenceCode.PREFERRED_COURSE_MISSING,
                    ScoreComponentCode.PREFERRED_COURSES,
                    course_id=course_id,
                ))
            components.append(ScoreComponent(
                code=ScoreComponentCode.PREFERRED_COURSES,
                label="Preferred courses",
                score=(
                    policy.preferred_course_weight * len(included)
                    - policy.missed_preferred_course_penalty * len(missing)
                ),
                weight=policy.preferred_course_weight,
                satisfied=not missing,
                details={
                    "requested_course_ids": preferences.preferred_course_ids,
                    "included_course_ids": included,
                    "missing_course_ids": missing,
                },
            ))
        if preferences.disliked_course_ids:
            disliked_course_ids = normalize_requested_course_ids(
                preferences.disliked_course_ids,
                sections,
            )
            disliked = sorted(course_ids & disliked_course_ids)
            for course_id in disliked:
                unsatisfied.append(self._evidence(
                    PreferenceEvidenceCode.DISLIKED_COURSE_INCLUDED,
                    ScoreComponentCode.DISLIKED_COURSES,
                    course_id=course_id,
                ))
            components.append(ScoreComponent(
                code=ScoreComponentCode.DISLIKED_COURSES,
                label="Disliked courses",
                score=-(policy.disliked_course_penalty * len(disliked)),
                weight=policy.disliked_course_penalty,
                satisfied=not disliked,
                details={
                    "requested_course_ids": preferences.disliked_course_ids,
                    "included_course_ids": disliked,
                },
            ))

    def _score_compact_schedule(
        self,
        sections: list[CourseSection],
        preferences: SoftPreferences,
        policy: TimetableScoringPolicy,
        components: list[ScoreComponent],
        satisfied: list[PreferenceEvidence],
        unsatisfied: list[PreferenceEvidence],
        trade_offs: list[ScoringTradeOff],
    ) -> None:
        summary = self._gap_summary(sections, policy)
        trade_code = self._compact_code(summary["total_gap_minutes"])
        trade_offs.append(ScoringTradeOff(code=trade_code, values=summary))
        if preferences.compact_schedule is None:
            return
        if preferences.compact_schedule is True:
            score = (
                policy.compact_schedule_weight
                - policy.gap_penalty_per_minute * summary["total_gap_minutes"]
                - policy.long_gap_penalty * summary["long_gap_count"]
            )
            is_satisfied = summary["total_gap_minutes"] <= policy.long_gap_threshold_minutes
        else:
            short_gap_count = int(summary["short_gap_count"])
            if short_gap_count == 0:
                score = policy.compact_schedule_weight
            else:
                score = -(policy.long_gap_penalty * short_gap_count)
            is_satisfied = short_gap_count == 0
        evidence = self._evidence(
            trade_code,
            ScoreComponentCode.COMPACT_SCHEDULE,
            total_gap_minutes=summary["total_gap_minutes"],
            long_gap_count=summary["long_gap_count"],
            short_gap_count=summary["short_gap_count"],
        )
        (satisfied if is_satisfied else unsatisfied).append(evidence)
        components.append(ScoreComponent(
            code=ScoreComponentCode.COMPACT_SCHEDULE,
            label="Compact schedule",
            score=round(score, 6),
            weight=policy.compact_schedule_weight,
            satisfied=is_satisfied,
            details=summary,
        ))

    @staticmethod
    def _meetings_by_day(sections: Iterable[CourseSection]) -> dict[Day, list[ClassTime]]:
        by_day: dict[Day, list[ClassTime]] = defaultdict(list)
        for section in sections:
            by_day.update()
            for meeting in section.class_times:
                by_day[meeting.day].append(meeting)
        for meetings in by_day.values():
            meetings.sort(key=lambda item: item.start_minutes)
        return dict(by_day)

    def _first_start_by_day(self, sections: Iterable[CourseSection]) -> dict[Day, int]:
        return {day: meetings[0].start_minutes for day, meetings in self._meetings_by_day(sections).items()}

    def _last_end_by_day(self, sections: Iterable[CourseSection]) -> dict[Day, int]:
        return {day: max(meeting.end_minutes for meeting in meetings) for day, meetings in self._meetings_by_day(sections).items()}

    def _gap_summary(
        self,
        sections: Iterable[CourseSection],
        policy: TimetableScoringPolicy | None = None,
    ) -> dict[str, object]:
        active_policy = policy or self.policy
        total = 0
        long_count = 0
        short_count = 0
        gaps_by_day: dict[str, list[int]] = {}
        for day, meetings in self._meetings_by_day(sections).items():
            gaps: list[int] = []
            for previous, following in zip(meetings, meetings[1:]):
                gap = max(0, following.start_minutes - previous.end_minutes)
                total += gap
                gaps.append(gap)
                if gap >= active_policy.long_gap_threshold_minutes and gap > 0:
                    long_count += 1
                if gap <= 30:
                    short_count += 1
            if gaps:
                gaps_by_day[day.value] = gaps
        return {
            "total_gap_minutes": total,
            "long_gap_count": long_count,
            "short_gap_count": short_count,
            "gaps_by_day": gaps_by_day,
        }

    @staticmethod
    def _compact_code(total_gap_minutes: int) -> PreferenceEvidenceCode:
        if total_gap_minutes <= 60:
            return PreferenceEvidenceCode.COMPACT_SCHEDULE_STRONG
        if total_gap_minutes <= 180:
            return PreferenceEvidenceCode.COMPACT_SCHEDULE_MODERATE
        return PreferenceEvidenceCode.COMPACT_SCHEDULE_WEAK

    @staticmethod
    def _evidence(
        code: PreferenceEvidenceCode,
        component_code: ScoreComponentCode,
        **values: object,
    ) -> PreferenceEvidence:
        return PreferenceEvidence(code=code, component_code=component_code, values=dict(values))

    @staticmethod
    def _minutes_to_clock(value: int) -> str:
        if value >= 24 * 60:
            return "NONE"
        return f"{value // 60:02d}:{value % 60:02d}"


def scoring_error_from_exception(
    exc: Exception,
    *,
    candidate_id: str | None = None,
) -> TimetableScoringError:
    if isinstance(exc, LookupError):
        code = ScoringErrorCode.SECTION_DETAILS_MISSING
    elif isinstance(exc, ValueError) and "Hard invalid" in str(exc):
        code = ScoringErrorCode.INVALID_CANDIDATE
    else:
        code = ScoringErrorCode.INVALID_SCORING_REQUEST
    return TimetableScoringError(code=code, message=str(exc), candidate_id=candidate_id)
