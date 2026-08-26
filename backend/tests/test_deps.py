"""Tests for FastAPI dependency wiring."""

from __future__ import annotations

from types import SimpleNamespace

from backend.app.agents import SessionStateToolset
from backend.app.container import build_container
from backend.app.deps import (
    get_container,
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

def test_get_container_rewires_stale_preference_toolset_without_losing_store() -> None:
    stale = build_container()
    stale.preference_toolset = SessionStateToolset(
        {
            "get_session_summary": stale.session_agent_tools.get_session_summary,
            "update_timetable_preferences": stale.session_agent_tools.update_timetable_preferences,
            "reset_session_preferences": stale.session_agent_tools.reset_session_preferences,
        }
    )
    stale.preference_agent.agent.tools = stale.preference_toolset
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(container=stale)))

    rewired = get_container(request)
    specs = {spec.name for spec in rewired.preference_toolset.specs()}

    assert rewired is not stale
    assert rewired.session_store is stale.session_store
    assert "search_courses_by_name" in specs
    assert request.app.state.container is rewired
