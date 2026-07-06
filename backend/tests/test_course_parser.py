"""Tests for internal general-course and restriction preprocessing."""

from openpyxl import Workbook
import pytest

from backend.app.models.course import Category, Day
from backend.app.services.course_parser import CatalogParseError, parse_catalog_workbook, parse_restrictions


def _save_workbook(path, rows):
    workbook = Workbook()
    sheet = workbook.active
    for row in rows:
        sheet.append(row)
    workbook.save(path)


def test_catalog_uses_first_row_as_header(tmp_path) -> None:
    path = tmp_path / "general.xlsx"
    _save_workbook(path, [
        ["교과목명", "교과목번호", "분반", "학점", "담당교수", "시간/강의실"],
        ["고전읽기", "ZE100", "1", 2, "김교수", "월 09:00(75) 609-313"],
    ])

    courses = parse_catalog_workbook(path, Category.GENERAL_REQUIRED)

    assert len(courses) == 1
    assert courses[0].course_id == "ZE100-001"
    assert courses[0].category is Category.GENERAL_REQUIRED
    assert courses[0].class_times[0].day is Day.MON


def test_catalog_falls_back_to_official_positions_for_broken_header(tmp_path) -> None:
    path = tmp_path / "broken.xlsx"
    header = [f"깨진열{i}" for i in range(17)]
    row = [None] * 17
    row[4], row[5], row[6], row[7] = "융합적사고", "ZE200", "7", 3
    row[10], row[11] = "이교수", "화 10:30-11:45 401-201"
    _save_workbook(path, [header, row])

    courses = parse_catalog_workbook(path, Category.GENERAL_REQUIRED)

    assert [course.course_id for course in courses] == ["ZE200-007"]


def test_catalog_skips_invalid_divisions_without_failing_file(tmp_path) -> None:
    path = tmp_path / "invalid_divisions.xlsx"
    header = ["교과목명", "교과목번호", "분반", "학점", "담당교수", "시간/강의실"]
    _save_workbook(path, [
        header,
        ["빈 분반", "ZE100", None, 2, "김교수", "월 09:00(75) 609-313"],
        ["0번 분반", "ZE101", "0", 2, "김교수", "화 09:00(75) 609-313"],
        ["문자 분반", "ZE102", "A1", 2, "김교수", "수 09:00(75) 609-313"],
        ["정상 분반", "ZE103", "2", 2, "김교수", "목 09:00(75) 609-313"],
    ])

    courses = parse_catalog_workbook(path, Category.GENERAL_REQUIRED)

    assert [course.course_id for course in courses] == ["ZE103-002"]


def test_internal_catalog_parser_rejects_major_category(tmp_path) -> None:
    with pytest.raises(CatalogParseError, match="교양필수/교양선택"):
        parse_catalog_workbook(tmp_path / "major.xlsx", Category.MAJOR_REQUIRED)


def test_restrictions_find_header_after_leading_rows(tmp_path) -> None:
    path = tmp_path / "restrictions.xlsx"
    header = ["대학", "개설학과", "교과목번호", "교과목명", "분반", "구분", "제한", "제한학과"]
    _save_workbook(path, [
        ["2026학년도 수강신청 제한 교과목 현황"],
        ["안내: 아래 표를 확인하세요"],
        header,
        ["공과대학", "컴퓨터공학과", "CS101", "프로그래밍", "001", "", "학과", "전자공학과"],
    ])

    records, departments = parse_restrictions(path)

    assert records[0]["교과목번호"] == "CS101"
    assert departments == ["전자공학과", "컴퓨터공학과"]
