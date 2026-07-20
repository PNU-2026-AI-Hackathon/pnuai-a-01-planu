"""Request and response schemas for catalog upload APIs."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from ..services.session_store import SessionStage


class _Model(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )


class MajorCatalogUploadResponse(_Model):
    session_id: str = Field(min_length=1)
    session_stage: SessionStage
    parsed_course_count: int = Field(ge=1)
    warnings: list[str] = Field(default_factory=list)
