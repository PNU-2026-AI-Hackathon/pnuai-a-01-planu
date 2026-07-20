"""Create server-trusted previews for natural-language major course selections."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from hashlib import sha256
from itertools import combinations
from typing import Protocol
from uuid import uuid4

from ..core.errors import AppError
from ..models.course import ClassTime, Course, Day
from ..models.major_selection import MajorSelectionParseResult
from ..schemas.major_schema import (
    AmbiguousMajorPreviewCourse,
    MajorPreviewClassTime,
    MajorPreviewConflict,
    MajorPreviewCourse,
    MajorPreviewResponse,
    MajorPreviewTimetableEntry,
    MatchedMajorPreviewCourse,
    UnmatchedMajorPreviewCourse,
)
from .major_course_matcher import MajorCourseMatcher
from .major_selection_parser import (
    EmptyMajorSelectionPromptError,
    InvalidMajorSelectionOutputError,
    MajorSelectionLLMError,
    MajorSelectionLLMTimeoutError,
    MajorSelectionParser,
)
from .session_store import SessionNotFoundError, SessionStore, session_store
from .session_store import SessionStage
from .timetable_validator import TimetableValidator


DAY_ORDER: dict[Day, int] = {
    Day.MON: 0,
    Day.TUE: 1,
    Day.WED: 2,
    Day.THU: 3,
    Day.FRI: 4,
    Day.SAT: 5,
    Day.SUN: 6,
}


class MajorSelectionParserProtocol(Protocol):
    def parse(self, prompt: str) -> MajorSelectionParseResult:
        ...


class MajorPreviewService:
    def __init__(
        self,
        *,
        store: SessionStore = session_store,
        parser: MajorSelectionParserProtocol | None = None,
        validator: TimetableValidator | None = None,
    ) -> None:
        self.store = store
        self.parser = parser or MajorSelectionParser()
        self.validator = validator or TimetableValidator()

    async def create_preview(self, session_id: str, prompt: str) -> MajorPreviewResponse:
        session_id = session_id.strip()
        prompt = prompt.strip()
        if not session_id:
            raise AppError("SESSION_NOT_FOUND", "세션 ID가 비어 있습니다.", status_code=400)
        if not prompt:
            raise AppError("EMPTY_MAJOR_PROMPT", "전공 선택 입력이 비어 있습니다.", status_code=400)

        try:
            session = self.store.get(session_id)
        except SessionNotFoundError as exc:
            raise AppError(
                "SESSION_NOT_FOUND",
                "세션을 찾을 수 없거나 만료되었습니다.",
                status_code=404,
            ) from exc

        if not session.major_candidates:
            raise AppError(
                "MAJOR_CATALOG_NOT_FOUND",
                "세션에 파싱된 전공 수강편람 데이터가 없습니다.",
                status_code=409,
            )
        if session.fixed_courses:
            raise AppError(
                "INVALID_SESSION_STAGE",
                "이미 전공 시간표가 확정된 세션에서는 미리보기를 생성할 수 없습니다.",
                status_code=409,
            )

        try:
            parse_result = await asyncio.to_thread(self.parser.parse, prompt)
        except EmptyMajorSelectionPromptError as exc:
            raise AppError(
                "EMPTY_MAJOR_PROMPT",
                "전공 선택 입력이 비어 있습니다.",
                status_code=400,
            ) from exc
        except (
            InvalidMajorSelectionOutputError,
            MajorSelectionLLMTimeoutError,
            MajorSelectionLLMError,
        ) as exc:
            raise AppError(
                "MAJOR_SELECTION_PARSE_FAILED",
                "전공 선택 내용을 구조화하지 못했습니다.",
                status_code=422,
            ) from exc

        match_result = MajorCourseMatcher(session.major_candidates).match(parse_result)
        matched_courses = [item.course for item in match_result.matched]
        has_time_conflict = self.validator.has_time_conflict(matched_courses)
        conflicts = _time_conflicts(matched_courses) if has_time_conflict else []
        preview_id = str(uuid4())

        response = MajorPreviewResponse(
            session_id=session.session_id,
            preview_id=preview_id,
            matched_courses=[
                MatchedMajorPreviewCourse(
                    reference=item.reference,
                    course=_preview_course(item.course),
                )
                for item in match_result.matched
            ],
            ambiguous_courses=[
                AmbiguousMajorPreviewCourse(
                    reference=item.reference,
                    candidates=[_preview_course(course) for course in item.candidates],
                    reason=item.reason,
                )
                for item in match_result.ambiguous
            ],
            unmatched_courses=[
                UnmatchedMajorPreviewCourse(
                    reference=item.reference,
                    reason=item.reason,
                )
                for item in match_result.unmatched
            ],
            ambiguous_texts=list(match_result.ambiguous_texts),
            timetable_entries=_timetable_entries(matched_courses),
            has_time_conflict=has_time_conflict,
            conflicts=conflicts,
            can_confirm=(
                bool(matched_courses)
                and not match_result.ambiguous
                and not match_result.unmatched
                and not match_result.ambiguous_texts
                and not has_time_conflict
            ),
        )

        try:
            self.store.update(
                session.session_id,
                session_stage=SessionStage.MAJOR_PREVIEW_CREATED,
                latest_major_preview={
                    "session_id": session.session_id,
                    "preview_id": preview_id,
                    "matched_course_ids": [course.course_id for course in matched_courses],
                    "ambiguous_courses": [
                        item.model_dump(mode="json") for item in response.ambiguous_courses
                    ],
                    "unmatched_courses": [
                        item.model_dump(mode="json") for item in response.unmatched_courses
                    ],
                    "ambiguous_texts": list(response.ambiguous_texts),
                    "has_time_conflict": response.has_time_conflict,
                    "conflicts": [item.model_dump(mode="json") for item in response.conflicts],
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "prompt_hash": sha256(prompt.encode("utf-8")).hexdigest(),
                },
            )
        except Exception as exc:
            raise AppError(
                "MAJOR_PREVIEW_SAVE_FAILED",
                "전공 미리보기 결과를 저장하지 못했습니다.",
                status_code=500,
            ) from exc

        return response


def _preview_course(course: Course) -> MajorPreviewCourse:
    return MajorPreviewCourse(
        course_id=course.course_id,
        course_name=course.course_name,
        category=course.category,
        area=course.area,
        credit=course.credit,
        division=course.division,
        professor=course.professor,
        class_times=[
            MajorPreviewClassTime(
                day=item.day,
                start=item.start,
                end=item.end,
                classroom=item.classroom,
                building_code=item.building_code,
            )
            for item in course.class_times
        ],
    )


def _timetable_entries(courses: list[Course]) -> list[MajorPreviewTimetableEntry]:
    entries = [
        MajorPreviewTimetableEntry(
            course_id=course.course_id,
            course_name=course.course_name,
            category=course.category,
            credit=course.credit,
            division=course.division,
            professor=course.professor,
            day=item.day,
            start=item.start,
            end=item.end,
            classroom=item.classroom,
            building_code=item.building_code,
        )
        for course in courses
        for item in course.class_times
    ]
    entries.sort(
        key=lambda item: (
            DAY_ORDER[item.day],
            item.start,
            item.end,
            item.course_name,
            item.division,
            item.course_id,
        )
    )
    return entries


def _time_conflicts(courses: list[Course]) -> list[MajorPreviewConflict]:
    conflicts: list[MajorPreviewConflict] = []
    for first, second in combinations(courses, 2):
        for first_time in first.class_times:
            for second_time in second.class_times:
                conflict = _overlap_conflict(first, first_time, second, second_time)
                if conflict is not None:
                    conflicts.append(conflict)
    return conflicts


def _overlap_conflict(
    first: Course,
    first_time: ClassTime,
    second: Course,
    second_time: ClassTime,
) -> MajorPreviewConflict | None:
    if not first_time.overlaps(second_time):
        return None
    return MajorPreviewConflict(
        first_course_id=first.course_id,
        second_course_id=second.course_id,
        day=first_time.day,
        overlap_start=max(first_time.start, second_time.start),
        overlap_end=min(first_time.end, second_time.end),
    )
