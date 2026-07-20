"""Ranking template definitions and weight lookup."""

from __future__ import annotations

from dataclasses import dataclass, fields

from pydantic import BaseModel, ConfigDict, Field

from ..models.preference import PreferenceTemplate
from ..models.timetable import RankingTemplate


@dataclass(frozen=True)
class RankingWeights:
    """A complete evaluation profile for one timetable direction."""

    valid_candidate: float = 70
    preferred_free_day: float = 8
    preferred_free_day_missing: float = -5
    preferred_free_time_range: float = 3
    preferred_free_time_range_missing: float = -2
    preferred_course: float = 4
    preferred_course_missing: float = -1
    avoided_course: float = -4
    avoided_course_absent: float = 1
    preferred_elective_area: float = 3
    preferred_elective_area_missing: float = -1
    no_consecutive_classes: float = 5
    consecutive_class: float = -3
    compact_idle_short: float = 4
    compact_idle_medium: float = 2
    compact_idle_long: float = -2
    attendance_days_low: float = 6
    attendance_days_medium: float = 2
    attendance_days_high: float = -4
    late_start_11_or_later: float = 6
    late_start_10_or_later: float = 3
    early_start_before_9: float = -4


class RankingTemplateDefinition(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
        arbitrary_types_allowed=True,
    )

    template: RankingTemplate
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    weights: RankingWeights


TEMPLATE_WEIGHT_PROFILES: dict[RankingTemplate, RankingWeights] = {
    RankingTemplate.BALANCED: RankingWeights(),
    RankingTemplate.FREE_DAY_PRIORITY: RankingWeights(
        valid_candidate=70,
        preferred_free_day=14,
        preferred_free_day_missing=-11,
        preferred_free_time_range=8,
        preferred_free_time_range_missing=-7,
        preferred_course=2,
        preferred_course_missing=-0.5,
        avoided_course=-2,
        avoided_course_absent=0.5,
        preferred_elective_area=2,
        preferred_elective_area_missing=-0.5,
        no_consecutive_classes=3,
        consecutive_class=-2,
        compact_idle_short=5,
        compact_idle_medium=3,
        compact_idle_long=-3,
        attendance_days_low=8,
        attendance_days_medium=4,
        attendance_days_high=-6,
        late_start_11_or_later=2,
        late_start_10_or_later=1,
        early_start_before_9=-1,
    ),
    RankingTemplate.NO_MORNING_PRIORITY: RankingWeights(
        valid_candidate=70,
        preferred_free_day=5,
        preferred_free_day_missing=-3,
        preferred_free_time_range=3,
        preferred_free_time_range_missing=-2,
        preferred_course=2,
        preferred_course_missing=-0.5,
        avoided_course=-2,
        avoided_course_absent=0.5,
        preferred_elective_area=2,
        preferred_elective_area_missing=-0.5,
        no_consecutive_classes=4,
        consecutive_class=-3,
        compact_idle_short=4,
        compact_idle_medium=2,
        compact_idle_long=-3,
        attendance_days_low=5,
        attendance_days_medium=3,
        attendance_days_high=-4,
        late_start_11_or_later=14,
        late_start_10_or_later=8,
        early_start_before_9=-11,
    ),
    RankingTemplate.COMPACT_SCHEDULE: RankingWeights(
        valid_candidate=70,
        preferred_free_day=5,
        preferred_free_day_missing=-3,
        preferred_free_time_range=3,
        preferred_free_time_range_missing=-2,
        preferred_course=2,
        preferred_course_missing=-0.5,
        avoided_course=-2,
        avoided_course_absent=0.5,
        preferred_elective_area=2,
        preferred_elective_area_missing=-0.5,
        no_consecutive_classes=5,
        consecutive_class=-4,
        compact_idle_short=14,
        compact_idle_medium=8,
        compact_idle_long=-11,
        attendance_days_low=6,
        attendance_days_medium=4,
        attendance_days_high=-5,
        late_start_11_or_later=2,
        late_start_10_or_later=1,
        early_start_before_9=-1,
    ),
}


