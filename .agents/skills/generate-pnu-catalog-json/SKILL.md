---
name: generate-pnu-catalog-json
description: Use this skill when converting a PNU course catalog Excel file into PlaNU JSON data. Generate a full backend course catalog JSON and a minimal frontend department JSON from the same source data.
---

# generate-pnu-catalog-json

## Goal

Convert a PNU course catalog Excel file into two JSON files for the PlaNU MVP:

1. `backend/data/course_catalog.json`
   - Full normalized course catalog data for backend validation and recommendation logic.

2. `frontend/src/data/departments.json`
   - Minimal department data for frontend department selection UI.

If either target directory does not exist, create it.

The frontend and backend data must come from the same parsed Excel source. Do not manually create frontend department data that is inconsistent with the backend course catalog.

## Recommended project structure

```text
planu/
  backend/
    data/
      course_catalog.json

  frontend/
    src/
      data/
        departments.json

  .agents/
    skills/
      generate-pnu-catalog-json/
        SKILL.md
        references/
          course-catalog-schema.md
          departments-schema.md
```

## Input

The input is a PNU course catalog Excel file.

Typical important columns include:

- `100%사이버강좌`
- `원어강의`
- `학년`
- `교과목구분`
- `교과목명(미확정구분)`
- `교과목번호`
- `분반`
- `학점`
- `시간`
- `제한인원`
- `교수명`
- `시간/강의실`
- `수강대상학과`
- `개설학과`

Column names may vary slightly between catalog files. Match columns by meaning when the names are clearly equivalent, but do not guess if the meaning is ambiguous.

## Outputs

### 1. Backend output

Create:

```text
backend/data/course_catalog.json
```

This file contains the full normalized course data.

Each course object should preserve the original catalog values that are useful for later verification, especially time and room information.

Example course object:

```json
{
  "category": "GENERAL_REQUIRED",
  "courseType": "효원핵심교양",
  "grade": 2,
  "courseName": "공학작문및발표",
  "courseCode": "ZE1000043",
  "section": "046",
  "credits": 3,
  "hours": 4,
  "capacity": {
    "current": 44,
    "max": 45
  },
  "professor": "서형원",
  "targetDepartments": ["컴퓨터공학과"],
  "offeringDepartment": "국어국문학과",
  "rawTargetDepartment": "컴퓨터공학과",
  "rawTimeAndRoom": "수 15:00-19:00 401-828",
  "schedules": [
    {
      "day": "수",
      "startTime": "15:00",
      "endTime": "19:00",
      "room": "401-828"
    }
  ],
  "isCyber": false,
  "isEnglish": false
}
```

### 2. Frontend output

Create:

```text
frontend/src/data/departments.json
```

This file is only for frontend department selection UI. It should be much smaller than the full backend catalog.

Prefer this shape:

```json
[
  {
    "college": "공과대학",
    "departments": [
      "컴퓨터공학과",
      "전기공학과"
    ]
  }
]
```

If college information is not available, use:

```json
[
  {
    "college": null,
    "departments": [
      "컴퓨터공학과",
      "전기공학과"
    ]
  }
]
```

## Source of truth rule

The full backend catalog is the source of truth.

Generate the frontend `departments.json` from the parsed catalog data, not from a separate manually written list.

The frontend department list should be derived in this order of preference:

1. Departments in `수강대상학과`
2. If the catalog has a separate reliable department/college mapping, use that mapping
3. If only `개설학과` exists, preserve it in the backend catalog, but do not treat it as a student eligibility department unless the user explicitly requests that fallback

Important distinction:

- `수강대상학과` means departments that are allowed or targeted for the course.
- `개설학과` means the department that opened the course.

Do not assume that `개설학과` is the same as an eligible student department.

## Parsing rules

### Basic fields

Map common Excel columns as follows:

- `교과목구분` → `courseType`
- `학년` → `grade`
- `교과목명(미확정구분)` → `courseName`
- `교과목번호` → `courseCode`
- `분반` → `section`
- `학점` → `credits`
- `시간` → `hours`
- `제한인원` → `capacity`
- `교수명` → `professor`
- `시간/강의실` → `rawTimeAndRoom` and, if possible, `schedules`
- `수강대상학과` → `targetDepartments` and `rawTargetDepartment`
- `개설학과` → `offeringDepartment`

Preserve Korean text exactly.

### Section numbers

Always store `section` as a string.

Do not remove leading zeros.

Correct:

```json
"section": "046"
```

Incorrect:

```json
"section": 46
```

### Capacity

If `제한인원` has the format `current/max`, convert it to:

```json
"capacity": {
  "current": 44,
  "max": 45
}
```

If it cannot be parsed safely, preserve the original value as `rawCapacity` and set `capacity` to `null`.

### Time and room

Always preserve the original `시간/강의실` value in `rawTimeAndRoom`.

Parse it into `schedules` only when the format is clear.

Example:

```text
수 15:00-19:00 401-828
```

Output:

```json
"schedules": [
  {
    "day": "수",
    "startTime": "15:00",
    "endTime": "19:00",
    "room": "401-828"
  }
]
```

Some rows may contain multiple schedules separated by commas, newlines, or `<br/>`.

Example:

```text
월 16:30(100) 107-8403,<br/> 수 16:30(100) 107-8403
```

Output:

```json
"schedules": [
  {
    "day": "월",
    "startTime": "16:30",
    "durationMinutes": 100,
    "room": "107-8403"
  },
  {
    "day": "수",
    "startTime": "16:30",
    "durationMinutes": 100,
    "room": "107-8403"
  }
]
```

If exact time parsing is difficult, do not guess. Keep `rawTimeAndRoom` and set `schedules` to an empty array.

### Cyber and English flags

- If `100%사이버강좌` has a meaningful non-empty value, set `isCyber` to `true`; otherwise `false`.
- If `원어강의` has a meaningful non-empty value, set `isEnglish` to `true`; otherwise `false`.

### Department parsing

For `수강대상학과`:

- Split multiple departments only when separators are clear.
- Preserve original text in `rawTargetDepartment`.
- Store parsed departments in `targetDepartments`.
- Do not invent departments that are not present.

If `수강대상학과` is empty:

- Use `targetDepartments: []`.
- Preserve the empty or missing value in `rawTargetDepartment` if helpful.
- Do not copy `개설학과` into `targetDepartments` unless explicitly requested.

For `departments.json`:

- Prefer departments extracted from `targetDepartments`.
- Remove duplicates.
- Sort departments in a stable and readable order, preferably Korean alphabetical order if practical.
- If college grouping is unavailable, use `college: null`.

## Validation rules

Before finishing, check that:

- `backend/data/course_catalog.json` exists.
- `frontend/src/data/departments.json` exists.
- Both files are valid UTF-8 JSON.
- `section` values are strings.
- Leading zeros in section values are preserved.
- `rawTimeAndRoom` is preserved for every course when available.
- `departments.json` contains only frontend selection data, not the full course catalog.
- Department eligibility is not inferred from `개설학과` unless explicitly requested.

## Reporting rules

After generating the files, report:

- Number of courses written to `backend/data/course_catalog.json`
- Number of departments written to `frontend/src/data/departments.json`
- Rows skipped and why
- Rows where time parsing failed
- Rows where capacity parsing failed
- Whether `departments.json` was derived from `수강대상학과`, a mapping file, or a fallback

Do not silently discard ambiguous data. Preserve raw values and report uncertainty.
