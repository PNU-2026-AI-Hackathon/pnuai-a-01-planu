"""Deterministic preparation for agent timetable generation requests."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from ..agent_tools.schemas import SessionStateSummary
from ..models.course_discovery import CourseCandidate
from ..models.timetable_generation import SectionSource, TimetableGenerationRequest


class TimetablePreparationIssueCode(str, Enum):
    MISSING_DEPARTMENT = "MISSING_DEPARTMENT"
    MISSING_MAJOR_CATALOG = "MISSING_MAJOR_CATALOG"
    MISSING_SELECTED_MAJOR_COURSES = "MISSING_SELECTED_MAJOR_COURSES"
    MAJOR_SECTION_UNCONFIRMED = "MAJOR_SECTION_UNCONFIRMED"
    MISSING_CANDIDATE_CATALOG = "MISSING_CANDIDATE_CATALOG"
    MISSING_CANDIDATE_SECTIONS = "MISSING_CANDIDATE_SECTIONS"
    MISSING_TARGET = "MISSING_TARGET"
    CONFLICTING_COURSE_CONSTRAINT = "CONFLICTING_COURSE_CONSTRAINT"
    TARGET_SMALLER_THAN_REQUIRED = "TARGET_SMALLER_THAN_REQUIRED"
    INVALID_REQUEST = "INVALID_REQUEST"


class TimetablePreparationIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: TimetablePreparationIssueCode
    message: str
    field: str | None = None
    values: list[str] = Field(default_factory=list)
    requires_user_confirmation: bool = True


class TimetablePreparationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ready: bool
    request: TimetableGenerationRequest | None = None
    issues: list[TimetablePreparationIssue] = Field(default_factory=list)


class TimetablePreparationOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_catalog_id: str | None = Field(default=None, min_length=1)
    discovered_candidates: list[CourseCandidate] = Field(default_factory=list)
    fixed_section_sources: list[SectionSource] | None = None
    one_shot_required_course_ids: list[str] = Field(default_factory=list)
    one_shot_excluded_course_ids: list[str] = Field(default_factory=list)
    target_additional_course_count: int | None = Field(default=None, ge=0)
    target_additional_credits: float | None = Field(default=None, ge=0)
    max_candidate_courses: int = Field(default=20, ge=1, le=50)
    max_sections_per_course: int = Field(default=5, ge=1, le=20)
    max_results: int = Field(default=3, ge=1, le=10)
    max_search_nodes: int = Field(default=5000, ge=1, le=50000)

    @field_validator("one_shot_required_course_ids", "one_shot_excluded_course_ids")
    @classmethod
    def dedupe_ids(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(values))


class TimetablePreparationService:
    """Build generation requests from prepared session and discovery data.

    This layer does not parse natural language, fetch catalog data, select among
    ambiguous sections, run backtracking, score Soft preferences, or save state.
    """

    def prepare(
        self,
        summary: SessionStateSummary,
        options: TimetablePreparationOptions,
    ) -> TimetablePreparationResult:
        issues = self._readiness_issues(summary, options)
        fixed_sources = self._fixed_sources(summary, options)
        candidate_sources = self._candidate_sources(options)
        required_course_ids = list(
            dict.fromkeys(
                [
                    *summary.hard_constraints.required_course_ids,
                    *options.one_shot_required_course_ids,
                ]
            )
        )
        excluded_course_ids = list(
            dict.fromkeys(
                [
                    *options.one_shot_excluded_course_ids,
                    *summary.hard_constraints.excluded_course_ids,
                ]
            )
        )

        overlap = sorted(set(required_course_ids) & set(excluded_course_ids))
        if overlap:
            issues.append(
                TimetablePreparationIssue(
                    code=TimetablePreparationIssueCode.CONFLICTING_COURSE_CONSTRAINT,
                    message="같은 과목이 필수 과목과 제외 과목에 동시에 포함되어 있습니다.",
                    field="required_course_ids/excluded_course_ids",
                    values=overlap,
                )
            )

        if (
            options.target_additional_course_count is not None
            and len(options.one_shot_required_course_ids)
            > options.target_additional_course_count
        ):
            issues.append(
                TimetablePreparationIssue(
                    code=TimetablePreparationIssueCode.TARGET_SMALLER_THAN_REQUIRED,
                    message="목표 추가 과목 수보다 이번 요청의 필수 과목 수가 많습니다.",
                    field="target_additional_course_count",
                    values=options.one_shot_required_course_ids,
                )
            )

        if issues:
            return TimetablePreparationResult(ready=False, issues=issues)

        try:
            request = TimetableGenerationRequest(
                fixed_section_sources=fixed_sources,
                candidate_course_ids=list(candidate_sources),
                candidate_section_sources_by_course=candidate_sources,
                required_course_ids=required_course_ids,
                excluded_course_ids=excluded_course_ids,
                required_free_days=list(summary.hard_constraints.required_free_days),
                earliest_start_time=summary.hard_constraints.earliest_start_time,
                latest_end_time=summary.hard_constraints.latest_end_time,
                min_credit=summary.hard_constraints.min_credit,
                max_credit=summary.hard_constraints.max_credit,
                department=summary.department,
                target_additional_course_count=options.target_additional_course_count,
                target_additional_credits=options.target_additional_credits,
                max_results=options.max_results,
                max_search_nodes=options.max_search_nodes,
            )
        except ValidationError as exc:
            first = exc.errors()[0]
            return TimetablePreparationResult(
                ready=False,
                issues=[
                    TimetablePreparationIssue(
                        code=TimetablePreparationIssueCode.INVALID_REQUEST,
                        message=str(first["msg"]),
                        field=".".join(str(part) for part in first["loc"]),
                    )
                ],
            )
        return TimetablePreparationResult(ready=True, request=request)

    def _readiness_issues(
        self,
        summary: SessionStateSummary,
        options: TimetablePreparationOptions,
    ) -> list[TimetablePreparationIssue]:
        issues: list[TimetablePreparationIssue] = []
        if summary.department is None:
            issues.append(
                _issue(
                    TimetablePreparationIssueCode.MISSING_DEPARTMENT,
                    "학과 정보가 필요합니다.",
                    "department",
                )
            )
        if summary.major_catalog_id is None:
            issues.append(
                _issue(
                    TimetablePreparationIssueCode.MISSING_MAJOR_CATALOG,
                    "전공 수강편람 catalog ID가 필요합니다.",
                    "major_catalog_id",
                )
            )
        if not summary.selected_major_course_ids:
            issues.append(
                _issue(
                    TimetablePreparationIssueCode.MISSING_SELECTED_MAJOR_COURSES,
                    "선택된 전공 과목 또는 분반이 필요합니다.",
                    "selected_major_course_ids",
                )
            )
        if options.candidate_catalog_id is None:
            issues.append(
                _issue(
                    TimetablePreparationIssueCode.MISSING_CANDIDATE_CATALOG,
                    "시간표에 추가할 후보 catalog ID가 필요합니다.",
                    "candidate_catalog_id",
                )
            )
        if (
            options.target_additional_course_count is None
            and options.target_additional_credits is None
        ):
            issues.append(
                _issue(
                    TimetablePreparationIssueCode.MISSING_TARGET,
                    "추가할 과목 수 또는 학점 목표가 필요합니다.",
                    "target",
                )
            )
        if not options.discovered_candidates:
            issues.append(
                _issue(
                    TimetablePreparationIssueCode.MISSING_CANDIDATE_SECTIONS,
                    "생성에 사용할 후보 분반이 필요합니다.",
                    "discovered_candidates",
                )
            )
        if options.fixed_section_sources is None and any(
            "-" not in course_id for course_id in summary.selected_major_course_ids
        ):
            issues.append(
                _issue(
                    TimetablePreparationIssueCode.MAJOR_SECTION_UNCONFIRMED,
                    "전공 course ID만 선택되어 있어 고정 분반을 확정할 수 없습니다.",
                    "selected_major_course_ids",
                    summary.selected_major_course_ids,
                )
            )
        return issues

    def _fixed_sources(
        self,
        summary: SessionStateSummary,
        options: TimetablePreparationOptions,
    ) -> list[SectionSource]:
        if options.fixed_section_sources is not None:
            return list(options.fixed_section_sources)
        if summary.major_catalog_id is None:
            return []
        return [
            SectionSource(catalog_id=summary.major_catalog_id, section_id=section_id)
            for section_id in summary.selected_major_course_ids
            if "-" in section_id
        ]

    def _candidate_sources(
        self,
        options: TimetablePreparationOptions,
    ) -> dict[str, list[SectionSource]]:
        if options.candidate_catalog_id is None:
            return {}
        sources: dict[str, list[SectionSource]] = {}
        for candidate in options.discovered_candidates[: options.max_candidate_courses]:
            section_ids = candidate.matching_section_ids[: options.max_sections_per_course]
            if not section_ids:
                continue
            sources[candidate.course_id] = [
                SectionSource(
                    catalog_id=options.candidate_catalog_id,
                    section_id=section_id,
                )
                for section_id in section_ids
            ]
        return sources


def _issue(
    code: TimetablePreparationIssueCode,
    message: str,
    field: str,
    values: list[str] | None = None,
) -> TimetablePreparationIssue:
    return TimetablePreparationIssue(
        code=code,
        message=message,
        field=field,
        values=values or [],
    )
