"""Adapters between durable session preferences and generation PreferenceRules."""

from __future__ import annotations

from ..models.preference import PreferenceRules
from ..models.session_preferences import HardConstraints, SoftPreferences


def hard_constraints_to_rules(hard: HardConstraints) -> PreferenceRules:
    """Convert durable HardConstraints into generator hard rules."""

    data: dict[str, object] = {}
    if hard.required_free_days:
        data["required_free_days"] = list(hard.required_free_days)
    if hard.earliest_start_time is not None:
        data["earliest_start_time"] = hard.earliest_start_time
    if hard.latest_end_time is not None:
        data["latest_end_time"] = hard.latest_end_time
    if hard.required_course_ids:
        data["required_course_names"] = list(hard.required_course_ids)
    if hard.excluded_course_ids:
        data["excluded_course_names"] = list(hard.excluded_course_ids)
    return PreferenceRules(**data)


def soft_preferences_to_rules(soft: SoftPreferences) -> PreferenceRules:
    """Convert durable SoftPreferences into ranking preferences."""

    data: dict[str, object] = {}
    if soft.preferred_free_days:
        data["preferred_free_days"] = list(soft.preferred_free_days)
    if soft.preferred_earliest_start_time is not None:
        data["preferred_first_class_time"] = soft.preferred_earliest_start_time
    if soft.preferred_latest_end_time is not None:
        # PreferenceRules currently exposes only preferred_first_class_time for
        # soft time-of-day ranking. Keep this field until a latest-end soft
        # ranking field exists.
        pass
    if soft.preferred_course_ids:
        data["preferred_course_names"] = list(soft.preferred_course_ids)
    if soft.disliked_course_ids:
        data["avoided_course_names"] = list(soft.disliked_course_ids)
    if soft.compact_schedule is not None:
        data["compact_schedule"] = soft.compact_schedule
    return PreferenceRules(**data)
