"""Adapters between durable session preferences and generation PreferenceRules."""

from __future__ import annotations

from ..models.preference import PreferenceRules
from ..models.session_preferences import HardConstraints, SoftPreferences


def hard_constraints_to_rules(hard: HardConstraints) -> PreferenceRules:
    """Convert durable HardConstraints into generator hard rules."""

    return PreferenceRules(
        required_free_days=list(hard.required_free_days),
        earliest_start_time=hard.earliest_start_time,
        latest_end_time=hard.latest_end_time,
        required_course_names=list(hard.required_course_ids),
        excluded_course_names=list(hard.excluded_course_ids),
    )


def soft_preferences_to_rules(soft: SoftPreferences) -> PreferenceRules:
    """Convert durable SoftPreferences into ranking preferences."""

    return PreferenceRules(
        preferred_free_days=list(soft.preferred_free_days),
        preferred_first_class_time=soft.preferred_earliest_start_time,
        preferred_course_names=list(soft.preferred_course_ids),
        avoided_course_names=list(soft.disliked_course_ids),
        compact_schedule=bool(soft.compact_schedule),
    )
