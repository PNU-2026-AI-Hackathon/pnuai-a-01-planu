"""Validated rules produced from a user's natural-language preferences."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .course import Day, time_to_minutes


class PreferenceRules(BaseModel):
    """Structured, deterministic input for filtering and ranking.

    Every field has a safe default so an LLM parsing failure can fall back to an
    empty ``PreferenceRules`` instance as required by the backend design.
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    # Hard filters
    excluded_days: list[Day] = Field(default_factory=list)
    earliest_start_time: str | None = None
    latest_end_time: str | None = None
    preferred_elective_areas: list[int] = Field(default_factory=list)
    required_keywords: list[str] = Field(default_factory=list)
    excluded_keywords: list[str] = Field(default_factory=list)

    # Soft ranking preferences
    preferred_free_days: list[Day] = Field(default_factory=list)
    avoid_morning_classes: bool = False
    morning_end_time: str = "10:00" # 아침 수업 기준을 10시로 설정
    minimize_consecutive_classes: bool = False
    max_consecutive_classes: int | None = Field(default=None, ge=1)

    @field_validator(
        "earliest_start_time", "latest_end_time", "morning_end_time"
    )
    @classmethod
    def validate_time(cls, value: str | None) -> str | None:
        if value is not None:
            time_to_minutes(value)
        return value

    @field_validator("preferred_elective_areas")
    @classmethod
    def validate_areas(cls, values: list[int]) -> list[int]:
        if any(not 1 <= value <= 7 for value in values):
            raise ValueError("elective areas must be between 1 and 7")
        return list(dict.fromkeys(values))

    @field_validator(
        "excluded_days", "preferred_free_days", "required_keywords", "excluded_keywords"
    )
    @classmethod
    def remove_duplicates(cls, values: list) -> list:
        return list(dict.fromkeys(values))

    @model_validator(mode="after")
    def validate_ranges(self) -> "PreferenceRules":
        if (
            self.earliest_start_time is not None
            and self.latest_end_time is not None
            and time_to_minutes(self.earliest_start_time)
            >= time_to_minutes(self.latest_end_time)
        ):
            raise ValueError("latest_end_time must be later than earliest_start_time")
        return self
