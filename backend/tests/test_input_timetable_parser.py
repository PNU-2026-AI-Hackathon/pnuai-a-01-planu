"""Tests for user-owned major/fixed timetable parsing."""

from openpyxl import Workbook
import pytest

from backend.app.models.course import Category, Day
from backend.app.services.input_timetable_parser import (
    InputTimetableParseError,
    parse_input_timetable,
    parse_input_timetable_workbook,
)


def test_direct_fixed_courses_become_input_timetable() -> None:
    timetable = parse_input_timetable([{
        "course_code": "MA100",
        "course_name": "컴퓨터프로그래밍",
        "category": "전공기초",
        "credit": 3,
        "division": "1",
        "professor": "김교수",
        "schedule": "월 09:00(75) 609-313",
    }])

    assert timetable.total_credit == 3
    assert timetable.courses[0].category is Category.MAJOR_BASIC
    assert timetable.schedule_items[0].day is Day.MON


def test_direct_fixed_courses_normalize_general_category_aliases() -> None:
    timetable = parse_input_timetable([{
        "course_code": "ZE100",
        "course_name": "고전읽기",
        "category": " 효원 핵심 교양 ",
        "credit": 2,
        "division": "1",
        "professor": "김교수",
        "schedule": "월 09:00(75) 609-313",
    }])

    assert timetable.courses[0].category is Category.GENERAL_REQUIRED


def test_direct_fixed_courses_reject_unknown_category() -> None:
    with pytest.raises(InputTimetableParseError, match="지원하지 않는 고정 과목 구분"):
        parse_input_timetable([{
            "course_code": "ZE999",
            "course_name": "미분류",
            "category": "자유선택",
            "credit": 2,
            "division": "1",
            "professor": "김교수",
            "schedule": "월 09:00(75) 609-313",
        }])


def test_uploaded_fixed_timetable_allows_leading_title_rows(tmp_path) -> None:
    path = tmp_path / "major.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["2026학년도 전공 수강지도"])
    sheet.append(["교과구분", "교과목명", "교과목번호", "분반", "학점", "담당교수", "시간/강의실"])
    sheet.append(["전공필수", "자료구조", "MA200", "2", 3, "박교수", "화 13:30(75) 401-201"])
    sheet.append(["전공기초", "이산수학", "MA201", "1", 3, "이교수", "수 10:30-11:45 607-110"])
    workbook.save(path)

    timetable = parse_input_timetable_workbook(path)

    assert [course.category for course in timetable.courses] == [
        Category.MAJOR_REQUIRED,
        Category.MAJOR_BASIC,
    ]
    assert timetable.total_credit == 6
