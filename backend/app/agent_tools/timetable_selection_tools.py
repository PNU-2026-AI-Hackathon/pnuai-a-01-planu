"""Agent-callable tools for selected timetables and revision preparation."""

from __future__ import annotations

from collections.abc import Mapping

from pydantic import BaseModel, ValidationError

from ..models.timetable_generation import GeneratedTimetableCandidate
from ..models.timetable_revision import (
    TimetableRevisionPreparationResult,
    TimetableRevisionRequest,
)
from ..services.session_service import SessionService
from ..services.timetable_revision_preparation_service import (
    TimetableRevisionPreparationService,
)
from .errors import service_error_result, validation_error_result
from .schemas import SessionIdInput, SessionStateSummary, SessionToolResult


class SelectTimetableCandidateInput(BaseModel):
    session_id: str
    candidate: GeneratedTimetableCandidate


class TimetableSelectionTools:
    """Thin tool layer over selected-timetable and revision services."""

    def __init__(
        self,
        *,
        session_service: SessionService,
        revision_preparation_service: TimetableRevisionPreparationService,
    ) -> None:
        self._session_service = session_service
        self._revision_preparation_service = revision_preparation_service

    def select_timetable_candidate(
        self,
        data: SelectTimetableCandidateInput | Mapping[str, object],
    ) -> SessionToolResult:
        """Store a timetable only after the user explicitly selects it."""

        try:
            request = SelectTimetableCandidateInput.model_validate(data)
            before = self._session_service.get_session(request.session_id)
            after = self._session_service.select_timetable_candidate(
                request.session_id,
                request.candidate,
            )
        except ValidationError as exc:
            return validation_error_result(exc)
        except Exception as exc:
            return service_error_result(
                exc,
                session_id=(data.get("session_id") if isinstance(data, Mapping) else None),
            )
        changed = before.selected_timetable != after.selected_timetable
        return SessionToolResult(
            success=True,
            message="선택한 시간표 후보를 세션에 저장했습니다.",
            session_id=after.session_id,
            changed=changed,
            changed_fields=(["selected_timetable", "selected_timetable_status"] if changed else []),
            state_summary=SessionStateSummary.from_state(after),
            selected_timetable=(
                None
                if after.selected_timetable is None
                else after.selected_timetable.model_copy(deep=True)
            ),
            selected_timetable_status=(
                None
                if after.selected_timetable_status is None
                else after.selected_timetable_status.value
            ),
        )

    def get_selected_timetable(
        self,
        data: SessionIdInput | Mapping[str, object],
    ) -> SessionToolResult:
        """Return the currently selected timetable without mutating it."""

        try:
            request = SessionIdInput.model_validate(data)
            state = self._session_service.get_session(request.session_id)
            selected = self._session_service.get_selected_timetable(request.session_id)
        except ValidationError as exc:
            return validation_error_result(exc)
        except Exception as exc:
            return service_error_result(
                exc,
                session_id=(data.get("session_id") if isinstance(data, Mapping) else None),
            )
        return SessionToolResult(
            success=True,
            message="현재 선택된 시간표를 조회했습니다.",
            session_id=state.session_id,
            changed=False,
            state_summary=SessionStateSummary.from_state(state),
            selected_timetable=selected,
            selected_timetable_status=(
                None
                if state.selected_timetable_status is None
                else state.selected_timetable_status.value
            ),
        )

    def clear_selected_timetable(
        self,
        data: SessionIdInput | Mapping[str, object],
    ) -> SessionToolResult:
        """Clear selected timetable state without clearing preferences."""

        try:
            request = SessionIdInput.model_validate(data)
            before = self._session_service.get_session(request.session_id)
            after = self._session_service.clear_selected_timetable(request.session_id)
        except ValidationError as exc:
            return validation_error_result(exc)
        except Exception as exc:
            return service_error_result(
                exc,
                session_id=(data.get("session_id") if isinstance(data, Mapping) else None),
            )
        changed = before.selected_timetable is not None or before.selected_timetable_status is not None
        return SessionToolResult(
            success=True,
            message="선택된 시간표를 해제했습니다.",
            session_id=after.session_id,
            changed=changed,
            changed_fields=(["selected_timetable", "selected_timetable_status"] if changed else []),
            state_summary=SessionStateSummary.from_state(after),
            selected_timetable=None,
            selected_timetable_status=None,
        )

    def prepare_timetable_revision(
        self,
        data: TimetableRevisionRequest | Mapping[str, object],
    ) -> TimetableRevisionPreparationResult:
        """Prepare locked/replaceable/excluded sections before generation."""

        try:
            request = TimetableRevisionRequest.model_validate(data)
        except ValidationError as exc:
            error = exc.errors()[0]
            return TimetableRevisionPreparationResult(
                success=False,
                session_id=str(data.get("session_id", "")) if isinstance(data, Mapping) else "",
                needs_confirmation=False,
                errors=[str(error["msg"])],
                message=str(error["msg"]),
            )
        try:
            return self._revision_preparation_service.prepare(request)
        except Exception as exc:
            return TimetableRevisionPreparationResult(
                success=False,
                session_id=request.session_id,
                needs_confirmation=False,
                errors=[str(exc)],
                message=str(exc),
            )
