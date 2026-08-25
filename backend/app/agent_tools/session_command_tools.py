"""Session mutation tools for future PlaNU agents."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from pydantic import BaseModel, ValidationError

from ..models import PlanuSessionState
from ..services.session_service import SessionService
from .errors import service_error_result, validation_error_result
from .schemas import (
    BoolPreferenceInput,
    CatalogInput,
    CourseIdInput,
    CourseIdsInput,
    DepartmentInput,
    DayInput,
    DaysInput,
    SessionIdInput,
    SessionStateSummary,
    SessionToolResult,
    TimeInput,
)


class SessionCommandTools:
    """Framework-independent adapters over mutating ``SessionService`` calls."""

    def __init__(self, session_service: SessionService) -> None:
        self._session_service = session_service

    def set_department(self, data: DepartmentInput | Mapping[str, object]) -> SessionToolResult:
        """Set the user's department after natural language has been normalized.

        The ``department`` field is the department text. Domain validation and state
        timestamp handling are delegated to ``SessionService``.
        """

        return self._run(
            DepartmentInput,
            data,
            lambda request: self._session_service.set_department(
                request.session_id,
                request.department,
            ),
            changed_selector=lambda state: state.department,
            message="학과를 세션에 저장했습니다.",
        )

    def register_major_catalog(self, data: CatalogInput | Mapping[str, object]) -> SessionToolResult:
        """Store the parsed major catalog id for the session.

        The input is a catalog identifier, not an uploaded file or raw parser
        content. Storage rules are delegated to ``SessionService``.
        """

        return self._run_catalog(
            data,
            self._session_service.register_major_catalog,
            lambda state: state.major_catalog_id,
            "전공 수강편람 식별자를 세션에 저장했습니다.",
        )

    def register_elective_catalog(
        self,
        data: CatalogInput | Mapping[str, object],
    ) -> SessionToolResult:
        """Store the optional parsed elective catalog id for the session.

        The input is a catalog identifier only. This tool does not parse files.
        """

        return self._run_catalog(
            data,
            self._session_service.register_elective_catalog,
            lambda state: state.elective_catalog_id,
            "교양 수강편람 식별자를 세션에 저장했습니다.",
        )

    def add_selected_major_course(self, data: CourseIdInput | Mapping[str, object]) -> SessionToolResult:
        """Add one resolved major course id to the selected course list.

        Use only after course names have been resolved to course ids. Duplicate
        handling is performed by ``SessionService``.
        """

        return self._run_course_id(
            data,
            self._session_service.add_selected_major_course,
            self._selected_courses,
            "선택 전공 과목을 추가했습니다.",
            selected_courses=True,
        )

    def remove_selected_major_course(self, data: CourseIdInput | Mapping[str, object]) -> SessionToolResult:
        """Remove one resolved major course id from the selected list.

        Missing ids are handled idempotently by ``SessionService``. Do not pass
        natural-language course names to this tool.
        """

        return self._run_course_id(
            data,
            self._session_service.remove_selected_major_course,
            self._selected_courses,
            "선택 전공 과목을 제거했습니다.",
            selected_courses=True,
        )

    def replace_selected_major_courses(
        self,
        data: CourseIdsInput | Mapping[str, object],
    ) -> SessionToolResult:
        """Replace selected major courses with resolved course ids.

        The ``course_ids`` list must contain concrete ids. De-duplication and
        validation are delegated to ``SessionService``.
        """

        return self._run(
            CourseIdsInput,
            data,
            lambda request: self._session_service.replace_selected_major_courses(
                request.session_id,
                request.course_ids,
            ),
            changed_selector=self._selected_courses,
            message="선택 전공 과목 목록을 교체했습니다.",
            include_courses=True,
        )

    def add_required_free_day(self, data: DayInput | Mapping[str, object]) -> SessionToolResult:
        """Add a weekday that must remain free as a Hard constraint.

        ``day`` is a resolved weekday enum value. Soft/Hard reconciliation is
        delegated to ``SessionService``.
        """

        return self._run_day(data, self._session_service.add_required_free_day, "Hard 공강일을 추가했습니다.")

    def remove_required_free_day(self, data: DayInput | Mapping[str, object]) -> SessionToolResult:
        """Remove a required free weekday from Hard constraints.

        Missing days are handled idempotently by ``SessionService``.
        """

        return self._run_day(data, self._session_service.remove_required_free_day, "Hard 공강일을 제거했습니다.")

    def replace_required_free_days(self, data: DaysInput | Mapping[str, object]) -> SessionToolResult:
        """Replace all required free weekdays in Hard constraints.

        ``days`` must be resolved weekday enum values; service logic handles
        de-duplication and Soft preference reconciliation.
        """

        return self._run_days(
            data,
            self._session_service.replace_required_free_days,
            "Hard 공강일 목록을 교체했습니다.",
        )

    def set_earliest_start_time(self, data: TimeInput | Mapping[str, object]) -> SessionToolResult:
        """Set the earliest allowed class start time as a Hard constraint.

        ``time`` must be HH:MM. Conflicts are validated by ``SessionService``.
        """

        return self._run_time(data, self._session_service.set_earliest_start_time, "Hard 시작 가능 시간을 설정했습니다.")

    def clear_earliest_start_time(self, data: SessionIdInput | Mapping[str, object]) -> SessionToolResult:
        """Clear the Hard earliest-start constraint for a session."""

        return self._run_session_id(data, self._session_service.clear_earliest_start_time, "Hard 시작 가능 시간을 초기화했습니다.")

    def set_latest_end_time(self, data: TimeInput | Mapping[str, object]) -> SessionToolResult:
        """Set the latest allowed class end time as a Hard constraint.

        ``time`` must be HH:MM. Conflicts are validated by ``SessionService``.
        """

        return self._run_time(data, self._session_service.set_latest_end_time, "Hard 종료 가능 시간을 설정했습니다.")

    def clear_latest_end_time(self, data: SessionIdInput | Mapping[str, object]) -> SessionToolResult:
        """Clear the Hard latest-end constraint for a session."""

        return self._run_session_id(data, self._session_service.clear_latest_end_time, "Hard 종료 가능 시간을 초기화했습니다.")

    def add_required_course(self, data: CourseIdInput | Mapping[str, object]) -> SessionToolResult:
        """Add a course id that must appear as a Hard constraint.

        Pass a resolved course id only. Required/excluded and Soft conflicts are
        reconciled by ``SessionService``.
        """

        return self._run_course_id(data, self._session_service.add_required_course, self._hard, "Hard 필수 과목을 추가했습니다.")

    def remove_required_course(self, data: CourseIdInput | Mapping[str, object]) -> SessionToolResult:
        """Remove a required course id from Hard constraints idempotently."""

        return self._run_course_id(data, self._session_service.remove_required_course, self._hard, "Hard 필수 과목을 제거했습니다.")

    def add_excluded_course(self, data: CourseIdInput | Mapping[str, object]) -> SessionToolResult:
        """Add a course id that must be excluded as a Hard constraint.

        Pass a resolved course id only. Conflicts are handled by
        ``SessionService``.
        """

        return self._run_course_id(data, self._session_service.add_excluded_course, self._hard, "Hard 제외 과목을 추가했습니다.")

    def remove_excluded_course(self, data: CourseIdInput | Mapping[str, object]) -> SessionToolResult:
        """Remove an excluded course id from Hard constraints idempotently."""

        return self._run_course_id(data, self._session_service.remove_excluded_course, self._hard, "Hard 제외 과목을 제거했습니다.")

    def clear_hard_constraints(self, data: SessionIdInput | Mapping[str, object]) -> SessionToolResult:
        """Clear all Hard constraints while leaving Soft preferences intact."""

        return self._run_session_id(data, self._session_service.clear_hard_constraints, "Hard 조건을 초기화했습니다.")

    def add_preferred_free_day(self, data: DayInput | Mapping[str, object]) -> SessionToolResult:
        """Add a weekday the user softly prefers to keep free.

        ``day`` is a resolved weekday. Hard conflicts are delegated to
        ``SessionService``.
        """

        return self._run_day(data, self._session_service.add_preferred_free_day, "Soft 선호 공강일을 추가했습니다.", hard=False)

    def remove_preferred_free_day(self, data: DayInput | Mapping[str, object]) -> SessionToolResult:
        """Remove a preferred free weekday idempotently from Soft preferences."""

        return self._run_day(data, self._session_service.remove_preferred_free_day, "Soft 선호 공강일을 제거했습니다.", hard=False)

    def replace_preferred_free_days(self, data: DaysInput | Mapping[str, object]) -> SessionToolResult:
        """Replace all preferred free weekdays in Soft preferences.

        Hard-required free days are handled by ``SessionService``.
        """

        return self._run_days(
            data,
            self._session_service.replace_preferred_free_days,
            "Soft 선호 공강일 목록을 교체했습니다.",
            hard=False,
        )

    def set_preferred_earliest_start_time(
        self,
        data: TimeInput | Mapping[str, object],
    ) -> SessionToolResult:
        """Set the user's preferred earliest class start time.

        ``time`` must be HH:MM. Hard boundary conflicts are validated by
        ``SessionService``.
        """

        return self._run_time(
            data,
            self._session_service.set_preferred_earliest_start_time,
            "Soft 선호 시작 시간을 설정했습니다.",
            hard=False,
        )

    def clear_preferred_earliest_start_time(
        self,
        data: SessionIdInput | Mapping[str, object],
    ) -> SessionToolResult:
        """Clear the Soft preferred earliest-start time."""

        return self._run_session_id(
            data,
            self._session_service.clear_preferred_earliest_start_time,
            "Soft 선호 시작 시간을 초기화했습니다.",
            hard=False,
        )

    def set_preferred_latest_end_time(
        self,
        data: TimeInput | Mapping[str, object],
    ) -> SessionToolResult:
        """Set the user's preferred latest class end time.

        ``time`` must be HH:MM. Hard boundary conflicts are validated by
        ``SessionService``.
        """

        return self._run_time(
            data,
            self._session_service.set_preferred_latest_end_time,
            "Soft 선호 종료 시간을 설정했습니다.",
            hard=False,
        )

    def clear_preferred_latest_end_time(
        self,
        data: SessionIdInput | Mapping[str, object],
    ) -> SessionToolResult:
        """Clear the Soft preferred latest-end time."""

        return self._run_session_id(
            data,
            self._session_service.clear_preferred_latest_end_time,
            "Soft 선호 종료 시간을 초기화했습니다.",
            hard=False,
        )

    def add_preferred_course(self, data: CourseIdInput | Mapping[str, object]) -> SessionToolResult:
        """Add a resolved course id as a positive Soft preference.

        Do not pass course names. Hard constraint conflicts are handled by
        ``SessionService``.
        """

        return self._run_course_id(data, self._session_service.add_preferred_course, self._soft, "Soft 선호 과목을 추가했습니다.", hard=False)

    def remove_preferred_course(self, data: CourseIdInput | Mapping[str, object]) -> SessionToolResult:
        """Remove a preferred course id from Soft preferences idempotently."""

        return self._run_course_id(data, self._session_service.remove_preferred_course, self._soft, "Soft 선호 과목을 제거했습니다.", hard=False)

    def add_disliked_course(self, data: CourseIdInput | Mapping[str, object]) -> SessionToolResult:
        """Add a resolved course id as a negative Soft preference.

        Do not pass course names. Hard-required conflicts are handled by
        ``SessionService``.
        """

        return self._run_course_id(data, self._session_service.add_disliked_course, self._soft, "Soft 비선호 과목을 추가했습니다.", hard=False)

    def remove_disliked_course(self, data: CourseIdInput | Mapping[str, object]) -> SessionToolResult:
        """Remove a disliked course id from Soft preferences idempotently."""

        return self._run_course_id(data, self._session_service.remove_disliked_course, self._soft, "Soft 비선호 과목을 제거했습니다.", hard=False)

    def set_compact_schedule_preference(
        self,
        data: BoolPreferenceInput | Mapping[str, object],
    ) -> SessionToolResult:
        """Set whether compact schedules should be softly preferred.

        ``value`` is a boolean ranking preference, not a hard filter.
        """

        return self._run(
            BoolPreferenceInput,
            data,
            lambda request: self._session_service.set_compact_schedule_preference(
                request.session_id,
                request.value,
            ),
            changed_selector=self._soft,
            message="Compact schedule Soft 선호를 설정했습니다.",
            include_soft=True,
        )

    def clear_compact_schedule_preference(
        self,
        data: SessionIdInput | Mapping[str, object],
    ) -> SessionToolResult:
        """Clear the compact schedule Soft preference."""

        return self._run_session_id(
            data,
            self._session_service.clear_compact_schedule_preference,
            "Compact schedule Soft 선호를 초기화했습니다.",
            hard=False,
        )

    def clear_soft_preferences(self, data: SessionIdInput | Mapping[str, object]) -> SessionToolResult:
        """Clear all Soft preferences while leaving Hard constraints intact."""

        return self._run_session_id(data, self._session_service.clear_soft_preferences, "Soft 선호를 초기화했습니다.", hard=False)

    def clear_all_preferences(self, data: SessionIdInput | Mapping[str, object]) -> SessionToolResult:
        """Clear both Hard constraints and Soft preferences for the session."""

        return self._run_session_id(
            data,
            self._session_service.clear_all_preferences,
            "Hard 조건과 Soft 선호를 모두 초기화했습니다.",
            hard=None,
        )

    def _run_catalog(
        self,
        data: CatalogInput | Mapping[str, object],
        command: Callable[[str, str], PlanuSessionState],
        changed_selector: Callable[[PlanuSessionState], object],
        message: str,
    ) -> SessionToolResult:
        return self._run(
            CatalogInput,
            data,
            lambda request: command(request.session_id, request.catalog_id),
            changed_selector=changed_selector,
            message=message,
        )

    def _run_course_id(
        self,
        data: CourseIdInput | Mapping[str, object],
        command: Callable[[str, str], PlanuSessionState],
        changed_selector: Callable[[PlanuSessionState], object],
        message: str,
        *,
        hard: bool = True,
        selected_courses: bool = False,
    ) -> SessionToolResult:
        return self._run(
            CourseIdInput,
            data,
            lambda request: command(request.session_id, request.course_id),
            changed_selector=changed_selector,
            message=message,
            include_hard=hard and not selected_courses,
            include_soft=not hard and not selected_courses,
            include_courses=selected_courses,
        )

    def _run_day(
        self,
        data: DayInput | Mapping[str, object],
        command: Callable[[str, object], PlanuSessionState],
        message: str,
        *,
        hard: bool = True,
    ) -> SessionToolResult:
        return self._run(
            DayInput,
            data,
            lambda request: command(request.session_id, request.day),
            changed_selector=self._hard if hard else self._soft,
            message=message,
            include_hard=hard,
            include_soft=not hard,
        )

    def _run_days(
        self,
        data: DaysInput | Mapping[str, object],
        command: Callable[[str, object], PlanuSessionState],
        message: str,
        *,
        hard: bool = True,
    ) -> SessionToolResult:
        return self._run(
            DaysInput,
            data,
            lambda request: command(request.session_id, request.days),
            changed_selector=self._hard if hard else self._soft,
            message=message,
            include_hard=hard,
            include_soft=not hard,
        )

    def _run_time(
        self,
        data: TimeInput | Mapping[str, object],
        command: Callable[[str, str], PlanuSessionState],
        message: str,
        *,
        hard: bool = True,
    ) -> SessionToolResult:
        return self._run(
            TimeInput,
            data,
            lambda request: command(request.session_id, request.time),
            changed_selector=self._hard if hard else self._soft,
            message=message,
            include_hard=hard,
            include_soft=not hard,
        )

    def _run_session_id(
        self,
        data: SessionIdInput | Mapping[str, object],
        command: Callable[[str], PlanuSessionState],
        message: str,
        *,
        hard: bool | None = True,
    ) -> SessionToolResult:
        return self._run(
            SessionIdInput,
            data,
            lambda request: command(request.session_id),
            changed_selector=self._preferences if hard is None else self._hard if hard else self._soft,
            message=message,
            include_hard=hard is not False,
            include_soft=hard is not True,
        )

    def _run(
        self,
        input_model: type[BaseModel],
        data: BaseModel | Mapping[str, object],
        command: Callable[[object], PlanuSessionState],
        *,
        changed_selector: Callable[[PlanuSessionState], object],
        message: str,
        include_hard: bool = False,
        include_soft: bool = False,
        include_courses: bool = False,
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

        changed = changed_selector(before) != changed_selector(after)
        return SessionToolResult(
            success=True,
            message=message,
            session_id=after.session_id,
            changed=changed,
            state_summary=SessionStateSummary.from_state(after),
            hard_constraints=after.hard_constraints if include_hard else None,
            soft_preferences=after.soft_preferences if include_soft else None,
            selected_major_course_ids=(
                list(after.selected_major_course_ids) if include_courses else None
            ),
            error=None,
        )

    @staticmethod
    def _selected_courses(state: PlanuSessionState) -> list[str]:
        return list(state.selected_major_course_ids)

    @staticmethod
    def _hard(state: PlanuSessionState) -> object:
        return state.hard_constraints

    @staticmethod
    def _soft(state: PlanuSessionState) -> object:
        return state.soft_preferences

    @staticmethod
    def _preferences(state: PlanuSessionState) -> tuple[object, object]:
        return state.hard_constraints, state.soft_preferences
