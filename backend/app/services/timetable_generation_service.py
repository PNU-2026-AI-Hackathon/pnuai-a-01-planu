"""Session orchestration for timetable candidate generation."""

from __future__ import annotations

from ..core.errors import AppError
from ..models.course_load import CourseLoadTarget
from ..models.preference import (
    GeneralPreferenceParseResult,
    PreferenceRules,
)
from ..models.timetable import TimetableGenerationResult
from .general_preference_parser import GeneralPreferenceParser
from .session_store import (
    SessionNotFoundError,
    SessionStage,
    SessionStore,
    session_store,
)
from .timetable_generator import TimetableGenerator
from .timetable_validator import TimetableValidator


class TimetableGenerationService:
    """Build generated timetable candidates from a prepared session."""

    def __init__(
        self,
        *,
        store: SessionStore = session_store,
        generator: TimetableGenerator | None = None,
        validator: TimetableValidator | None = None,
        preference_parser: GeneralPreferenceParser | None = None,
    ) -> None:
        self.store = store
        self.validator = validator or TimetableValidator()
        self.generator = generator or TimetableGenerator(validator=self.validator)
        self.preference_parser = preference_parser or GeneralPreferenceParser()

    def generate_for_session(
        self,
        *,
        session_id: str,
        course_load_target: CourseLoadTarget | None = None,
        hard_conditions: PreferenceRules | None = None,
        preference_prompt: str = "",
        max_candidates: int | None = None,
    ) -> TimetableGenerationResult:
        session_id = session_id.strip()
        if not session_id:
            raise AppError("SESSION_NOT_FOUND", "세션 ID가 비어 있습니다.", status_code=400)
        try:
            data = self.store.get(session_id)
        except SessionNotFoundError as exc:
            raise AppError(
                "SESSION_NOT_FOUND",
                "세션을 찾을 수 없거나 만료되었습니다.",
                status_code=404,
            ) from exc
        if data.session_stage is not SessionStage.GENERAL_READY:
            raise AppError(
                "INVALID_SESSION_STAGE",
                "전공 확정과 교양 후보 준비가 완료된 세션에서만 시간표를 생성할 수 있습니다.",
                details={"session_stage": data.session_stage.value},
            )
        if not data.fixed_courses:
            raise AppError(
                "FIXED_MAJOR_NOT_FOUND",
                "확정된 전공 시간표가 없습니다.",
                hint="전공 과목을 먼저 확정해 주세요.",
            )

        fixed_major_credits = self.validator.calculate_total_credit(data.fixed_courses)
        if abs(fixed_major_credits - data.confirmed_major_credits) > 1e-9:
            raise AppError(
                "CONFIRMED_MAJOR_CREDIT_MISMATCH",
                "세션에 저장된 전공 학점과 실제 전공 과목 학점 합계가 다릅니다.",
                details={
                    "confirmed_major_credits": data.confirmed_major_credits,
                    "calculated_major_credits": fixed_major_credits,
                },
            )

        target = course_load_target or CourseLoadTarget.mvp_default_policy()
        parse_result = self._parse_prompt(preference_prompt)
        effective_hard_conditions = self._merge_rules(
            hard_conditions,
            parse_result.hard_conditions,
        )
        ranking_preferences = self._merge_rules(
            effective_hard_conditions,
            parse_result.soft_conditions,
        )
        result = self.generator.generate_detailed(
            fixed_major_courses=data.fixed_courses,
            required_general_candidates=data.general_required_candidates,
            elective_general_candidates=data.general_elective_candidates,
            course_load_target=target,
            hard_conditions=effective_hard_conditions,
            max_candidates=max_candidates,
        )
        result = result.model_copy(
            update={
                "hard_conditions": effective_hard_conditions,
                "soft_conditions": parse_result.soft_conditions,
                "unsupported_conditions": parse_result.unsupported_conditions,
                "warnings": parse_result.warnings,
            }
        )
        self.store.update_timetable_generation(
            session_id,
            candidates=result.candidates,
            diagnostics=result.diagnostics,
            course_load_target=target,
            hard_conditions=effective_hard_conditions,
            ranking_preferences=ranking_preferences,
            unsupported_conditions=parse_result.unsupported_conditions,
            warnings=parse_result.warnings,
            truncated=result.truncated,
        )
        return result

    def _parse_prompt(self, prompt: str) -> GeneralPreferenceParseResult:
        if not prompt.strip():
            return GeneralPreferenceParseResult()
        return self.preference_parser.parse(prompt)

    @staticmethod
    def _merge_rules(
        base: PreferenceRules | None,
        addition: PreferenceRules | None,
    ) -> PreferenceRules:
        merged = (base or PreferenceRules()).model_dump(mode="json")
        extra = addition or PreferenceRules()
        extra_dump = extra.model_dump(mode="json")
        for field_name, value in extra_dump.items():
            if isinstance(value, list):
                merged[field_name] = list(dict.fromkeys([*merged.get(field_name, []), *value]))
                continue
            if isinstance(value, bool):
                merged[field_name] = bool(merged.get(field_name)) or value
                continue
            if merged.get(field_name) in (None, "") and value not in (None, ""):
                merged[field_name] = value
        return PreferenceRules.model_validate(merged)
