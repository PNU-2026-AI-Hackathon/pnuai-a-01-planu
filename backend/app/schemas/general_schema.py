"""Request/response schemas for general-course preparation."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ..services.session_store import SessionStage


class _Model(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )


class GeneralPreparationResponse(_Model):
    session_id: str = Field(min_length=1)
    session_stage: SessionStage
    required_course_count: int = Field(ge=0)
    elective_course_count: int = Field(ge=0)
    excluded_course_count: int = Field(ge=0)
    data_source: Literal["uploaded_catalog", "fallback_catalog"]
    elective_area: int | None = Field(default=None, ge=1, le=7)
    warnings: list[str] = Field(default_factory=list)
