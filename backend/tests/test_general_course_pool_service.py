"""Tests for general-course candidate pool preparation."""

from __future__ import annotations

import json
import asyncio

import pytest

from backend.app.core.errors import AppError
from backend.app.models import Category, ClassTime, Course, Day
from backend.app.services.general_course_pool_service import (
    CourseRestrictionPolicy,
    DepartmentRestrictionRule,
    GeneralCoursePoolService,
    GeneralCoursePreparationService,
)
from backend.app.services.course_restriction_loader import (
    CourseRestrictionLoadError,
    load_department_restriction_rules,
)
from backend.app.services.session_store import SessionStage, SessionStore


class CountingRestrictionPolicy(CourseRestrictionPolicy):
    def __init__(self, rules: list[DepartmentRestrictionRule] | None = None) -> None:
        super().__init__(rules=rules or [])
        self.evaluated_course_ids: list[str] = []

    def evaluate(self, course: Course, *, department: str):
        self.evaluated_course_ids.append(course.course_id)
        return super().evaluate(course, department=department)


def _course(
    course_id: str,
    name: str,
    category: Category | str,
    division: str,
    *,
    area: int | None = None,
    start: str = "09:00",
    end: str = "10:15",
    professor: str = "김교수",
) -> Course:
    return Course(
        course_id=course_id,
        course_name=name,
        category=category,
        area=area,
        credit=3,
        division=division,
        professor=professor,
        class_times=[
            ClassTime(
                day=Day.MON,
                start=start,
                end=end,
                classroom="제6공학관 6201",
                building_code="6201",
            )
        ],
    )


def _rule(
    course_code: str,
    division: str,
    *,
    allowed: set[str] | None = None,
    blocked: set[str] | None = None,
) -> DepartmentRestrictionRule:
    return DepartmentRestrictionRule(
        course_code=course_code,
        division=division,
        allowed_departments=frozenset(allowed or set()),
        blocked_departments=frozenset(blocked or set()),
    )


def _restriction_row(
    course_code: str,
    division: str,
    availability: str,
    department: str,
    *,
    restriction_type: str = "학과",
) -> dict[str, str]:
    return {
        "교과목번호": course_code,
        "분반": division,
        "제한구분": restriction_type,
        "수강여부": availability,
        "학과명": department,
    }


def test_build_pools_uses_normalized_general_required_aliases() -> None:
    hyo = _course("ZE100-001", "고전읽기와토론", "효원핵심교양", "001")
    required = _course("ZE101-001", "대학영어", "교양필수", "001")
    service = GeneralCoursePoolService()

    result = service.build_pools(
        department="컴퓨터공학과",
        general_required_courses=[hyo, required],
    )

    assert [course.course_id for course in result.pools.required_courses] == [
        "ZE100-001",
        "ZE101-001",
    ]
    assert result.pools.elective_courses == []


def test_build_pools_keeps_electives_separate_and_rejects_unsupported_category() -> None:
    required = _course("ZE100-001", "고전읽기와토론", Category.GENERAL_REQUIRED, "001")
    elective = _course("ZE200-001", "과학기술과사회", "교양선택", "001", area=2)
    major = _course("MA100-001", "자료구조", Category.MAJOR_REQUIRED, "001")

    result = GeneralCoursePoolService().build_pools(
        department="컴퓨터공학과",
        general_required_courses=[required, major],
        uploaded_elective_courses=[elective, major],
    )

    assert result.pools.required_courses == [required]
    assert result.pools.elective_courses == [elective]
    assert any(
        item.course_key == "MA100-001" and item.reason_code == "UNSUPPORTED_CATEGORY"
        for item in result.excluded_courses
    )


def test_department_restrictions_exclude_only_matching_restricted_courses() -> None:
    allowed_required = _course("ZE100-001", "고전읽기와토론", Category.GENERAL_REQUIRED, "001")
    blocked_required = _course("ZE101-001", "대학영어", Category.GENERAL_REQUIRED, "001")
    unrestricted_upload = _course("ZE300-001", "현대사회와윤리", Category.GENERAL_ELECTIVE, "001", area=3)
    blocked_upload = _course("ZE400-001", "창의적사고", Category.GENERAL_ELECTIVE, "001", area=4)
    policy = CourseRestrictionPolicy(
        rules=[
            _rule("ZE101", "001", blocked={"컴퓨터공학과"}),
            _rule("ZE400", "001", blocked={"컴퓨터공학과"}),
        ],
    )

    result = GeneralCoursePoolService(restriction_policy=policy).build_pools(
        department="컴퓨터공학과",
        general_required_courses=[allowed_required, blocked_required],
        uploaded_elective_courses=[unrestricted_upload, blocked_upload],
    )

    assert result.pools.required_courses == [allowed_required]
    assert result.pools.elective_courses == [unrestricted_upload]
    assert [item.reason_code for item in result.excluded_courses].count(
        "DEPARTMENT_NOT_ELIGIBLE"
    ) == 2


