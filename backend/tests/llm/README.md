# LLM Preference Evaluation

General tests:

```bash
pytest -m "not llm_eval"
```

Real LLM evaluation:

```bash
pytest -m llm_eval
```

The LLM evaluation uses `parse_preferences_with_trace`, which calls the configured OpenAI-backed parser with `temperature=0`. Set `OPENAI_API_KEY` before running `llm_eval`; `OPENAI_MODEL` defaults to the parser setting.

The regression cases should live in `cases/preference_cases.json`; the test also accepts the current legacy location, `preference_cases.json`. The JSON field `disliked_course_names` maps to the current backend model field `avoided_course_names`; the meaning is unchanged.
