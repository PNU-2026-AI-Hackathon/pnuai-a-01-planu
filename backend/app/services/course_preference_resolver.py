"""Boundary for resolving parsed course-name preferences to course ids.

Expected flow:

User free text
-> LLM ``PreferenceRules`` / ``HardPreferenceConditions`` / ``SoftPreferenceConditions``
-> compare course names with the uploaded catalog
-> resolve one or more concrete ``course_id`` values
-> store ids in ``HardConstraints`` / ``SoftPreferences`` through ``SessionService``

This module intentionally does not implement catalog search yet. Course names
can map to multiple divisions, so callers must not guess a single course id from
a name without an explicit resolver decision.
"""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field


class ResolvedCoursePreferences(BaseModel):
    """Course-id preferences ready to apply to session preference state."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    required_course_ids: list[str] = Field(default_factory=list)
    excluded_course_ids: list[str] = Field(default_factory=list)
    preferred_course_ids: list[str] = Field(default_factory=list)
    disliked_course_ids: list[str] = Field(default_factory=list)


class CoursePreferenceResolver(Protocol):
    """Resolve parser-level course names against a concrete uploaded catalog.

    Implementations should return only catalog-backed course ids, or report
    ambiguity to their caller instead of selecting an arbitrary division.
    """

    def resolve(
        self,
        *,
        session_id: str,
        catalog_id: str,
        required_course_names: list[str],
        excluded_course_names: list[str],
        preferred_course_names: list[str],
        avoided_course_names: list[str],
    ) -> ResolvedCoursePreferences:
        """Return resolved course-id preferences for session storage."""
