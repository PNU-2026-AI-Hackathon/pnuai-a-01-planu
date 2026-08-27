"""Read-only session state tools for future PlaNU agents."""

from __future__ import annotations

from collections.abc import Mapping

from pydantic import ValidationError

from ..models import PlanuSessionState
from ..services.session_service import SessionService
from .errors import service_error_result, validation_error_result
from .schemas import SessionIdInput, SessionStateSummary, SessionToolResult


class SessionQueryTools:
    """Framework-independent adapters over read-only ``SessionService`` calls."""

    def __init__(self, session_service: SessionService) -> None:
        self._session_service = session_service

    def get_session_summary(self, data: SessionIdInput | Mapping[str, object]) -> SessionToolResult:
        """Return a compact session summary for planning.

        Use after an agent has a concrete session_id. This tool does not extend
        session time, does not return whole course/catalog payloads, and must not
        receive raw natural-language text.
        """

        return self._query(data, "현재 세션 요약을 조회했습니다.")

    def get_hard_constraints(self, data: SessionIdInput | Mapping[str, object]) -> SessionToolResult:
        """Return only the current Hard constraints for a session.

        Use when deciding generation filters. Natural-language requests must be
        parsed before calling this tool; conflict handling belongs to the service
        during command tools, not here.
        """

        return self._query(data, "현재 Hard 조건을 조회했습니다.", include_hard=True)

    def get_soft_preferences(self, data: SessionIdInput | Mapping[str, object]) -> SessionToolResult:
        """Return only the current Soft preferences for a session.

        Use when deciding ranking preferences. Natural-language requests must be
        parsed before calling this tool; domain rules are enforced by the service.
        """

        return self._query(data, "현재 Soft 선호를 조회했습니다.", include_soft=True)

    def get_selected_major_courses(
        self,
        data: SessionIdInput | Mapping[str, object],
    ) -> SessionToolResult:
        """Return selected major course ids only.

        Use after course names have already been resolved elsewhere. This tool
        does not search catalogs or convert names into course ids.
        """

        return self._query(
            data,
            "현재 선택된 전공 과목 ID 목록을 조회했습니다.",
            include_courses=True,
        )

    def _query(
        self,
        data: SessionIdInput | Mapping[str, object],
        message: str,
        *,
        include_hard: bool = False,
        include_soft: bool = False,
        include_courses: bool = False,
    ) -> SessionToolResult:
        try:
            request = SessionIdInput.model_validate(data)
            state = self._session_service.get_session(request.session_id)
        except ValidationError as exc:
            return validation_error_result(exc)
        except Exception as exc:
            return service_error_result(exc)

        return self._success(
            state,
            message,
            include_hard=include_hard,
            include_soft=include_soft,
            include_courses=include_courses,
        )

    @staticmethod
    def _success(
        state: PlanuSessionState,
        message: str,
        *,
        include_hard: bool = False,
        include_soft: bool = False,
        include_courses: bool = False,
    ) -> SessionToolResult:
        return SessionToolResult(
            success=True,
            message=message,
            session_id=state.session_id,
            changed=False,
            state_summary=SessionStateSummary.from_state(state),
            hard_constraints=state.hard_constraints if include_hard else None,
            soft_preferences=state.soft_preferences if include_soft else None,
            selected_major_course_ids=(
                list(state.selected_major_course_ids) if include_courses else None
            ),
            error=None,
        )