LEGACY_TEMPLATE_MAP: dict[PreferenceTemplate, RankingTemplate] = {
    PreferenceTemplate.REQUIRED_FREE_DAY: RankingTemplate.FREE_DAY_PRIORITY,
    PreferenceTemplate.PREFER_FREE_DAY: RankingTemplate.FREE_DAY_PRIORITY,
    PreferenceTemplate.MINIMIZE_ATTENDANCE_DAYS: RankingTemplate.FREE_DAY_PRIORITY,
    PreferenceTemplate.MINIMIZE_CONSECUTIVE_CLASSES: RankingTemplate.COMPACT_SCHEDULE,
    PreferenceTemplate.COMPACT_SCHEDULE: RankingTemplate.COMPACT_SCHEDULE,
}


LEGACY_TEMPLATE_WEIGHT_PROFILES: dict[PreferenceTemplate, RankingWeights] = {
    PreferenceTemplate.PREFER_FREE_DAY: RankingWeights(
        preferred_free_day=14,
        preferred_free_day_missing=-11,
        preferred_free_time_range=8,
        preferred_free_time_range_missing=-7,
        preferred_course=2,
        preferred_course_missing=-0.5,
        avoided_course=-2,
        avoided_course_absent=0.5,
        preferred_elective_area=2,
        preferred_elective_area_missing=-0.5,
        no_consecutive_classes=3,
        consecutive_class=-2,
        compact_idle_short=5,
        compact_idle_medium=3,
        compact_idle_long=-3,
        attendance_days_low=6,
        attendance_days_medium=3,
        attendance_days_high=-4,
        late_start_11_or_later=2,
        late_start_10_or_later=1,
        early_start_before_9=-1,
    ),
    PreferenceTemplate.MINIMIZE_ATTENDANCE_DAYS: RankingWeights(
        preferred_free_day=6,
        preferred_free_day_missing=-4,
        preferred_free_time_range=3,
        preferred_free_time_range_missing=-2,
        preferred_course=2,
        preferred_course_missing=-0.5,
        avoided_course=-2,
        avoided_course_absent=0.5,
        preferred_elective_area=2,
        preferred_elective_area_missing=-0.5,
        no_consecutive_classes=3,
        consecutive_class=-2,
        compact_idle_short=5,
        compact_idle_medium=3,
        compact_idle_long=-3,
        attendance_days_low=14,
        attendance_days_medium=7,
        attendance_days_high=-11,
        late_start_11_or_later=2,
        late_start_10_or_later=1,
        early_start_before_9=-1,
    ),
    PreferenceTemplate.MINIMIZE_CONSECUTIVE_CLASSES: RankingWeights(
        preferred_free_day=5,
        preferred_free_day_missing=-3,
        preferred_free_time_range=3,
        preferred_free_time_range_missing=-2,
        preferred_course=2,
        preferred_course_missing=-0.5,
        avoided_course=-2,
        avoided_course_absent=0.5,
        preferred_elective_area=2,
        preferred_elective_area_missing=-0.5,
        no_consecutive_classes=14,
        consecutive_class=-10,
        compact_idle_short=4,
        compact_idle_medium=2,
        compact_idle_long=-3,
        attendance_days_low=5,
        attendance_days_medium=3,
        attendance_days_high=-4,
        late_start_11_or_later=2,
        late_start_10_or_later=1,
        early_start_before_9=-1,
    ),
    PreferenceTemplate.COMPACT_SCHEDULE: RankingWeights(
        preferred_free_day=5,
        preferred_free_day_missing=-3,
        preferred_free_time_range=3,
        preferred_free_time_range_missing=-2,
        preferred_course=2,
        preferred_course_missing=-0.5,
        avoided_course=-2,
        avoided_course_absent=0.5,
        preferred_elective_area=2,
        preferred_elective_area_missing=-0.5,
        no_consecutive_classes=5,
        consecutive_class=-4,
        compact_idle_short=14,
        compact_idle_medium=8,
        compact_idle_long=-11,
        attendance_days_low=6,
        attendance_days_medium=4,
        attendance_days_high=-5,
        late_start_11_or_later=2,
        late_start_10_or_later=1,
        early_start_before_9=-1,
    ),
    PreferenceTemplate.REQUIRED_FREE_DAY: RankingWeights(
        preferred_free_day=12,
        preferred_free_day_missing=-9,
        preferred_free_time_range=7,
        preferred_free_time_range_missing=-6,
        preferred_course=2,
        preferred_course_missing=-0.5,
        avoided_course=-2,
        avoided_course_absent=0.5,
        preferred_elective_area=2,
        preferred_elective_area_missing=-0.5,
        no_consecutive_classes=4,
        consecutive_class=-3,
        compact_idle_short=5,
        compact_idle_medium=3,
        compact_idle_long=-3,
        attendance_days_low=7,
        attendance_days_medium=4,
        attendance_days_high=-5,
        late_start_11_or_later=2,
        late_start_10_or_later=1,
        early_start_before_9=-1,
    ),
}


