---
name: llm-prompt-improvement
description: Evaluate PlaNU natural-language preference parsing with pytest, classify LLM prompt/schema/normalization failures, and improve only the LLM prompt or minimal parser code when justified. Use when asked to run PlaNU LLM evaluation, improve prompt accuracy, handle preference parser failures, or validate required/preferred/excluded/avoided course-name extraction and earliest-start/elective-area parsing.
---

# PlaNU LLM Prompt Improvement

## Purpose

Evaluate whether PlaNU correctly converts natural-language course preferences into structured `PreferenceRules`, classify failures, and improve prompts only when the evidence points to a prompt problem. Do not modify evaluation cases or expected values to make tests pass.

## Required Workflow

1. Inspect the current implementation before editing:
   - Natural-language parser entrypoint
   - Prompt definition and prompt assembly
   - Pydantic output model
   - Post-processing and normalization
   - Existing pytest tests and markers
   - Whether tests call a real LLM
2. Run the non-LLM regression suite first:

   ```bash
   python -m pytest -m "not llm_eval"
   ```

3. Run real LLM evaluation only when the user requested LLM evaluation or prompt improvement and external calls are approved:

   ```bash
   python -m pytest -m llm_eval
   ```

   If API keys, network access, or data-export approval are unavailable, do not change the prompt based on speculation. Report the execution blocker.

4. Classify every failure before editing.
5. Edit the prompt only for prompt-caused failures. For schema or normalization failures, make the smallest relevant code change instead.
6. Re-run the full relevant suites after changes:

   ```bash
   python -m pytest -m llm_eval
   python -m pytest -m "not llm_eval"
   ```

## Field Semantics

Use the project's actual field names. In this repository, `disliked_course_names` test expectations may map to `avoided_course_names` in the model.

- `required_course_names`: hard required concrete course names.
- `preferred_course_names`: positive soft preferences for concrete course names.
- `excluded_course_names`: hard excluded concrete course names.
- `avoided_course_names` or `disliked_course_names`: negative soft preferences for concrete course names.
- `preferred_elective_areas`: preferred general-education areas; this is a preference, not an exclusive filter unless the schema says otherwise.
- `earliest_start_time`: hard earliest allowed start time, such as `"10:00"`.

## Strength Rules

- Treat "반드시", "꼭 포함", "무조건 넣어", and "이 과목이 없는 시간표는 싫다" as required.
- Treat "가능하면 듣고 싶다", "우선적으로 넣어", "되도록 포함", and "꼭 필요한 것은 아니지만 듣고 싶다" as preferred, not required.
- Treat "절대 듣기 싫다", "무조건 제외", "포함하지 말아", and "이 과목이 있으면 안 된다" as excluded.
- Treat "가능하면 피하고 싶다", "다른 선택지가 있다면 빼고 싶다", "우선순위를 낮춰", and "별로 선호하지 않는다" as avoided/disliked, not excluded.
- Treat "4영역을 선호", "4영역을 우선 추천", and "가능하면 4영역에서 골라" as `preferred_elective_areas`.
- Treat "오전 10시 이후 수업", "10시보다 이른 수업은 싫다", and "첫 수업은 10시부터 가능하다" as `earliest_start_time: "10:00"` when the condition is hard.
- For same-input corrections, prefer the later explicit correction: "필수까지는 아니고 가능하면" means preferred, not required.
- For negated strength, honor the negation: "절대 제외할 정도는 아니야" means avoided/disliked, not excluded.

## Failure Classes

- `PROMPT_CLASSIFICATION`: wrong hard/soft or positive/negative strength.
- `PROMPT_OMISSION`: explicit user condition omitted.
- `PROMPT_HALLUCINATION`: condition invented from text.
- `SCHEMA_VALIDATION`: Pydantic schema or validator failure.
- `PARSER_NORMALIZATION`: course-name, time, list, or alias normalization failure.
- `TEST_EXPECTATION`: expected value looks suspicious, but do not modify it without user approval.
- `API_OR_ENVIRONMENT`: timeout, auth, network, dependency, or approval problem.
- `NON_DETERMINISTIC`: same input produces unstable results.

## Editing Rules

- Do not delete cases, change expectations, add `skip`/`xfail`, or weaken assertions.
- Do not hardcode test IDs, exact test sentences, or unique course names into the prompt.
- Add general rules that apply to semantically similar expressions.
- Avoid large prompt rewrites; at most two prompt edits in one skill run.
- Do not duplicate conflicting rules.
- If a change causes regression and a better general rule is not obvious, revert the change and report it.

## Report Format

End with this information:

```text
평가 환경
- 모델:
- temperature:
- 평가 케이스 수:
- 실제 LLM 호출 여부:

변경 전
- 전체 성공:
- 전체 실패:
- 필드별 실패 수:

실패 원인
- PROMPT_CLASSIFICATION:
- PROMPT_OMISSION:
- PROMPT_HALLUCINATION:
- SCHEMA_VALIDATION:
- PARSER_NORMALIZATION:
- API_OR_ENVIRONMENT:
- NON_DETERMINISTIC:

수정 내용
- 수정 파일:
- 변경한 일반 규칙:
- 프롬프트 외 코드 변경 여부:

변경 후
- 전체 성공:
- 전체 실패:
- 기존 테스트 회귀:
- 남은 실패 사례:

판단
- 개선 여부:
- 추가로 사람이 확인할 trace ID:
- 추가 결정이 필요한 사항:
```
