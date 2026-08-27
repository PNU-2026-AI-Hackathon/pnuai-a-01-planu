"""Models for recommendation course-load targets.

The active timetable generation path uses ``CourseLoadTarget`` to carry optional
credit and elective-count goals from API requests into the session store and
timetable generator.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class _Model(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )


class CourseLoadTarget(_Model):
    """Optional user targets for timetable generation.

    ``target_total_credits`` is the desired total-credit upper bound used by
    the timetable generator when building and comparing candidates.

    ``additional_elective_count`` is the desired number of elective general
    courses to add after required general courses are accounted for.
    """

    target_total_credits: float | None = Field(default=None, gt=0)
    additional_elective_count: int | None = Field(default=None, ge=0)

    @classmethod
    def mvp_default_policy(cls) -> "CourseLoadTarget":
        """PlaNU MVP default: required generals only, no automatic electives.

        When both target fields are absent, the generator may still include
        required general courses but does not add elective general courses on
        the user's behalf.
        """

        return cls()
