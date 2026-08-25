"""Session orchestration for timetable candidate generation."""

from __future__ import annotations

from ..core.errors import AppError
from ..models.course_load import CourseLoadTarget
from ..models.preference import (
    GeneralPreferenceParseResult,
    PreferenceRules,
)
from ..models.timetable import TimetableGenerationResult
from ..models.timetable_generation import (
    GeneratedTimetableCandidate,
    TimetableValidationResult,
)
from ..repositories.recent_timetable_candidate_repository import RecentTimetableCandidateRepository
from .general_preference_parser import GeneralPreferenceParser
from .session_store import (
    SessionNotFoundError,
    SessionStage,
    SessionStore,
    session_store,
)
from .session_preference_adapter import hard_constraints_to_rules, soft_preferences_to_rules
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
        recent_candidate_repository: RecentTimetableCandidateRepository | None = None,
    ) -> None:
        self.store = store
        self.validator = validator or TimetableValidator()
        self.generator = generator or TimetableGenerator(validator=self.validator)
        self.preference_parser = preference_parser or GeneralPreferenceParser()
        self.recent_candidate_repository = recent_candidate_repository

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
        if data.session_stage not in {
            SessionStage.GENERAL_READY,
            SessionStage.CANDIDATES_GENERATED,
            SessionStage.RANKING_COMPLETED,
        }:
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
        session_hard_conditions = hard_constraints_to_rules(data.hard_constraints)
        session_soft_conditions = soft_preferences_to_rules(data.soft_preferences)
        effective_hard_conditions = self._merge_rules(
            session_hard_conditions,
            hard_conditions,
        )
        effective_hard_conditions = self._merge_rules(
            effective_hard_conditions,
            parse_result.hard_conditions,
        )
        effective_soft_conditions = self._merge_rules(
            session_soft_conditions,
            parse_result.soft_conditions,
        )
        # Combined rules used by the ranker for both hard filtering and soft scoring.
        ranking_preferences = self._merge_rules(
            effective_hard_conditions,
            effective_soft_conditions,
        )
        result = self.generator.generate_detailed(
            fixed_major_courses=data.fixed_courses,
            required_general_candidates=data.general_required_candidates,
            elective_general_candidates=[
                course for course in data.general_elective_candidates
                if course.area not in set(data.hard_constraints.excluded_elective_areas)
            ],
            course_load_target=target,
            hard_conditions=effective_hard_conditions,
            min_credit=data.hard_constraints.min_credit,
            min_credit_inclusive=data.hard_constraints.min_credit_inclusive,
            max_credit=data.hard_constraints.max_credit,
            max_credit_inclusive=data.hard_constraints.max_credit_inclusive,
            max_candidates=max_candidates,
        )
        result = result.model_copy(
            update={
                "hard_conditions": effective_hard_conditions,
                "soft_conditions": effective_soft_conditions,
                "unsupported_conditions": parse_result.unsupported_conditions,
                "warnings": parse_result.warnings,
            }
        )
        recent_candidates = _recent_candidates_from_legacy_result(
            session_id=session_id,
            generation_revision=data.generation_revision,
            result=result,
            fixed_major_course_ids=[course.course_id for course in data.fixed_courses],
        )
        if self.recent_candidate_repository is not None:
            if recent_candidates:
                self.recent_candidate_repository.save_candidates(session_id, recent_candidates)
            else:
                self.recent_candidate_repository.clear_candidates(session_id)

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
            is_explicit = field_name in extra.model_fields_set
            if isinstance(value, list):
                merged[field_name] = list(dict.fromkeys([*merged.get(field_name, []), *value]))
                continue
            if isinstance(value, bool):
                if is_explicit:
                    merged[field_name] = value
                continue
            if value not in (None, "") and is_explicit:
                merged[field_name] = value
        return PreferenceRules.model_validate(merged)


def _recent_candidates_from_legacy_result(
    *,
    session_id: str,
    generation_revision: int | None,
    result: TimetableGenerationResult,
    fixed_major_course_ids: list[str],
) -> list[GeneratedTimetableCandidate]:
    fixed_set = set(fixed_major_course_ids)
    candidates: list[GeneratedTimetableCandidate] = []
    for index, candidate in enumerate(result.candidates, start=1):
        courses = list(candidate.timetable.courses)
        section_ids = [_course_section_identity(course) for course in courses]
        fixed_section_ids = [
            _course_section_identity(course)
            for course in courses
            if course.course_id in fixed_set
        ]
        added_section_ids = [
            _course_section_identity(course)
            for course in courses
            if course.course_id not in fixed_set
        ]
        candidates.append(
            GeneratedTimetableCandidate(
                candidate_id=GeneratedTimetableCandidate.build_id(section_ids),
                section_ids=section_ids,
                fixed_section_ids=fixed_section_ids,
                added_section_ids=added_section_ids,
                course_ids=[course.course_id.rsplit("-", 1)[0] for course in courses],
                total_credits=float(candidate.timetable.total_credit or 0),
                validation=TimetableValidationResult(
                    valid=True,
                    checked_section_ids=section_ids,
                ),
                generation_order=index,
                session_id=session_id,
                generation_revision=generation_revision,
            )
        )
    return candidates


def _course_section_identity(course: object) -> str:
    course_id = str(getattr(course, "course_id"))
    division = str(getattr(course, "division", "") or "")
    return f"{course_id}:{division}" if division else course_id


def legacy_candidate_id_for_courses(course_ids: list[str]) -> str:
    return GeneratedTimetableCandidate.build_id(course_ids)
