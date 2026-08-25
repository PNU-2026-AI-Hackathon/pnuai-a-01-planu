"""Supervisor and restricted domain agents for PlaNU chat routing."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from .session_state_agent import (
    ConfirmationRequest,
    SessionStateAgent,
    SessionStateAgentError,
    SessionStateAgentErrorCode,
    SessionStateAgentInput,
    SessionStateAgentResult,
)


class AgentDomain(str, Enum):
    MAJOR = "major"
    PREFERENCE = "preference"
    TIMETABLE = "timetable"


class RunnableAgent(Protocol):
    def run(self, data: SessionStateAgentInput | Mapping[str, object]) -> SessionStateAgentResult:
        ...


ALLOWED_FALLBACKS: dict[AgentDomain, tuple[AgentDomain, ...]] = {}

ResponsibilityCheck = Callable[[str], bool]


@dataclass(slots=True)
class DomainAgent:
    """Restricted wrapper around one SessionStateAgent domain worker."""

    domain: AgentDomain
    agent: SessionStateAgent
    can_handle: ResponsibilityCheck

    def run(self, data: SessionStateAgentInput | Mapping[str, object]) -> SessionStateAgentResult:
        request = SessionStateAgentInput.model_validate(data)
        if not self.can_handle(request.user_message):
            return not_my_responsibility_result(
                session_id=request.session_id,
                request_id=request.request_id,
                domain=self.domain,
            )
        return self.agent.run(request)

    @property
    def tool_names(self) -> list[str]:
        return [spec.name for spec in self.agent.tools.specs()]


class PlanuSupervisorAgent:
    """Routes user turns to the narrowest PlaNU domain agent."""

    def __init__(
        self,
        *,
        major_agent: RunnableAgent,
        preference_agent: RunnableAgent,
        timetable_agent: RunnableAgent,
    ) -> None:
        self._agents = {
            AgentDomain.MAJOR: major_agent,
            AgentDomain.PREFERENCE: preference_agent,
            AgentDomain.TIMETABLE: timetable_agent,
        }
        self.last_route: AgentDomain | None = None
        self.last_attempted_routes: list[AgentDomain] = []

    def run(self, data: SessionStateAgentInput | Mapping[str, object]) -> SessionStateAgentResult:
        request = SessionStateAgentInput.model_validate(data)
        route = classify_supervisor_route(request.user_message)
        attempted: list[AgentDomain] = []
        result = self._run_domain(route, request, attempted)
        if _is_not_my_responsibility(result):
            for fallback in self._fallback_routes(route, request.user_message):
                result = self._run_domain(fallback, request, attempted)
                if not _is_not_my_responsibility(result):
                    break
        self.last_route = attempted[-1] if attempted else None
        self.last_attempted_routes = attempted
        if _is_not_my_responsibility(result):
            return self._needs_routing_confirmation(request, attempted)
        return result

    def _run_domain(
        self,
        domain: AgentDomain,
        request: SessionStateAgentInput,
        attempted: list[AgentDomain],
    ) -> SessionStateAgentResult:
        attempted.append(domain)
        return self._agents[domain].run(request)

    @staticmethod
    def _fallback_routes(route: AgentDomain, text: str) -> list[AgentDomain]:
        return list(ALLOWED_FALLBACKS.get(route, ()))

    @staticmethod
    def _needs_routing_confirmation(
        request: SessionStateAgentInput,
        attempted: list[AgentDomain],
    ) -> SessionStateAgentResult:
        attempted_labels = ", ".join(domain.value for domain in attempted)
        return SessionStateAgentResult(
            success=False,
            session_id=request.session_id,
            request_id=request.request_id,
            message="요청을 어떤 작업으로 처리해야 할지 확인이 필요합니다.",
            needs_confirmation=True,
            confirmation_request=ConfirmationRequest(
                reason=f"하위 에이전트가 담당 범위가 아니라고 응답했습니다: {attempted_labels}",
                question="전공 과목, 조건 변경, 시간표 생성/수정 중 어떤 작업인지 알려주세요.",
                candidates=[],
            ),
            error=SessionStateAgentError(
                code=SessionStateAgentErrorCode.NOT_MY_RESPONSIBILITY,
                message="no routed agent accepted the request",
            ),
        )


def classify_supervisor_route(text: str) -> AgentDomain:
    normalized = _normalize(text)
    if _looks_like_preference_reset(normalized):
        return AgentDomain.PREFERENCE
    if _looks_like_timetable_revision(normalized):
        return AgentDomain.TIMETABLE
    if _looks_like_preference_crud(normalized):
        return AgentDomain.PREFERENCE
    if _looks_like_timetable_generation(normalized):
        return AgentDomain.TIMETABLE
    if _looks_like_major_request(normalized):
        return AgentDomain.MAJOR
    return AgentDomain.PREFERENCE


def major_responsibility(text: str) -> bool:
    normalized = _normalize(text)
    return _looks_like_major_request(normalized) and not _looks_like_preference_crud(normalized)


def preference_responsibility(text: str) -> bool:
    normalized = _normalize(text)
    return _looks_like_preference_reset(normalized) or _looks_like_preference_crud(normalized)


def timetable_responsibility(text: str) -> bool:
    normalized = _normalize(text)
    return (
        not _looks_like_preference_reset(normalized)
        and not _looks_like_preference_crud(normalized)
        and (_looks_like_timetable_revision(normalized) or _looks_like_timetable_generation(normalized))
    )


def not_my_responsibility_result(
    *,
    session_id: str,
    request_id: str | None,
    domain: AgentDomain,
) -> SessionStateAgentResult:
    return SessionStateAgentResult(
        success=False,
        session_id=session_id,
        request_id=request_id,
        message=f"{domain.value} agent cannot handle this request.",
        error=SessionStateAgentError(
            code=SessionStateAgentErrorCode.NOT_MY_RESPONSIBILITY,
            message="NOT_MY_RESPONSIBILITY",
        ),
    )


def _is_not_my_responsibility(result: SessionStateAgentResult) -> bool:
    return (
        result.error is not None
        and result.error.code is SessionStateAgentErrorCode.NOT_MY_RESPONSIBILITY
    )


def _looks_like_major_request(text: str) -> bool:
    return any(marker in text for marker in ("전공", "분반", "수강편람", "major"))


def _looks_like_preference_crud(text: str) -> bool:
    return any(
        marker in text
        for marker in (
            "금요일",
            "월요일",
            "화요일",
            "수요일",
            "목요일",
            "토요일",
            "일요일",
            "비워",
            "빼줘",
            "제외",
            "선호",
            "비선호",
            "필수",
            "10시",
            "9시",
            "5시",
            "6시",
            "아침",
            "오후",
            "이전",
            "이전에는",
            "모든 수업",
            "끝내",
            "마쳐",
            "종료",
            "공강",
            "외국어",
            "학점",
            "연강",
            "연속",
            "몰아듣기",
            "몰아서",
            "모아서",
        )
    )


def _looks_like_timetable_generation(text: str) -> bool:
    return any(marker in text for marker in ("시간표 만들어", "시간표 생성", "추천", "짜줘", "재생성"))


def _looks_like_preference_reset(text: str) -> bool:
    return (
        any(marker in text for marker in ("마음에 안", "별로", "전체적으로", "다시 정"))
        and any(marker in text for marker in ("조건", "처음", "다시"))
    )


def _looks_like_timetable_revision(text: str) -> bool:
    return (
        any(marker in text for marker in ("이 시간표", "선택한 시간표", "현재 시간표"))
        and any(marker in text for marker in ("바꿔", "대신", "수정", "교체", "하나만", "한 과목"))
    )


def _normalize(text: str) -> str:
    return text.strip().casefold()






