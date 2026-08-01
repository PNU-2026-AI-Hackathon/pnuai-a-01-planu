"""Error mapping helpers for PlaNU agent session tools."""

from __future__ import annotations

from pydantic import ValidationError

from ..services.exceptions import InvalidSessionStateValueError, SessionNotAvailableError
from .schemas import SessionToolError, SessionToolErrorCode, SessionToolResult


def error_result(
    *,
    message: str,
    code: SessionToolErrorCode,
    session_id: str | None = None,
    field: str | None = None,
    value: object | None = None,
) -> SessionToolResult:
    return SessionToolResult(
        success=False,
        message=message,
        session_id=session_id,
        changed=False,
        error=SessionToolError(
            code=code,
            message=message,
            field=field,
            value=None if value is None else str(value),
        ),
    )


def validation_error_result(exc: ValidationError) -> SessionToolResult:
    first_error = exc.errors()[0]
    field = ".".join(str(part) for part in first_error["loc"])
    return error_result(
        message=str(first_error["msg"]),
        code=SessionToolErrorCode.INVALID_VALUE,
        field=field,
    )


def service_error_result(exc: Exception, *, session_id: str | None = None) -> SessionToolResult:
    if isinstance(exc, SessionNotAvailableError):
        return error_result(
            message=str(exc),
            code=SessionToolErrorCode.SESSION_NOT_AVAILABLE,
            session_id=exc.session_id,
        )
    if isinstance(exc, InvalidSessionStateValueError):
        code = SessionToolErrorCode.INVALID_VALUE
        reason = exc.reason or ""
        if any(
            marker in reason
            for marker in (
                "hard-",
                "already covered",
                "already hard-required",
                "earlier than the hard",
                "later than the hard",
                "both required and excluded",
                "both preferred and disliked",
            )
        ):
            code = SessionToolErrorCode.CONFLICTING_CONSTRAINT
        return error_result(
            message=str(exc),
            code=code,
            session_id=session_id,
            field=exc.field_name,
            value=exc.value,
        )
    return error_result(
        message=str(exc),
        code=SessionToolErrorCode.INTERNAL_TOOL_ERROR,
        session_id=session_id,
    )
