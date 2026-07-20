"""Session orchestration for timetable candidate generation."""

from __future__ import annotations

from ..core.errors import AppError
from ..models.course_load import CourseLoadTarget
from ..models.preference import PreferenceRules
from ..models.timetable import TimetableGenerationResult
from .session_store import SessionStage, SessionStore, session_store
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
    ) -> None:
        self.store = store
        self.validator = validator or TimetableValidator()
        self.generator = generator or TimetableGenerator(validator=self.validator)

    def generate_for_session(
        self,
        *,
        session_id: str,
        course_load_target: CourseLoadTarget | None = None,
        hard_conditions: PreferenceRules | None = None,
        max_candidates: int | None = None,
    ) -> TimetableGenerationResult:
        data = self.store.get(session_id)
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

        target = course_load_target or CourseLoadTarget()
        result = self.generator.generate_detailed(
            fixed_major_courses=data.fixed_courses,
            required_general_candidates=data.general_required_candidates,
            elective_general_candidates=data.general_elective_candidates,
            course_load_target=target,
            hard_conditions=hard_conditions,
            max_candidates=max_candidates,
        )
        self.store.update_timetable_generation(
            session_id,
            candidates=result.candidates,
            diagnostics=result.diagnostics,
            course_load_target=target,
            hard_conditions=hard_conditions,
            truncated=result.truncated,
        )
        return result

