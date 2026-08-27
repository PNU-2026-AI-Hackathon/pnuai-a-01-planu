# PlaNU Departments JSON Schema

`shared/departments.json` is an array of department objects for frontend selection.

```json
{
  "college": null,
  "department": "컴퓨터공학과"
}
```

## Rules

- `department` is required.
- `college` may be `null` if the source Excel does not contain college information.
- Remove duplicates.
- Do not include phone numbers.
- Do not include HTML tags.
- Prefer departments from `수강대상학과`.
- If `수강대상학과` is unavailable and `개설학과` is used, state that in the generation report.
