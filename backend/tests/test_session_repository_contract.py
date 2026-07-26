"""Tests for the future agent session repository contract objects."""

from __future__ import annotations

from datetime import datetime, timezone

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


def test_planu_session_state_can_be_created() -> None:
    now = _aware_now()

    state = PlanuSessionState(
        session_id="session-1",
        department="컴퓨터공학부",
        major_catalog_id="major-catalog-1",
        elective_catalog_id="elective-catalog-1",
        selected_major_course_ids=["MAJ001-001"],
        created_at=now,
        updated_at=now,
        last_accessed_at=now,
        expires_at=now,
    )

    assert state.session_id == "session-1"
    assert state.selected_major_course_ids == ["MAJ001-001"]


def test_planu_session_state_rejects_empty_session_id() -> None:
    now = _aware_now()

    with pytest.raises(ValidationError, match="session_id"):
        PlanuSessionState(
            session_id=" ",
            created_at=now,
            updated_at=now,
            last_accessed_at=now,
            expires_at=now,
        )


def test_planu_session_state_rejects_naive_datetime() -> None:
    now = _aware_now()
    naive_now = datetime(2026, 7, 26, 12, 0)

    with pytest.raises(ValidationError, match="timezone"):
        PlanuSessionState(
            session_id="session-1",
            created_at=now,
            updated_at=naive_now,
            last_accessed_at=now,
            expires_at=now,
        )


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
