"""Session-scoped cache for candidates produced by timetable generation tools."""

from __future__ import annotations

from threading import RLock

from ..models.timetable_generation import GeneratedTimetableCandidate


class TimetableCandidateNotFoundError(LookupError):
    def __init__(self, session_id: str, candidate_id: str) -> None:
        self.session_id = session_id
        self.candidate_id = candidate_id
        super().__init__(f"generated timetable candidate not found: {candidate_id}")


class RecentTimetableCandidateRepository:
    """Stores only the latest generated candidates for each session."""

    def __init__(self) -> None:
        self._candidates_by_session: dict[str, dict[str, GeneratedTimetableCandidate]] = {}
        self._lock = RLock()

    def save_candidates(
        self,
        session_id: str,
        candidates: list[GeneratedTimetableCandidate],
    ) -> None:
        with self._lock:
            self._candidates_by_session[session_id] = {
                candidate.candidate_id: candidate.model_copy(deep=True)
                for candidate in candidates
            }

    def clear_candidates(self, session_id: str) -> None:
        with self._lock:
            self._candidates_by_session.pop(session_id, None)

    def get_candidate(
        self,
        session_id: str,
        candidate_id: str,
    ) -> GeneratedTimetableCandidate:
        with self._lock:
            candidate = self._candidates_by_session.get(session_id, {}).get(candidate_id)
            if candidate is None:
                raise TimetableCandidateNotFoundError(session_id, candidate_id)
            return candidate.model_copy(deep=True)
