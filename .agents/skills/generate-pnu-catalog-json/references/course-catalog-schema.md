# PlaNU Course Catalog JSON Schema

`shared/course_catalog.json` is an array of course section objects.

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
  "rawCapacity": "44/45",
  "professor": "서형원",
  "rawTimeAndRoom": "수 15:00-19:00 401-828",
  "schedules": [
    {
      "day": "수",
      "startTime": "15:00",
      "endTime": "19:00",
      "durationMinutes": null,
      "room": "401-828"
    }
  ],
  "targetDepartments": [],
  "offeringDepartment": "건축공학과",
  "rawTargetDepartments": "",
  "rawOfferingDepartment": "건축공학과<br/>(+82|051-510-1426)",
  "isCyber": false,
  "isEnglish": false,
  "notes": ""
}
```

## Required invariants

- `courseCode` must be a string.
- `section` must be a string and must preserve leading zeros.
- `rawTimeAndRoom` must always be preserved.
- `schedules` may be empty if parsing fails.
- `targetDepartments` must not be inferred from `offeringDepartment`.
- Missing unknown values should be represented as `null`, `""`, or `[]` consistently.
