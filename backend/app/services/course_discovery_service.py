"""Structured course catalog discovery service."""

from __future__ import annotations

from collections import defaultdict
from difflib import SequenceMatcher

from ..models.course import Day, time_to_minutes
from ..models.course_discovery import (
    CourseCandidate,
    CourseDiscoveryRequest,
    CourseDiscoveryResult,
    CourseMatchType,
    CourseSection,
    DiscoveryResolution,
    normalize_course_search_text,
)
from ..repositories.catalog_repository import CatalogRepository


_MATCH_PRIORITY = {
    CourseMatchType.COURSE_ID_EXACT: 100,
    CourseMatchType.COURSE_CODE_EXACT: 95,
    CourseMatchType.NAME_EXACT: 90,
    CourseMatchType.NAME_PREFIX: 75,
    CourseMatchType.NAME_CONTAINS: 60,
    CourseMatchType.NAME_SIMILAR: 45,
    CourseMatchType.CONDITION: 10,
}


class CourseDiscoveryService:
    """Find course-level candidates from structured catalog criteria."""

    def __init__(self, repository: CatalogRepository) -> None:
        self._repository = repository

    def discover(self, request: CourseDiscoveryRequest) -> CourseDiscoveryResult:
        sections = self._repository.list_sections(request.catalog_id)
        grouped = _group_sections(sections)
        candidates: list[CourseCandidate] = []

        for course_id, course_sections in grouped.items():
            candidate = self._candidate_for_group(course_id, course_sections, request)
            if candidate is not None:
                candidates.append(candidate)

        if request.query:
            candidates.sort(key=_explicit_sort_key)
        else:
            candidates.sort(key=_condition_sort_key)

        limited = candidates[: request.limit]
        resolution = self._resolution(request, candidates)
        success = resolution is not DiscoveryResolution.NOT_FOUND
        return CourseDiscoveryResult(
            success=success,
            catalog_id=request.catalog_id,
            request=request,
            candidates=limited,
            resolution=resolution,
            total_scanned_courses=len(grouped),
            total_matched_courses=len(candidates),
            message=_result_message(resolution, len(candidates), request.limit),
            error=None,
        )

    def search_by_name(
        self,
        *,
        catalog_id: str,
        query: str,
        limit: int = 20,
    ) -> CourseDiscoveryResult:
        """Search a catalog by explicit course name, course id, or course code."""

        request = CourseDiscoveryRequest(
            catalog_id=catalog_id,
            query=query,
            limit=limit,
        )
        return self.discover(request)

    def get_course_sections(
        self,
        *,
        catalog_id: str,
        course_id: str,
        section_ids: list[str] | None = None,
    ) -> list[CourseSection]:
        sections = self._repository.get_course_sections(catalog_id, course_id)
        if section_ids is None:
            return sections
        wanted = set(section_ids)
        return [section for section in sections if section.section_id in wanted]

    def get_section_details(self, *, catalog_id: str, section_id: str) -> CourseSection:
        return self._repository.get_section(catalog_id, section_id)

    def _candidate_for_group(
        self,
        course_id: str,
        sections: list[CourseSection],
        request: CourseDiscoveryRequest,
    ) -> CourseCandidate | None:
        first = sections[0]
        if request.included_course_ids and course_id not in request.included_course_ids:
            return None
        if course_id in request.excluded_course_ids:
            return None
        if request.category is not None and first.category is not request.category:
            return None
        if request.area is not None and first.area != request.area:
            return None
        if request.department is not None and first.department != request.department:
            return None

        query_match = _query_match_type(request.query, first, sections)
        if request.query is not None and query_match is None:
            return None

        matching_sections = [
            section
            for section in sections
            if _section_matches(section, request)
        ]
        if not matching_sections:
            return None

        match_type = query_match or CourseMatchType.CONDITION
        reasons = _match_reasons(request, first, match_type, len(matching_sections))
        rank_score = (
            _MATCH_PRIORITY[match_type] * 1000
            + len(matching_sections) * 10
            + len(reasons)
        )
        return CourseCandidate(
            course_id=course_id,
            course_code=first.course_code,
            course_name=first.course_name,
            category=first.category,
            area=first.area,
            department=first.department,
            total_section_count=len(sections),
            matching_section_count=len(matching_sections),
            matching_section_ids=[section.section_id for section in matching_sections],
            match_reasons=reasons,
            match_type=match_type,
            rank_score=rank_score,
        )

    @staticmethod
    def _resolution(
        request: CourseDiscoveryRequest,
        candidates: list[CourseCandidate],
    ) -> DiscoveryResolution:
        if not candidates:
            return DiscoveryResolution.NOT_FOUND
        if not request.query:
            return DiscoveryResolution.CANDIDATES

        exact_types = {
            CourseMatchType.COURSE_ID_EXACT,
            CourseMatchType.COURSE_CODE_EXACT,
            CourseMatchType.NAME_EXACT,
        }
        exact_candidates = [
            candidate
            for candidate in candidates
            if candidate.match_type in exact_types
        ]
        if len(exact_candidates) == 1:
            return DiscoveryResolution.EXACT
        return DiscoveryResolution.AMBIGUOUS