def test_upload_without_restriction_entry_is_not_excluded_by_restriction_data() -> None:
    required = _course("ZE100-001", "고전읽기와토론", Category.GENERAL_REQUIRED, "001")
    uploaded = _course("UP100-001", "업로드교양", Category.GENERAL_ELECTIVE, "001", area=1)
    policy = CourseRestrictionPolicy(
        rules=[_rule("OTHER", "001", blocked={"컴퓨터공학과"})],
    )

    result = GeneralCoursePoolService(restriction_policy=policy).build_pools(
        department="컴퓨터공학과",
        general_required_courses=[required],
        uploaded_elective_courses=[uploaded],
    )

    assert result.pools.elective_courses == [uploaded]
    assert result.excluded_courses == []


def test_restriction_rule_without_matching_course_section_allows_course() -> None:
    course = _course("ZE100-001", "고전읽기와토론", Category.GENERAL_REQUIRED, "001")
    policy = CourseRestrictionPolicy(rules=[_rule("ZE100", "002", blocked={"컴퓨터공학과"})])

    result = GeneralCoursePoolService(restriction_policy=policy).build_pools(
        department="컴퓨터공학과",
        general_required_courses=[course],
    )

    assert result.pools.required_courses == [course]


def test_blocked_department_is_excluded() -> None:
    course = _course("ZE100-001", "고전읽기와토론", Category.GENERAL_REQUIRED, "001")
    policy = CourseRestrictionPolicy(rules=[_rule("ZE100", "001", blocked={"컴퓨터공학과"})])

    result = GeneralCoursePoolService(restriction_policy=policy).build_pools(
        department="컴퓨터공학과",
        general_required_courses=[course],
    )

    assert result.pools.required_courses == []
    assert result.excluded_courses[0].reason_code == "DEPARTMENT_NOT_ELIGIBLE"


def test_other_blocked_department_does_not_exclude_course() -> None:
    course = _course("ZE100-001", "고전읽기와토론", Category.GENERAL_REQUIRED, "001")
    policy = CourseRestrictionPolicy(rules=[_rule("ZE100", "001", blocked={"전자공학과"})])

    result = GeneralCoursePoolService(restriction_policy=policy).build_pools(
        department="컴퓨터공학과",
        general_required_courses=[course],
    )

    assert result.pools.required_courses == [course]


def test_allowed_department_is_accepted() -> None:
    course = _course("ZE100-001", "고전읽기와토론", Category.GENERAL_REQUIRED, "001")
    policy = CourseRestrictionPolicy(rules=[_rule("ZE100", "001", allowed={"컴퓨터공학과"})])

    result = GeneralCoursePoolService(restriction_policy=policy).build_pools(
        department="컴퓨터공학과",
        general_required_courses=[course],
    )

    assert result.pools.required_courses == [course]


def test_department_missing_from_allowed_list_is_excluded() -> None:
    course = _course("ZE100-001", "고전읽기와토론", Category.GENERAL_REQUIRED, "001")
    policy = CourseRestrictionPolicy(rules=[_rule("ZE100", "001", allowed={"전자공학과"})])

    result = GeneralCoursePoolService(restriction_policy=policy).build_pools(
        department="컴퓨터공학과",
        general_required_courses=[course],
    )

    assert result.pools.required_courses == []
    assert result.excluded_courses[0].reason_code == "DEPARTMENT_NOT_ELIGIBLE"


def test_duplicate_restriction_rule_for_same_course_section_raises() -> None:
    with pytest.raises(ValueError, match="duplicate restriction rule: ZE100-001"):
        CourseRestrictionPolicy(
            rules=[
                _rule("ZE100", "001", allowed={"컴퓨터공학과"}),
                _rule("ZE100", "001", blocked={"전자공학과"}),
            ]
        )


def test_restriction_rules_for_different_divisions_are_allowed() -> None:
    policy = CourseRestrictionPolicy(
        rules=[
            _rule("ZE100", "001", blocked={"컴퓨터공학과"}),
            _rule("ZE100", "002", blocked={"컴퓨터공학과"}),
        ]
    )

    assert len(policy.rules_by_course_section) == 2


