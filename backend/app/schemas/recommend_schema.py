"""Request/response schemas for timetable recommendation."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from ..models.preference import PreferenceRules
from ..models.timetable import Timetable


class RecommendRequest(BaseModel):
    """Input accepted by ``POST /recommend``.

    ``selected_preferences`` comes from explicit UI controls. ``free_text`` is
    passed to the LLM only to extract additional rules not covered by the UI.
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    session_id: str = Field(min_length=1)
    required_general_count: int = Field(default=0, ge=0)
    elective_general_count: int = Field(default=0, ge=0)
    selected_preferences: PreferenceRules = Field(default_factory=PreferenceRules)
    free_text: str = Field(default="", max_length=1000)

    @property
    def user_prompt(self) -> str:
        """Backward-compatible alias for earlier design docs."""

        return self.free_text


class RecommendResponse(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    recommendations: list[Timetable]
