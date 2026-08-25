"""Public API DTOs for PlaNU agent runtime responses."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ..agent_tools.schemas import SessionStateSummary
from .condition_summary_schema import ConditionSummaryDto
from ..agents.session_state_agent import AgentCourseCandidate, UnresolvedSessionRequest
from ..models.timetable_selection import SelectedTimetable


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, validate_assignment=True)


class SessionCreateRequest(_Model):
    department: str | None = Field(default=None, min_length=1)


class SessionCreateResponse(_Model):
    session_id: str = Field(min_length=1)
    created_at: str
    expires_at: str


class ConfirmationOption(_Model):
    id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    description: str | None = None
    course_id: str | None = None
    section_id: str | None = None
    candidate_id: str | None = None


class ConfirmationDto(_Model):
    reason: str
    question: str
    options: list[ConfirmationOption] = Field(default_factory=list)


class TimetableCourseDto(_Model):
    course_id: str
    section_id: str
    course_code: str | None = None
    course_name: str | None = None
    section: str | None = None
    professor: str | None = None
    day: str | None = None
    start_time: str | None = None
    end_time: str | None = None
    building: str | None = None
    classroom: str | None = None
    credits: float | None = None


class TimetableCandidateDto(_Model):
    rank: int | None = None
    candidate_id: str
    comparison_score: float | None = Field(
        default=None,
        description="Relative ranking score used only to compare candidates; it is not a 0-100 satisfaction percentage.",
    )
    total_credits: float
    courses: list[TimetableCourseDto] = Field(default_factory=list)
    advantages: list[str] = Field(default_factory=list)
    trade_offs: list[str] = Field(default_factory=list)


class SelectedTimetableDto(_Model):
    candidate_id: str
    total_credits: float
    section_ids: list[str] = Field(default_factory=list)
    courses: list[TimetableCourseDto] = Field(default_factory=list)
    selected_at: str | None = None
    status: str | None = None


class PlanuChatRequest(_Model):
    message: str = Field(min_length=1)
    request_id: str | None = Field(default=None, min_length=1)


class PlanuChatResponse(_Model):
    session_id: str
    message: str
    changed: bool = False
    needs_confirmation: bool = False
    confirmation: ConfirmationDto | None = None
    unresolved_requests: list[UnresolvedSessionRequest] = Field(default_factory=list)
    candidate_courses: list[AgentCourseCandidate] = Field(default_factory=list)
    timetable_candidates: list[TimetableCandidateDto] = Field(default_factory=list)
    selected_timetable: SelectedTimetableDto | None = None
    session_summary: SessionStateSummary | None = None
    condition_summary: ConditionSummaryDto | None = None


class LegacyAgentMessageResponse(_Model):
    success: bool
    session_id: str | None = None
    request_id: str | None = None
    message: str
    changed: bool = False
    partially_applied: bool = False
    needs_confirmation: bool = False
    confirmation: ConfirmationDto | None = None
    session_summary: SessionStateSummary | None = None
    condition_summary: ConditionSummaryDto | None = None
    candidate_courses: list[AgentCourseCandidate] = Field(default_factory=list)
    timetable_candidates: list[TimetableCandidateDto] = Field(default_factory=list)
    selected_timetable: SelectedTimetableDto | None = None
    unresolved_requests: list[UnresolvedSessionRequest] = Field(default_factory=list)
    executed_tools: list[dict[str, Any]] = Field(default_factory=list)
    failed_tools: list[dict[str, Any]] = Field(default_factory=list)
    error: dict[str, Any] | None = None


class SelectedTimetableResponse(_Model):
    session_id: str
    selected_timetable: SelectedTimetableDto | None = None


def selected_timetable_from_domain(
    selected: SelectedTimetable | None,
    *,
    status: str | None = None,
) -> SelectedTimetableDto | None:
    if selected is None:
        return None
    return SelectedTimetableDto(
        candidate_id=selected.candidate_id,
        total_credits=selected.total_credits,
        section_ids=list(selected.section_ids),
        courses=[
            TimetableCourseDto(course_id=course_id, section_id=section_id)
            for course_id, section_id in zip(selected.course_ids, selected.section_ids, strict=False)
        ],
        selected_at=selected.selected_at.isoformat(),
        status=status,
    )