def _group_sections(sections: list[CourseSection]) -> dict[str, list[CourseSection]]:
    grouped: dict[str, list[CourseSection]] = defaultdict(list)
    for section in sections:
        grouped[section.course_id].append(section)
    return {
        course_id: sorted(items, key=lambda item: (item.division, item.section_id))
        for course_id, items in grouped.items()
    }


def _query_match_type(
    query: str | None,
    first: CourseSection,
    sections: list[CourseSection],
) -> CourseMatchType | None:
    if query is None:
        return None
    normalized_query = normalize_course_search_text(query)
    normalized_name = normalize_course_search_text(first.course_name)
    normalized_course_id = normalize_course_search_text(first.course_id)
    normalized_code = normalize_course_search_text(first.course_code)
    normalized_section_ids = {
        normalize_course_search_text(section.section_id)
        for section in sections
    }

    if normalized_query == normalized_course_id or normalized_query in normalized_section_ids:
        return CourseMatchType.COURSE_ID_EXACT
    if normalized_query == normalized_code:
        return CourseMatchType.COURSE_CODE_EXACT
    if normalized_query == normalized_name:
        return CourseMatchType.NAME_EXACT
    if normalized_name.startswith(normalized_query):
        return CourseMatchType.NAME_PREFIX
    if normalized_query in normalized_name:
        return CourseMatchType.NAME_CONTAINS
    if SequenceMatcher(None, normalized_query, normalized_name).ratio() >= 0.72:
        return CourseMatchType.NAME_SIMILAR
    return None


def _section_matches(section: CourseSection, request: CourseDiscoveryRequest) -> bool:
    if request.allowed_days:
        section_days = {item.day for item in section.class_times}
        if not any(day in section_days for day in request.allowed_days):
            return False
    if request.excluded_days and any(
        item.day in request.excluded_days for item in section.class_times
    ):
        return False
    if request.earliest_start_time is not None:
        earliest = time_to_minutes(request.earliest_start_time)
        if any(item.start_minutes < earliest for item in section.class_times):
            return False
    if request.latest_end_time is not None:
        latest = time_to_minutes(request.latest_end_time)
        if any(item.end_minutes > latest for item in section.class_times):
            return False
    return True


def _match_reasons(
    request: CourseDiscoveryRequest,
    first: CourseSection,
    match_type: CourseMatchType,
    matching_count: int,
) -> list[str]:
    reasons: list[str] = []
    if request.query:
        reasons.append({
            CourseMatchType.COURSE_ID_EXACT: "course ID 정확 일치",
            CourseMatchType.COURSE_CODE_EXACT: "과목코드 정확 일치",
            CourseMatchType.NAME_EXACT: "과목명 정확 일치",
            CourseMatchType.NAME_PREFIX: "과목명 시작 일치",
            CourseMatchType.NAME_CONTAINS: "과목명 포함 일치",
            CourseMatchType.NAME_SIMILAR: "과목명 유사 일치",
            CourseMatchType.CONDITION: "조건 일치",
        }[match_type])
    if request.category is not None:
        reasons.append(request.category.korean_label)
    if request.area is not None:
        reasons.append(f"교양 {request.area}영역")
    elif first.area is not None and first.category.name.startswith("GENERAL"):
        reasons.append(f"교양 {first.area}영역")
    if request.department is not None:
        reasons.append(f"{request.department} 개설")
    if request.allowed_days:
        days = ", ".join(day.value for day in request.allowed_days)
        reasons.append(f"{days} 수업 분반 {matching_count}개")
    if request.excluded_days:
        days = ", ".join(day.value for day in request.excluded_days)
        reasons.append(f"{days} 수업이 없는 분반 {matching_count}개")
    if request.earliest_start_time is not None:
        reasons.append(f"{request.earliest_start_time} 이후 시작 분반 {matching_count}개")
    if request.latest_end_time is not None:
        reasons.append(f"{request.latest_end_time} 이전 종료 분반 {matching_count}개")
    if request.excluded_course_ids:
        reasons.append("제외 과목 ID 미포함")
    if not reasons:
        reasons.append("catalog 둘러보기 후보")
    return reasons


def _explicit_sort_key(candidate: CourseCandidate) -> tuple[int, str, str]:
    return (
        -_MATCH_PRIORITY[candidate.match_type],
        candidate.course_name,
        candidate.course_code,
    )


def _condition_sort_key(candidate: CourseCandidate) -> tuple[int, int, str, str]:
    return (
        -candidate.matching_section_count,
        -len(candidate.match_reasons),
        candidate.course_name,
        candidate.course_code,
    )


def _result_message(
    resolution: DiscoveryResolution,
    matched_count: int,
    limit: int,
) -> str:
    if resolution is DiscoveryResolution.NOT_FOUND:
        return "조건에 맞는 과목 후보를 찾지 못했습니다."
    if resolution is DiscoveryResolution.EXACT:
        return "명시적 검색어와 정확히 일치하는 과목을 찾았습니다."
    if resolution is DiscoveryResolution.AMBIGUOUS:
        return f"명시적 검색어와 유사한 과목 후보 {min(matched_count, limit)}개를 찾았습니다."
    return f"조건에 맞는 과목 후보 {min(matched_count, limit)}개를 찾았습니다."