class RankingTemplateService:
    """Translate template ids into definitions and reusable weight objects."""

    def __init__(
        self,
        definitions: dict[RankingTemplate, RankingTemplateDefinition] | None = None,
    ) -> None:
        self._definitions = definitions or _default_definitions()

    def list_templates(self) -> list[RankingTemplateDefinition]:
        return list(self._definitions.values())

    def get_definition(
        self,
        template: RankingTemplate | PreferenceTemplate | str | None,
    ) -> RankingTemplateDefinition:
        ranking_template = normalize_ranking_template(template)
        return self._definitions[ranking_template]

    def get_weights(
        self,
        template: RankingTemplate | PreferenceTemplate | str | None,
    ) -> RankingWeights:
        return self.get_definition(template).weights


def normalize_ranking_template(
    template: RankingTemplate | PreferenceTemplate | str | None,
) -> RankingTemplate:
    if template is None:
        return RankingTemplate.BALANCED
    if isinstance(template, RankingTemplate):
        return template
    if isinstance(template, PreferenceTemplate):
        return LEGACY_TEMPLATE_MAP[template]
    return RankingTemplate(template)


def weights_for_template(
    template: RankingTemplate | PreferenceTemplate | str | None,
) -> RankingWeights:
    return RankingTemplateService().get_weights(template)


def _default_definitions() -> dict[RankingTemplate, RankingTemplateDefinition]:
    definitions = {
        RankingTemplate.BALANCED: RankingTemplateDefinition(
            template=RankingTemplate.BALANCED,
            name="균형형",
            description="공강, 오전 수업, 등교 일수와 빈 시간을 균형 있게 평가합니다.",
            weights=TEMPLATE_WEIGHT_PROFILES[RankingTemplate.BALANCED],
        ),
        RankingTemplate.FREE_DAY_PRIORITY: RankingTemplateDefinition(
            template=RankingTemplate.FREE_DAY_PRIORITY,
            name="공강일 우선형",
            description="선호 공강일 만족과 등교 일수 감소를 더 크게 평가합니다.",
            weights=TEMPLATE_WEIGHT_PROFILES[RankingTemplate.FREE_DAY_PRIORITY],
        ),
        RankingTemplate.NO_MORNING_PRIORITY: RankingTemplateDefinition(
            template=RankingTemplate.NO_MORNING_PRIORITY,
            name="오전 회피형",
            description="첫 수업이 늦게 시작하는 시간표를 더 크게 평가합니다.",
            weights=TEMPLATE_WEIGHT_PROFILES[RankingTemplate.NO_MORNING_PRIORITY],
        ),
        RankingTemplate.COMPACT_SCHEDULE: RankingTemplateDefinition(
            template=RankingTemplate.COMPACT_SCHEDULE,
            name="공강 최소형",
            description="수업 사이 빈 시간이 짧고 연강이 적은 시간표를 더 크게 평가합니다.",
            weights=TEMPLATE_WEIGHT_PROFILES[RankingTemplate.COMPACT_SCHEDULE],
        ),
    }
    expected_fields = {field.name for field in fields(RankingWeights)}
    for definition in definitions.values():
        actual_fields = {field.name for field in fields(definition.weights)}
        if actual_fields != expected_fields:
            raise ValueError("ranking template weight profile is incomplete")
    return definitions
