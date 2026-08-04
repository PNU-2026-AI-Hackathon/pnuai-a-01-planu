"""Framework-independent agent tool adapters for PlaNU."""

from .schemas import (
    BoolPreferenceInput,
    CatalogInput,
    CourseIdInput,
    CourseIdsInput,
    DepartmentInput,
    DayInput,
    DaysInput,
    HardConstraintsPatch,
    ResetSessionPreferencesInput,
    SessionIdInput,
    SessionStateSummary,
    SessionToolError,
    SessionToolErrorCode,
    SessionToolResult,
    SoftPreferencesPatch,
    TextValueInput,
    TimeInput,
    UpdateSelectedMajorCoursesInput,
    UpdateSessionProfileInput,
    UpdateTimetablePreferencesInput,
)
from .course_discovery_tools import (
    CourseDiscoveryTools,
    CourseSectionsInput,
    SearchCoursesByNameInput,
    SectionDetailsInput,
)
from .session_agent_tools import SessionAgentTools
from .session_command_tools import SessionCommandTools
from .session_query_tools import SessionQueryTools
from .timetable_generation_tools import TimetableGenerationTools
from .timetable_scoring_tools import (
    ScoreTimetableCandidateRequest,
    TimetableScoringTools,
)

__all__ = [
    "BoolPreferenceInput",
    "CatalogInput",
    "CourseIdInput",
    "CourseIdsInput",
    "CourseDiscoveryTools",
    "CourseSectionsInput",
    "DepartmentInput",
    "DayInput",
    "DaysInput",
    "HardConstraintsPatch",
    "ResetSessionPreferencesInput",
    "SearchCoursesByNameInput",
    "SectionDetailsInput",
    "SessionAgentTools",
    "SessionCommandTools",
    "SessionIdInput",
    "SessionQueryTools",
    "SessionStateSummary",
    "SessionToolError",
    "SessionToolErrorCode",
    "SessionToolResult",
    "SoftPreferencesPatch",
    "ScoreTimetableCandidateRequest",
    "TextValueInput",
    "TimeInput",
    "TimetableGenerationTools",
    "TimetableScoringTools",
    "UpdateSelectedMajorCoursesInput",
    "UpdateSessionProfileInput",
    "UpdateTimetablePreferencesInput",
]
