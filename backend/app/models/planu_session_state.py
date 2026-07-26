"""Minimal session state shared by future agent tools and repositories."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PlanuSessionState(BaseModel):
    """Persistent state for one PlaNU planning session.

    The model intentionally contains only durable session facts. Domain changes
    such as adding preferences or selecting courses should be handled by a
    service/tool and then persisted through a repository implementation.
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
    selected_major_course_ids: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    last_accessed_at: datetime
    expires_at: datetime

    @field_validator("session_id")
    @classmethod
    def validate_session_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("session_id must not be empty")
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