def test_loader_merges_multiple_department_rows_into_one_rule(tmp_path) -> None:
    path = tmp_path / "course_restrictions.json"
    path.write_text(
        json.dumps(
            [
                {"data": _restriction_row("ZE100", "001", "수강가능", "컴퓨터공학과")},
                {"data": _restriction_row("ZE100", "001", "수강가능", "전자공학과")},
                {"data": _restriction_row("ZE100", "001", "수강불가", "기계공학과")},
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    rules = load_department_restriction_rules(path)

    assert rules == [
        DepartmentRestrictionRule(
            course_code="ZE100",
            division="001",
            allowed_departments=frozenset({"컴퓨터공학과", "전자공학과"}),
            blocked_departments=frozenset({"기계공학과"}),
        )
    ]


def test_different_divisions_apply_separate_restriction_rules() -> None:
    first = _course("ZE100-001", "고전읽기와토론", Category.GENERAL_REQUIRED, "001")
    second = _course("ZE100-002", "고전읽기와토론", Category.GENERAL_REQUIRED, "002", start="10:30", end="11:45")
    policy = CourseRestrictionPolicy(rules=[_rule("ZE100", "001", blocked={"컴퓨터공학과"})])

    result = GeneralCoursePoolService(restriction_policy=policy).build_pools(
        department="컴퓨터공학과",
        general_required_courses=[first, second],
    )

    assert result.pools.required_courses == [second]
    assert result.excluded_courses[0].course_key == "ZE100-001"


def test_uploaded_elective_without_rule_is_evaluated_and_allowed() -> None:
    required = _course("ZE100-001", "고전읽기와토론", Category.GENERAL_REQUIRED, "001")
    uploaded = _course("UP100-001", "업로드교양", Category.GENERAL_ELECTIVE, "001", area=1)
    policy = CountingRestrictionPolicy()

    result = GeneralCoursePoolService(restriction_policy=policy).build_pools(
        department="컴퓨터공학과",
        general_required_courses=[required],
        uploaded_elective_courses=[uploaded],
    )

    assert result.pools.elective_courses == [uploaded]
    assert "UP100-001" in policy.evaluated_course_ids


def test_uploaded_elective_applies_restriction_rule_while_preserving_upload_info() -> None:
    required = _course("ZE100-001", "고전읽기와토론", Category.GENERAL_REQUIRED, "001")
    uploaded = _course(
        "ZE200-001",
        "제한교양",
        Category.GENERAL_ELECTIVE,
        "001",
        area=2,
        professor="업로드교수",
    )
    policy = CountingRestrictionPolicy([_rule("ZE200", "001", blocked={"컴퓨터공학과"})])

    result = GeneralCoursePoolService(restriction_policy=policy).build_pools(
        department="컴퓨터공학과",
        general_required_courses=[required],
        uploaded_elective_courses=[uploaded],
    )

    assert result.pools.elective_courses == []
    assert "ZE200-001" in policy.evaluated_course_ids
    assert result.excluded_courses[-1].reason_code == "DEPARTMENT_NOT_ELIGIBLE"


def test_catalog_elective_fallback_is_not_processed_as_required_candidate() -> None:
    required = _course("ZE100-001", "고전읽기와토론", Category.GENERAL_REQUIRED, "001")
    fallback = _course("ZE200-001", "과학기술과사회", Category.GENERAL_ELECTIVE, "001", area=2)

    result = GeneralCoursePoolService().build_pools(
        department="컴퓨터공학과",
        general_required_courses=[required],
        fallback_elective_courses=[fallback],
    )

    assert result.pools.required_courses == [required]
    assert result.pools.elective_courses == [fallback]
    assert not any(
        item.course_key == "ZE200-001" and item.reason_code == "UNSUPPORTED_CATEGORY"
        for item in result.excluded_courses
    )


def test_loader_rejects_invalid_restriction_row(tmp_path) -> None:
    path = tmp_path / "course_restrictions.json"
    path.write_text(
        json.dumps(
            [{"data": _restriction_row("ZE100", "001", "모름", "컴퓨터공학과")}],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    with pytest.raises(CourseRestrictionLoadError, match="수강여부"):
        load_department_restriction_rules(path)


def test_uploaded_elective_information_wins_and_conflicts_warn() -> None:
    required = _course("ZE100-001", "고전읽기와토론", Category.GENERAL_REQUIRED, "001")
    uploaded_elective = _course(
        "ZE200-001",
        "과학기술과사회",
        Category.GENERAL_ELECTIVE,
        "001",
        area=2,
        professor="업로드교수",
    )

    result = GeneralCoursePoolService().build_pools(
        department="컴퓨터공학과",
        general_required_courses=[required],
        uploaded_elective_courses=[uploaded_elective, uploaded_elective],
    )

    assert result.pools.elective_courses == [uploaded_elective]
    assert result.pools.elective_courses[0].professor == "업로드교수"
    assert any(item.reason_code == "DUPLICATE_COURSE" for item in result.excluded_courses)


def test_no_uploaded_elective_uses_explicit_fallback_only() -> None:
    required = _course("ZE100-001", "고전읽기와토론", Category.GENERAL_REQUIRED, "001")
    fallback = _course("FB100-001", "기본교양", Category.GENERAL_ELECTIVE, "001", area=1)

    with_fallback = GeneralCoursePoolService().build_pools(
        department="컴퓨터공학과",
        general_required_courses=[required],
        fallback_elective_courses=[fallback],
    )
    without_fallback = GeneralCoursePoolService().build_pools(
        department="컴퓨터공학과",
        general_required_courses=[required],
    )

    assert with_fallback.pools.elective_courses == [fallback]
    assert without_fallback.pools.elective_courses == []
    assert without_fallback.warnings


def test_pool_builder_does_not_filter_major_time_conflicts_or_course_load() -> None:
    required = _course("ZE100-001", "고전읽기와토론", Category.GENERAL_REQUIRED, "001")
    elective = _course("ZE200-001", "과학기술과사회", Category.GENERAL_ELECTIVE, "001", area=2)

    result = GeneralCoursePoolService().build_pools(
        department="컴퓨터공학과",
        general_required_courses=[required],
        uploaded_elective_courses=[elective],
    )

    assert result.pools.required_courses == [required]
    assert result.pools.elective_courses == [elective]


def test_preparation_requires_major_confirmed_session_and_saves_result() -> None:
    required = _course("ZE100-001", "고전읽기와토론", Category.GENERAL_REQUIRED, "001")
    elective = _course("ZE200-001", "과학기술과사회", Category.GENERAL_ELECTIVE, "001", area=2)
    store = SessionStore()
    session = store.create("컴퓨터공학과", elective_candidates=[elective])
    store.update(
        session.session_id,
        fixed_courses=[_course("MA100-001", "자료구조", Category.MAJOR_REQUIRED, "001")],
        session_stage=SessionStage.MAJOR_CONFIRMED,
    )

    response = asyncio.run(GeneralCoursePreparationService(
        store=store,
        general_required_courses=[required],
    ).prepare_for_session(session.session_id))

    saved = store.get(session.session_id)
    assert response.required_course_count == 1
    assert response.elective_course_count == 1
    assert saved.general_required_candidates == [required]
    assert saved.general_elective_candidates == [elective]
    assert saved.session_stage is SessionStage.GENERAL_READY


def test_preparation_is_idempotent_when_session_is_general_ready() -> None:
    required = _course("ZE100-001", "고전읽기와토론", Category.GENERAL_REQUIRED, "001")
    elective = _course("ZE200-001", "과학기술과사회", Category.GENERAL_ELECTIVE, "001", area=2)
    store = SessionStore()
    session = store.create("컴퓨터공학과", elective_candidates=[elective, elective])
    store.update(
        session.session_id,
        fixed_courses=[_course("MA100-001", "자료구조", Category.MAJOR_REQUIRED, "001")],
        session_stage=SessionStage.MAJOR_CONFIRMED,
    )

    first = asyncio.run(GeneralCoursePreparationService(
        store=store,
        general_required_courses=[required],
    ).prepare_for_session(session.session_id))
    second = asyncio.run(GeneralCoursePreparationService(
        store=store,
        general_required_courses=[],
    ).prepare_for_session(session.session_id))

    saved = store.get(session.session_id)
    assert second == first
    assert saved.general_required_candidates == [required]
    assert saved.general_elective_candidates == [elective]
    assert len(saved.general_pool_diagnostics) == 1
    assert saved.general_pool_diagnostics[0].reason_code == "DUPLICATE_COURSE"


def test_preparation_rejects_wrong_stage_without_partial_save() -> None:
    required = _course("ZE100-001", "고전읽기와토론", Category.GENERAL_REQUIRED, "001")
    store = SessionStore()
    session = store.create("컴퓨터공학과")

    with pytest.raises(AppError) as exc_info:
        asyncio.run(GeneralCoursePreparationService(
            store=store,
            general_required_courses=[required],
        ).prepare_for_session(session.session_id))

    saved = store.get(session.session_id)
    assert exc_info.value.code == "INVALID_SESSION_STAGE"
    assert saved.general_required_candidates == []
    assert saved.session_stage is SessionStage.CATALOG_PARSED
