"""Structured timetable revision preparation models."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .session_preferences import HardConstraints, SoftPreferences
from .timetable_generation import SectionSource, TimetableGenerationRequest


class _RevisionModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )


class TimetableRevisionRequest(_RevisionModel):
    """Deterministic request for preparing a revision from a selected timetable."""

    session_id: str = Field(min_length=1)
    base_candidate_id: str | None = Field(default=None, min_length=1)
    replace_course_ids: list[str] = Field(default_factory=list)
    replace_section_ids: list[str] = Field(default_factory=list)
    excluded_course_ids: list[str] = Field(default_factory=list)
    excluded_section_ids: list[str] = Field(default_factory=list)
    required_course_ids: list[str] = Field(default_factory=list)
    temporary_hard_constraints: HardConstraints | None = None
    temporary_soft_preferences: SoftPreferences | None = None
    target_additional_course_count: int | None = Field(default=1, ge=0)
    max_results: int = Field(default=3, ge=1)

    @field_validator(
        "replace_course_ids",
        "replace_section_ids",
        "excluded_course_ids",
        "excluded_section_ids",
        "required_course_ids",
    )
    @classmethod
    def validate_id_list(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("id lists must not contain empty values")
        return list(dict.fromkeys(values))

    @model_validator(mode="after")
    def validate_changes_present(self) -> "TimetableRevisionRequest":
        if (
            not self.replace_course_ids
            and not self.replace_section_ids
            and not self.excluded_course_ids
            and not self.excluded_section_ids
            and not self.required_course_ids
            and self.temporary_hard_constraints is None
            and self.temporary_soft_preferences is None
        ):
            raise ValueError("at least one revision change or temporary preference is required")
        return self


class TimetableRevisionPreparationResult(_RevisionModel):
    success: bool
    session_id: str
    base_candidate_id: str | None = None
    selected_timetable_status: str | None = None
    locked_section_ids: list[str] = Field(default_factory=list)
    locked_section_sources: list[SectionSource] = Field(default_factory=list)
    replaceable_section_ids: list[str] = Field(default_factory=list)
    excluded_section_ids: list[str] = Field(default_factory=list)
    excluded_course_ids: list[str] = Field(default_factory=list)
    required_course_ids: list[str] = Field(default_factory=list)
    additional_discovery: list[dict[str, object]] = Field(default_factory=list)
    generation_request: TimetableGenerationRequest | None = None
    needs_confirmation: bool = False
    confirmation_reasons: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    message: str
