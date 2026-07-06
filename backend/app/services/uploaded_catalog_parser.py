"""Safe parsing entry points for user-uploaded catalog files."""

from __future__ import annotations

from pathlib import Path

from ..models.course import Category, Course
from .course_parser import CatalogParseError, parse_catalog_workbook
from .input_timetable_parser import InputTimetableParseError, parse_fixed_course_workbook

MAX_UPLOAD_SIZE = 5 * 1024 * 1024


class UploadedCatalogError(CatalogParseError):
    """A user-facing validation failure for an uploaded catalog."""


def validate_uploaded_catalog(path: str | Path) -> Path:
    source = Path(path)
    if source.suffix.lower() != ".xlsx":
        raise UploadedCatalogError("수강편람은 .xlsx 파일만 업로드할 수 있습니다.")
    if not source.is_file():
        raise UploadedCatalogError("업로드한 파일을 찾을 수 없습니다.")
    if source.stat().st_size > MAX_UPLOAD_SIZE:
        raise UploadedCatalogError("파일 크기는 5MB 이하여야 합니다.")
    # xlsx is a zip container. Checking the signature rejects renamed files
    # before openpyxl spends work on them.
    with source.open("rb") as stream:
        # 엑셀 파일은 시작 4바이트가 PK\x03\x04로 시작합니다. (PK는 zip 파일의 시그니처)
        if stream.read(4) != b"PK\x03\x04":
            raise UploadedCatalogError("유효한 .xlsx 파일이 아닙니다.")
    return source


def parse_major_catalog(path: str | Path) -> list[Course]:
    source = validate_uploaded_catalog(path)
    try:
        courses = parse_fixed_course_workbook(source)
    except InputTimetableParseError as exc:
        raise UploadedCatalogError(str(exc)) from exc
    if not courses:
        raise UploadedCatalogError("시간 정보가 있는 전공 과목을 찾지 못했습니다.")
    return courses


def parse_elective_catalog(path: str | Path, *, area: int | None = None) -> list[Course]:
    source = validate_uploaded_catalog(path)
    # An uploaded combined elective file may not carry a 1-7 area field. The
    # current Course contract requires it, so callers can provide the known
    if area is None:
        raise UploadedCatalogError("교양 영역을 선택해주세요.")
    if area < 1 or area > 7:
        raise UploadedCatalogError("교양 영역은 1~7 사이의 정수여야 합니다.")
    selected_area = area
    
    try:
        courses = parse_catalog_workbook(source, Category.GENERAL_ELECTIVE, area=selected_area)
    except CatalogParseError as exc:
        raise UploadedCatalogError(str(exc)) from exc
    if not courses:
        raise UploadedCatalogError("시간 정보가 있는 교양선택 과목을 찾지 못했습니다.")
    return courses


def parse_uploaded_catalog(
    major_catalog_path: str | Path,
    elective_catalog_path: str | Path | None = None,
) -> tuple[list[Course], list[Course]]:
    """Parse the required major file and optional elective file together."""

    major = parse_major_catalog(major_catalog_path)
    elective = parse_elective_catalog(elective_catalog_path) if elective_catalog_path else []
    return major, elective


class UploadedCatalogParser:
    """Small injectable facade for route/service wiring."""

    parse_major = staticmethod(parse_major_catalog)
    parse_elective = staticmethod(parse_elective_catalog)
    parse = staticmethod(parse_uploaded_catalog)
