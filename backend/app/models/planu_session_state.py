"""Minimal session state shared by future agent tools and repositories."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from .session_preferences import CourseId, HardConstraints, SoftPreferences


class PlanuSessionState(BaseModel):
    """Persistent state for one PlaNU planning session.

    The model intentionally contains only durable session facts. Domain changes
    such as adding preferences or selecting courses should be handled by a
    service/tool and then persisted through a repository implementation.

    ``updated_at`` is the time when actual planning data such as department,
    uploaded catalogs, or selected courses last changed. Simple session access
    and TTL extension do not update it.
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    session_id: str = Field(min_length=1)
    department: str | None = None
    major_catalog_id: str | None = None
    elective_catalog_id: str | None = None
    selected_major_course_ids: list[CourseId] = Field(default_factory=list)
    hard_constraints: HardConstraints = Field(default_factory=HardConstraints)
    soft_preferences: SoftPreferences = Field(default_factory=SoftPreferences)
    created_at: datetime
    updated_at: datetime
    last_accessed_at: datetime
    expires_at: datetime
    version: int = Field(default=1, ge=1)

    @field_validator("session_id")
    @classmethod
    def validate_session_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("session_id must not be empty")
        return value

    @field_validator("selected_major_course_ids")
    @classmethod
    def validate_selected_major_course_ids(cls, value: list[str]) -> list[str]:
        seen: set[str] = set()
        for course_id in value:
            normalized_course_id = course_id.strip()
            if not normalized_course_id:
                raise ValueError("selected_major_course_ids must not contain empty ids")
            if normalized_course_id in seen:
                raise ValueError("selected_major_course_ids must not contain duplicates")
            seen.add(normalized_course_id)
        return value

    @field_validator(
        "created_at",
        "updated_at",
        "last_accessed_at",
        "expires_at",
    )
    @classmethod
    def validate_timezone_aware_datetime(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
            raise ValueError("datetime fields must include timezone information")
        return value

    @model_validator(mode="after")
    def validate_time_order(self) -> "PlanuSessionState":
        if self.updated_at < self.created_at:
            raise ValueError("updated_at must not be earlier than created_at")
        if self.last_accessed_at < self.created_at:
            raise ValueError("last_accessed_at must not be earlier than created_at")
        if self.expires_at <= self.last_accessed_at:
            raise ValueError("expires_at must be later than last_accessed_at")
        return self
