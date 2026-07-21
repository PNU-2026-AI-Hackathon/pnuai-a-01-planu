"""Response schemas for session lookup APIs."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from ..models.course import Course
from ..services.session_store import SessionStage


class _Model(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )


class MajorCandidatesResponse(_Model):
    session_id: str = Field(min_length=1)
    session_stage: SessionStage
    department: str = Field(min_length=1)
    major_candidates: list[Course] = Field(default_factory=list)
