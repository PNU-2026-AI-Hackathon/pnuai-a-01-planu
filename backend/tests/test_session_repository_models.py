"""Tests for the future agent session state and repository errors."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from backend.app.models import PlanuSessionState
from backend.app.repositories import (
    SessionAlreadyExistsError,
    SessionNotFoundError,
    SessionRepositoryError,
)


def _aware_now() -> datetime:
    return datetime(2026, 7, 26, 12, 0, tzinfo=timezone.utc)


def _valid_state_kwargs() -> dict[str, object]:
    now = _aware_now()
    return {
        "session_id": "session-1",
        "department": "컴퓨터공학부",
        "major_catalog_id": "major-catalog-1",
        "elective_catalog_id": "elective-catalog-1",
        "selected_major_course_ids": ["MAJ001-001"],
        "created_at": now,
        "updated_at": now,
        "last_accessed_at": now,
        "expires_at": now + timedelta(minutes=30),
    }


def test_planu_session_state_can_be_created() -> None:
    state = PlanuSessionState(**_valid_state_kwargs())

    assert state.session_id == "session-1"
    assert state.selected_major_course_ids == ["MAJ001-001"]


def test_planu_session_state_rejects_empty_session_id() -> None:
    kwargs = _valid_state_kwargs()
    kwargs["session_id"] = " "

    with pytest.raises(ValidationError, match="session_id"):
        PlanuSessionState(**kwargs)


def test_planu_session_state_rejects_naive_datetime() -> None:
    kwargs = _valid_state_kwargs()
    kwargs["updated_at"] = datetime(2026, 7, 26, 12, 0)

    with pytest.raises(ValidationError, match="timezone"):
        PlanuSessionState(**kwargs)


def test_planu_session_state_rejects_updated_at_before_created_at() -> None:
    kwargs = _valid_state_kwargs()
    kwargs["updated_at"] = _aware_now() - timedelta(seconds=1)

    with pytest.raises(ValidationError, match="updated_at"):
        PlanuSessionState(**kwargs)


def test_planu_session_state_rejects_last_accessed_at_before_created_at() -> None:
    kwargs = _valid_state_kwargs()
    kwargs["last_accessed_at"] = _aware_now() - timedelta(seconds=1)

    with pytest.raises(ValidationError, match="last_accessed_at"):
        PlanuSessionState(**kwargs)


@pytest.mark.parametrize("delta", [timedelta(0), -timedelta(seconds=1)])
def test_planu_session_state_rejects_expires_at_not_after_last_accessed_at(
    delta: timedelta,
) -> None:
    kwargs = _valid_state_kwargs()
    kwargs["expires_at"] = _aware_now() + delta

    with pytest.raises(ValidationError, match="expires_at"):
        PlanuSessionState(**kwargs)


@pytest.mark.parametrize("invalid_course_id", ["", " "])
def test_planu_session_state_rejects_empty_selected_major_course_id(
    invalid_course_id: str,
) -> None:
    kwargs = _valid_state_kwargs()
    kwargs["selected_major_course_ids"] = ["MAJ001-001", invalid_course_id]

    with pytest.raises(ValidationError, match="selected_major_course_ids"):
        PlanuSessionState(**kwargs)


def test_planu_session_state_rejects_duplicate_selected_major_course_id() -> None:
    kwargs = _valid_state_kwargs()
    kwargs["selected_major_course_ids"] = ["MAJ001-001", "MAJ001-001"]

    with pytest.raises(ValidationError, match="duplicates"):
        PlanuSessionState(**kwargs)


@pytest.mark.parametrize(
    "error",
    [
        SessionRepositoryError("session-1"),
        SessionAlreadyExistsError("session-1"),
        SessionNotFoundError("session-1"),
    ],
)
def test_session_repository_errors_keep_session_id(
    error: SessionRepositoryError,
) -> None:
    assert error.session_id == "session-1"
