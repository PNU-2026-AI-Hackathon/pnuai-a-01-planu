"""Confirm a server-trusted major preview as the session's fixed timetable."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from pydantic import ValidationError

from ..core.errors import AppError
from ..models.course import Course
from ..models.input_timetable import InputTimetable
from ..schemas.major_schema import MajorConfirmResponse
from .major_preview_service import _preview_course, _time_conflicts
from .session_store import (
    InvalidMajorConfirmStageError,
    InvalidPreviewSessionError,
    MajorAlreadyConfirmedError,
    MajorCourseReferenceMismatchError,
    MajorPreviewNotFoundError,
    SessionNotFoundError,
    SessionStage,
    SessionStore,
    StaleMajorPreviewError,
    session_store,
)
from .timetable_validator import TimetableValidator


class MajorConfirmService:
    def __init__(
        self,
        *,
        store: SessionStore = session_store,
        validator: TimetableValidator | None = None,
    ) -> None:
        self.store = store
        self.validator = validator or TimetableValidator()

    async def confirm(self, session_id: str, preview_id: str) -> MajorConfirmResponse:
        return await self._confirm(session_id, preview_id, allow_reconfirm=False)

    async def reconfirm(self, session_id: str, preview_id: str) -> MajorConfirmResponse:
        return await self._confirm(session_id, preview_id, allow_reconfirm=True)

    async def _confirm(
        self,
        session_id: str,
        preview_id: str,
        *,
        allow_reconfirm: bool,
    ) -> MajorConfirmResponse:
        session_id = session_id.strip()
        preview_id = preview_id.strip()
        if not session_id:
            raise AppError("SESSION_NOT_FOUND", "세션 ID가 비어 있습니다.", status_code=400)
        if not preview_id:
            raise AppError("MAJOR_PREVIEW_NOT_FOUND", "미리보기 ID가 비어 있습니다.", status_code=400)

        try:
            session = self.store.get(session_id)
        except SessionNotFoundError as exc:
            raise AppError(
                "SESSION_NOT_FOUND",
                "세션을 찾을 수 없거나 만료되었습니다.",
                status_code=404,
            ) from exc

        if session.fixed_courses:
            if session.confirmed_major_preview_id == preview_id:
                latest_preview_id = (
                    session.latest_major_preview.get("preview_id")
                    if session.latest_major_preview is not None
                    else None
                )
                if not allow_reconfirm or latest_preview_id in (None, preview_id):
                    return self._response(
                        session_id=session.session_id,
                        preview_id=preview_id,
                        courses=session.fixed_courses,
                        session_stage=session.session_stage,
                        confirmed_major_credits=session.confirmed_major_credits,
                    )
            if not allow_reconfirm:
                raise AppError(
                    "INVALID_SESSION_STAGE",
                    "이미 다른 전공 미리보기로 확정된 세션입니다.",
                    status_code=409,
                )

        if not session.major_candidates:
            raise AppError(
                "INVALID_SESSION_STAGE",
                "세션에 파싱된 전공 수강편람 데이터가 없습니다.",
                status_code=409,
            )
        if (
            session.session_stage is not SessionStage.MAJOR_PREVIEW_CREATED
            and not (
                allow_reconfirm
                and session.confirmed_major_preview_id == preview_id
                and session.fixed_courses
            )
        ):
            raise AppError(
                "INVALID_SESSION_STAGE",
                "전공 미리보기 생성 이후에만 전공 시간표를 확정할 수 있습니다.",
                status_code=409,
            )

        preview = session.latest_major_preview
        if preview is None:
            raise AppError(
                "MAJOR_PREVIEW_NOT_FOUND",
                "확정할 전공 미리보기를 찾을 수 없습니다.",
                status_code=404,
            )
        if preview.get("session_id") not in (None, session.session_id):
            raise AppError(
                "INVALID_PREVIEW_SESSION",
                "현재 세션에서 생성된 전공 미리보기가 아닙니다.",
                status_code=403,
            )
        if preview.get("preview_id") != preview_id:
            raise AppError(
                "STALE_MAJOR_PREVIEW",
                "최신 전공 미리보기만 확정할 수 있습니다.",
                status_code=409,
            )

        matched_course_ids = self._confirmable_course_ids(preview)
        courses = self._resolve_courses(session.major_candidates, matched_course_ids)

        if self.validator.has_time_conflict(courses):
            raise AppError(
                "MAJOR_TIME_CONFLICT",
                "전공 과목끼리 시간이 겹쳐 확정할 수 없습니다.",
                status_code=409,
                details={
                    "conflicts": [
                        item.model_dump(mode="json") for item in _time_conflicts(courses)
                    ]
                },
            )

        try:
            timetable = InputTimetable(courses=courses)
        except ValidationError as exc:
            raise AppError(
                "MAJOR_PREVIEW_NOT_CONFIRMABLE",
                "전공 미리보기 데이터가 완전하지 않아 확정할 수 없습니다.",
                status_code=409,
            ) from exc

        confirmed_credits = float(timetable.total_credit or 0)
        confirmed_preview = deepcopy(preview)
        confirmed_preview["confirmed_at"] = datetime.now(timezone.utc).isoformat()
        confirmed_preview["is_confirmed"] = True

        try:
            if allow_reconfirm:
                updated = self.store.reconfirm_major_preview(
                    session.session_id,
                    preview_id=preview_id,
                    fixed_courses=courses,
                    confirmed_major_credits=confirmed_credits,
                    confirmed_preview=confirmed_preview,
                )
            else:
                updated = self.store.confirm_major_preview(
                    session.session_id,
                    preview_id=preview_id,
                    fixed_courses=courses,
                    confirmed_major_credits=confirmed_credits,
                    confirmed_preview=confirmed_preview,
                )
        except SessionNotFoundError as exc:
            raise AppError(
                "SESSION_NOT_FOUND",
                "세션을 찾을 수 없거나 만료되었습니다.",
                status_code=404,
            ) from exc
        except MajorAlreadyConfirmedError as exc:
            raise AppError(
                "INVALID_SESSION_STAGE",
                "이미 다른 전공 미리보기로 확정된 세션입니다.",
                status_code=409,
            ) from exc
        except InvalidMajorConfirmStageError as exc:
            raise AppError(
                "INVALID_SESSION_STAGE",
                "전공 미리보기 생성 이후에만 전공 시간표를 확정할 수 있습니다.",
                status_code=409,
            ) from exc
        except MajorPreviewNotFoundError as exc:
            raise AppError(
                "MAJOR_PREVIEW_NOT_FOUND",
                "확정할 전공 미리보기를 찾을 수 없습니다.",
                status_code=404,
            ) from exc
        except InvalidPreviewSessionError as exc:
            raise AppError(
                "INVALID_PREVIEW_SESSION",
                "현재 세션에서 생성된 전공 미리보기가 아닙니다.",
                status_code=403,
            ) from exc
        except StaleMajorPreviewError as exc:
            raise AppError(
                "STALE_MAJOR_PREVIEW",
                "최신 전공 미리보기만 확정할 수 있습니다.",
                status_code=409,
            ) from exc
        except MajorCourseReferenceMismatchError as exc:
            raise AppError(
                "MAJOR_COURSE_REFERENCE_INVALID",
                "전공 미리보기의 과목 참조가 수강편람 데이터와 일치하지 않습니다.",
                status_code=409,
            ) from exc
        except (TypeError, ValueError) as exc:
            raise AppError(
                "MAJOR_CONFIRM_SAVE_FAILED",
                "전공 시간표 확정 결과를 저장하지 못했습니다.",
                status_code=500,
            ) from exc

        return self._response(
            session_id=updated.session_id,
            preview_id=preview_id,
            courses=updated.fixed_courses,
            session_stage=updated.session_stage,
            confirmed_major_credits=updated.confirmed_major_credits,
        )

    def _confirmable_course_ids(self, preview: dict[str, Any]) -> list[str]:
        matched_course_ids = list(preview.get("matched_course_ids") or [])
        if not matched_course_ids:
            raise AppError(
                "MAJOR_PREVIEW_NOT_CONFIRMABLE",
                "확정할 수 있는 전공 과목이 없습니다.",
                status_code=409,
            )
        if preview.get("ambiguous_courses"):
            raise AppError(
                "MAJOR_PREVIEW_NOT_CONFIRMABLE",
                "분반이 확정되지 않은 전공 과목이 있습니다.",
                status_code=409,
            )
        if preview.get("unmatched_courses"):
            raise AppError(
                "MAJOR_PREVIEW_NOT_CONFIRMABLE",
                "수강편람에서 찾지 못한 전공 과목이 있습니다.",
                status_code=409,
            )
        if preview.get("ambiguous_texts"):
            raise AppError(
                "MAJOR_PREVIEW_NOT_CONFIRMABLE",
                "해석이 모호한 전공 입력이 있습니다.",
                status_code=409,
            )
        if preview.get("has_time_conflict"):
            raise AppError(
                "MAJOR_TIME_CONFLICT",
                "전공 과목끼리 시간이 겹쳐 확정할 수 없습니다.",
                status_code=409,
                details={"conflicts": list(preview.get("conflicts") or [])},
            )
        return matched_course_ids

    def _resolve_courses(
        self,
        candidates: list[Course],
        matched_course_ids: list[str],
    ) -> list[Course]:
        by_id = {course.course_id: course for course in candidates}
        courses: list[Course] = []
        for course_id in matched_course_ids:
            course = by_id.get(course_id)
            if course is None:
                raise AppError(
                    "MAJOR_COURSE_REFERENCE_INVALID",
                    "전공 미리보기의 과목 참조가 수강편람 데이터와 일치하지 않습니다.",
                    status_code=409,
                )
            courses.append(course)
        return courses

    @staticmethod
    def _response(
        *,
        session_id: str,
        preview_id: str,
        courses: list[Course],
        session_stage: SessionStage,
        confirmed_major_credits: float,
    ) -> MajorConfirmResponse:
        return MajorConfirmResponse(
            session_id=session_id,
            preview_id=preview_id,
            confirmed_courses=[_preview_course(course) for course in courses],
            confirmed_course_count=len(courses),
            confirmed_major_credits=confirmed_major_credits,
            session_stage=session_stage,
        )
