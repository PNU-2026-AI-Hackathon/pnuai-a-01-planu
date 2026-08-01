"""Intent-level session tools intended for LLM agent registration."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from pydantic import BaseModel, ValidationError

from ..models import PlanuSessionState
from ..services.session_service import SessionService
from .errors import service_error_result, validation_error_result
from .schemas import (
    ResetSessionPreferencesInput,
    SessionIdInput,
    SessionStateSummary,
    SessionToolResult,
    UpdateSelectedMajorCoursesInput,
    UpdateSessionProfileInput,
    UpdateTimetablePreferencesInput,
)


class SessionAgentTools:
    """Small, intent-level session tool surface for future LLM agents."""

    def __init__(self, session_service: SessionService) -> None:
        self._session_service = session_service

    def get_session_summary(
        self,
        data: SessionIdInput | Mapping[str, object],
    ) -> SessionToolResult:
        """Use when the agent needs the current planning state for a session.

        This read-only tool returns a compact summary only. It does not refresh
        session TTL and must not be mixed with mutation requests.
        """

        try:
            request = SessionIdInput.model_validate(data)
            state = self._session_service.get_session(request.session_id)
        except ValidationError as exc:
            return validation_error_result(exc)
        except Exception as exc:
            return service_error_result(exc)
        return self._success(
            state,
            message="현재 세션 요약을 조회했습니다.",
            changed_fields=[],
        )

    def update_session_profile(
        self,
        data: UpdateSessionProfileInput | Mapping[str, object],
    ) -> SessionToolResult:
        """Use when the user provides department or catalog identifiers.

        Only supplied fields are updated. ``None`` means unchanged; fields are
        cleared only when named in ``clear_fields``. Empty strings are rejected.
        """

        return self._run(
            UpdateSessionProfileInput,
            data,
            lambda request: self._session_service.update_profile(
                request.session_id,
                request.to_service_update(),
            ),
            field_names=[
                "department",
                "major_catalog_id",
                "elective_catalog_id",
            ],
            message="세션 기본 정보를 갱신했습니다.",
        )

    def update_selected_major_courses(
        self,
        data: UpdateSelectedMajorCoursesInput | Mapping[str, object],
    ) -> SessionToolResult:
        """Use when the selected major course id list should change.

        ``course_ids`` must contain resolver-produced course_id values, not
        natural-language course names. ``replace`` overwrites, ``add`` appends
        missing ids, and ``remove`` deletes ids idempotently.
        """

        return self._run(
            UpdateSelectedMajorCoursesInput,
            data,
            lambda request: self._session_service.update_selected_major_courses(
                request.session_id,
                request.course_ids,
                mode=request.mode,
            ),
            field_names=["selected_major_course_ids"],
            message="선택 전공 과목 목록을 갱신했습니다.",
        )

    def update_timetable_preferences(
        self,
        data: UpdateTimetablePreferencesInput | Mapping[str, object],
    ) -> SessionToolResult:
        """Use for one user request that changes Hard constraints or Soft preferences.

        Patch list fields replace the whole list. ``None`` means unchanged;
        clearing is explicit through ``clear_fields``. Hard constraints have
        priority over Soft preferences, and final conflicts are validated by the
        service before a single repository save.
        """

        return self._run(
            UpdateTimetablePreferencesInput,
            data,
            lambda request: self._session_service.update_preferences(
                request.session_id,
                hard_patch=(
                    None if request.hard is None else request.hard.to_service_update()
                ),
                soft_patch=(
                    None if request.soft is None else request.soft.to_service_update()
                ),
            ),
            field_names=[
                "hard_constraints.required_free_days",
                "hard_constraints.earliest_start_time",
                "hard_constraints.latest_end_time",
                "hard_constraints.required_course_ids",
                "hard_constraints.excluded_course_ids",
                "soft_preferences.preferred_free_days",
                "soft_preferences.preferred_earliest_start_time",
                "soft_preferences.preferred_latest_end_time",
                "soft_preferences.preferred_course_ids",
                "soft_preferences.disliked_course_ids",
                "soft_preferences.compact_schedule",
            ],
            message="시간표 조건과 선호를 갱신했습니다.",
        )

    def reset_session_preferences(
        self,
        data: ResetSessionPreferencesInput | Mapping[str, object],
    ) -> SessionToolResult:
        """Use when the user explicitly asks to reset timetable preferences.

        ``hard`` clears only Hard constraints, ``soft`` clears only Soft
        preferences, and ``all`` clears both. Profile fields and selected major
        courses are never modified by this tool.
        """

        def command(request: ResetSessionPreferencesInput) -> PlanuSessionState:
            if request.target == "hard":
                return self._session_service.clear_hard_constraints(request.session_id)
            if request.target == "soft":
                return self._session_service.clear_soft_preferences(request.session_id)
            return self._session_service.clear_all_preferences(request.session_id)

        return self._run(
            ResetSessionPreferencesInput,
            data,
            command,
            field_names=[
                "hard_constraints.required_free_days",
                "hard_constraints.earliest_start_time",
                "hard_constraints.latest_end_time",
                "hard_constraints.required_course_ids",
                "hard_constraints.excluded_course_ids",
                "soft_preferences.preferred_free_days",
                "soft_preferences.preferred_earliest_start_time",
                "soft_preferences.preferred_latest_end_time",
                "soft_preferences.preferred_course_ids",
                "soft_preferences.disliked_course_ids",
                "soft_preferences.compact_schedule",
            ],
            message="시간표 조건과 선호를 초기화했습니다.",
        )

    def _run(
        self,
        input_model: type[BaseModel],
        data: BaseModel | Mapping[str, object],
        command: Callable[[object], PlanuSessionState],
        *,
        field_names: list[str],
        message: str,
    ) -> SessionToolResult:
        try:
            request = input_model.model_validate(data)
            session_id = str(getattr(request, "session_id"))
            before = self._session_service.get_session(session_id)
            after = command(request)
        except ValidationError as exc:
            return validation_error_result(exc)
        except Exception as exc:
            return service_error_result(exc, session_id=locals().get("session_id"))

        changed_fields = self._changed_fields(before, after, field_names)
        return self._success(after, message=message, changed_fields=changed_fields)

    @classmethod
    def _success(
        cls,
        state: PlanuSessionState,
        *,
        message: str,
        changed_fields: list[str],
    ) -> SessionToolResult:
        return SessionToolResult(
            success=True,
            message=message,
            session_id=state.session_id,
            changed=bool(changed_fields),
            changed_fields=changed_fields,
            state_summary=SessionStateSummary.from_state(state),
            error=None,
        )

    @classmethod
    def _changed_fields(
        cls,
        before: PlanuSessionState,
        after: PlanuSessionState,
        field_names: list[str],
    ) -> list[str]:
        return [
            field_name
            for field_name in field_names
            if cls._field_value(before, field_name) != cls._field_value(after, field_name)
        ]

    @staticmethod
    def _field_value(state: PlanuSessionState, field_name: str) -> object:
        value: object = state
        for part in field_name.split("."):
            value = getattr(value, part)
        return value
