"""Helpers for extracting additional preference rules from free text."""

from __future__ import annotations

from typing import Any

from ..models.preference import PreferenceRules, merge_preference_rules


def build_preference_parse_payload(
    *,
    free_text: str,
    selected_preferences: PreferenceRules | None = None,
) -> dict[str, Any]:
    """Build the LLM input while keeping UI-selected rules authoritative.

    The LLM should use ``selected_preferences`` as context and return only
    additional rules found in ``free_text``. Callers must merge its validated
    output with ``merge_preference_rules`` so duplicate fields are not scored or
    filtered twice.
    """

    selected = selected_preferences or PreferenceRules()
    return {
        "selected_preferences": selected.model_dump(mode="json"),
        "free_text": free_text.strip(),
        "instruction": (
            "Extract only additional timetable preferences that are not already "
            "represented in selected_preferences. Return PreferenceRules JSON."
        ),
    }


def merge_selected_and_llm_preferences(
    *,
    selected_preferences: PreferenceRules | None = None,
    llm_preferences: PreferenceRules | None = None,
) -> PreferenceRules:
    """Apply the documented precedence: UI selection, then LLM, then defaults."""

    return merge_preference_rules(selected_preferences, llm_preferences)
