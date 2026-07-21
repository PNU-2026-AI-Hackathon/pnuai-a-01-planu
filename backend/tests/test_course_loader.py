"""Tests for loading generated catalog JSON into schedulable courses."""

from __future__ import annotations

import json

import pytest

from backend.app.models.course import Category, Day
from backend.app.services.course_loader import CourseCatalogLoadError, load_courses, load_default_catalogs
from backend.app.services.department_service import load_departments


def test_load_courses_reads_generated_catalog_json(tmp_path) -> None:
    path = tmp_path / "course_catalog.json"
    path.write_text(json.dumps([
        {
            "category": "GENERAL_ELECTIVE",
            "area": 1,
            "courseName": "대학생활설계와비전",
            "courseCode": "HR1200112",
            "section": "001",
            "credits": 2,
            "professor": "박종호",
            "schedules": [
                {
                    "day": "수",
                    "startTime": "16:30",
                    "endTime": None,
                    "durationMinutes": 100,
                    "room": "501-311",
                }
            ],
        },
        {
            "category": "GENERAL_REQUIRED",
            "area": None,
            "courseName": "온라인강의",
            "courseCode": "ZE1000453",
            "section": "045",
            "credits": 3,
            "professor": "김교수",
            "schedules": [],
        },
    ], ensure_ascii=False), encoding="utf-8")

    courses = load_courses(path)

    assert len(courses) == 1
    assert courses[0].course_id == "HR1200112-001"
    assert courses[0].category is Category.GENERAL_ELECTIVE
    assert courses[0].class_times[0].day is Day.WED
    assert courses[0].class_times[0].end == "18:10"


def test_load_default_catalogs_groups_general_courses(tmp_path) -> None:
    path = tmp_path / "course_catalog.json"
    path.write_text(json.dumps([
        {
            "category": "GENERAL_REQUIRED",
            "area": None,
            "courseName": "고전읽기와토론",
            "courseCode": "ZE1000001",
            "section": "001",
            "credits": 2,
            "professor": "김교수",
            "schedules": [{"day": "월", "startTime": "09:00", "endTime": "10:00", "room": "401-101"}],
        },
        {
            "category": "GENERAL_ELECTIVE",
            "area": 2,
            "courseName": "과학기술과사회",
            "courseCode": "ZE2000001",
            "section": "002",
            "credits": 3,
            "professor": "이교수",
            "schedules": [{"day": "화", "startTime": "10:00", "endTime": "11:15", "room": "609-313"}],
        },
    ], ensure_ascii=False), encoding="utf-8")

    catalogs = load_default_catalogs(path)

    assert [course.course_id for course in catalogs["general_required"]] == ["ZE1000001-001"]
    assert [course.course_id for course in catalogs["general_elective"]] == ["ZE2000001-002"]


def test_load_courses_normalizes_category_aliases_before_filtering(tmp_path) -> None:
    path = tmp_path / "course_catalog.json"
    path.write_text(json.dumps([
        {
            "category": " 효원 핵심 교양 ",
            "area": None,
            "courseName": "고전읽기와토론",
            "courseCode": "ZE1000001",
            "section": "001",
            "credits": 2,
            "professor": "김교수",
            "schedules": [{"day": "월", "startTime": "09:00", "endTime": "10:00", "room": "401-101"}],
        },
        {
            "category": "교양 선택",
            "area": 2,
            "courseName": "과학기술과사회",
            "courseCode": "ZE2000001",
            "section": "002",
            "credits": 3,
            "professor": "이교수",
            "schedules": [{"day": "화", "startTime": "10:00", "endTime": "11:15", "room": "609-313"}],
        },
    ], ensure_ascii=False), encoding="utf-8")

    courses = load_courses(path, category=Category.GENERAL_REQUIRED)

    assert [course.course_id for course in courses] == ["ZE1000001-001"]
    assert courses[0].category is Category.GENERAL_REQUIRED


def test_load_courses_rejects_unknown_category(tmp_path) -> None:
    path = tmp_path / "course_catalog.json"
    path.write_text(json.dumps([
        {
            "category": "자유선택",
            "area": None,
            "courseName": "미분류",
            "courseCode": "ZE9999999",
            "section": "001",
            "credits": 2,
            "professor": "김교수",
            "schedules": [{"day": "월", "startTime": "09:00", "endTime": "10:00", "room": "401-101"}],
        }
    ], ensure_ascii=False), encoding="utf-8")

    with pytest.raises(CourseCatalogLoadError, match="unknown course category"):
        load_courses(path)


def test_load_courses_skips_unsupported_schedule_days(tmp_path) -> None:
    path = tmp_path / "course_catalog.json"
    path.write_text(json.dumps([
        {
            "category": "GENERAL_REQUIRED",
            "area": None,
            "courseName": "주말강의",
            "courseCode": "ZE3000001",
            "section": "001",
            "credits": 2,
            "professor": "김교수",
            "schedules": [{"day": "토", "startTime": "09:00", "endTime": "10:00", "room": "401-101"}],
        }
    ], ensure_ascii=False), encoding="utf-8")

    assert load_courses(path) == []


def test_load_departments_accepts_generated_grouped_json(tmp_path) -> None:
    path = tmp_path / "departments.json"
    path.write_text(json.dumps([
        {"college": None, "departments": ["컴퓨터공학과", "전기공학과"]},
        {"college": "공과대학", "departments": ["컴퓨터공학과"]},
    ], ensure_ascii=False), encoding="utf-8")

    assert load_departments(path) == ["전기공학과", "컴퓨터공학과"]
