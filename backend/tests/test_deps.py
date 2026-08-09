"""Tests for FastAPI dependency wiring."""

from __future__ import annotations

from backend.app.deps import (
    clear_dependency_caches,
    get_session_state_toolset,
    get_timetable_scoring_tools,
)


def test_session_state_toolset_dependency_registers_scoring_tools() -> None:
    clear_dependency_caches()
    try:
        toolset = get_session_state_toolset()
        specs = {spec.name for spec in toolset.specs()}

        assert "score_timetable_candidate" in specs
        assert "rank_timetable_candidates" in specs
        assert toolset.has_tool("score_timetable_candidate") is True
        assert toolset.has_tool("rank_timetable_candidates") is True
    finally:
        clear_dependency_caches()


def test_clear_dependency_caches_resets_timetable_scoring_tools_provider() -> None:
    clear_dependency_caches()
    try:
        first = get_timetable_scoring_tools()
        clear_dependency_caches()
        second = get_timetable_scoring_tools()

        assert second is not first
    finally:
        clear_dependency_caches()