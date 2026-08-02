# PlaNU 테스트 가이드

이 문서는 다른 팀원이 PlaNU를 테스트할 때 어떤 테스트를 어떤 순서로 실행하면 되는지 정리한 문서입니다.

## 1. 테스트 종류

PlaNU 테스트는 크게 세 종류로 나눕니다.

| 종류 | 목적 | 외부 LLM API 필요 |
| --- | --- | --- |
| 기본 백엔드 테스트 | 서비스, API, 에이전트 단위 테스트와 통합 테스트 검증 | 필요 없음 |
| 에이전트 탐색 테스트 | 단일 에이전트가 상태 변경 도구와 수강편람 탐색 도구를 올바른 순서로 호출하는지 검증 | 필요 없음 |
| live LLM 테스트 | 실제 LLM/proxy API로 자연어 파싱과 주요 HTTP 흐름 검증 | 필요 |

기본 테스트는 fake/scripted model을 사용하므로 API 키 없이 실행됩니다.

## 2. 사전 준비

프로젝트 루트에서 실행합니다.

```powershell
cd C:\hackerton
```

Python 버전은 프로젝트 기준 `3.14.0`입니다.

```powershell
python --version
```

테스트 러너 확인:

```powershell
python -m pytest --version
```

## 3. API 키 없이 실행하는 기본 테스트

가장 먼저 전체 백엔드 테스트를 실행합니다.

```powershell
python -m pytest backend\tests
```

정상 예:

```text
545 passed, 1 skipped, 52 deselected
```

`pytest.ini` 설정 때문에 `llm_eval`, `llm_live`, `live_llm` 마커가 붙은 실제 LLM 테스트는 기본 실행에서 자동 제외됩니다.

## 4. 이번 에이전트 확장 기능만 빠르게 확인

단일 에이전트의 상태 변경, 수강편람 탐색 도구 연결, 후보 결과 모델, 확인 요청 처리를 빠르게 확인하려면 아래 테스트를 실행합니다.

```powershell
python -m pytest backend\tests\test_session_state_agent.py
```

추가로 탐색 도구 자체까지 확인하려면:

```powershell
python -m pytest backend\tests\test_course_discovery.py backend\tests\test_agent_session_tools.py backend\tests\test_session_agent_tools.py
```

이번 작업에서 특히 확인해야 할 항목:

- `search_courses_by_name`가 명시적 과목 검색에 호출되는지
- `discover_courses`가 조건 기반 후보 탐색에 호출되는지
- 상태 변경과 탐색이 함께 있을 때 상태 변경 후 탐색하는지
- Hard 조건은 탐색 필터로 반영되고 Soft 선호는 Hard 필터로 바뀌지 않는지
- `AMBIGUOUS` 검색 결과에서 `needs_confirmation=True`가 반환되는지
- 모호한 후보를 첫 번째 항목으로 자동 선택하지 않는지
- 일반 후보 탐색에서 모든 후보의 분반 상세를 무조건 조회하지 않는지

## 5. 실제 LLM API로 테스트하기

현재 live LLM 테스트는 `.env`에서 `PROXY_TOKEN`을 읽습니다. 일반적인 `OPENAI_API_KEY` 이름이 아니라는 점에 주의합니다.

권장 위치는 `backend\.env`입니다. 루트 `.env`도 읽을 수 있지만, 백엔드 전용 설정은 `backend\.env`가 우선입니다.

```env
RUN_LIVE_LLM_TESTS=1
PROXY_TOKEN=실제_토큰
OPENAI_MODEL=openai/gpt-4.1-mini
CHAT_PROXY_URL=https://mlapi.run/.../v1
LIVE_LLM_TIMEOUT_SECONDS=60
```

주의:

- `.env` 파일은 Git에 커밋하지 않습니다.
- 토큰 값이 `여기에 토큰 입력` 또는 `여기에 api key 입력` 그대로면 live 테스트가 skip됩니다.
- 실제 API를 호출하므로 비용, 네트워크 상태, 모델 응답 변화의 영향을 받을 수 있습니다.

PowerShell에서 `.env` 대신 직접 환경 변수를 넣어 실행할 수도 있습니다.

```powershell
$env:RUN_LIVE_LLM_TESTS = "1"
$env:PROXY_TOKEN = "실제_토큰"
$env:OPENAI_MODEL = "openai/gpt-4.1-mini"
$env:CHAT_PROXY_URL = "https://mlapi.run/.../v1"
$env:LIVE_LLM_TIMEOUT_SECONDS = "60"
```

live LLM 전체 실행:

```powershell
python -m pytest backend\tests\live_llm -m live_llm -v -s
```

개별 live 테스트:

```powershell
python -m pytest backend\tests\live_llm\test_live_llm_smoke.py -m live_llm -v -s
python -m pytest backend\tests\live_llm\test_major_selection_live.py -m live_llm -v -s
python -m pytest backend\tests\live_llm\test_general_preference_live.py -m live_llm -v -s
```

## 6. live LLM 테스트에서 봐야 할 것

실행 중 출력되는 `live_llm_config`에서 아래 값을 확인합니다.

```text
model: 설정한 모델명
proxy_enabled: true
timeout_seconds: 설정한 timeout
```

각 호출은 `live_llm_trace`로 요약됩니다.

확인 포인트:

- `success`가 `true`인지
- `latency_ms`가 과도하게 크지 않은지
- 실패 시 `error_code`가 인증 문제인지, timeout인지, 모델 응답 형식 문제인지
- 마지막 `live_llm_summary`의 `failure_count`가 0인지

## 7. 수동 검증 시나리오

자동 테스트 외에 사람이 직접 확인할 때는 아래 자연어 요청을 사용합니다.

| 요청 | 기대 동작 |
| --- | --- |
| 금요일은 반드시 비우고 들을 수 있는 교양 후보를 찾아줘 | Hard 조건 저장 후 `discover_courses` 호출 |
| 금요일 수업이 없는 교양 후보만 잠깐 보여줘 | 세션 조건 저장 없이 일회성 `discover_courses` 호출 |
| 오전 10시 이전 수업은 빼고 3영역 후보를 보여줘 | `earliest_start_time=10:00`, `area=3` 탐색 |
| 컴퓨터프로그래밍을 찾아줘 | `search_courses_by_name` 호출, 상태 변경 없음 |
| 컴퓨터프로그래밍을 반드시 넣어줘 | 검색 결과가 EXACT이면 required course로 저장 |
| 대학수학을 반드시 넣어줘 | 후보가 모호하면 confirmation 요청, 자동 저장 없음 |
| 과제 적은 수업 추천해줘 | 현재 데이터로 확인 불가하므로 unresolved 처리 |
| MAJ101 분반 보여줘 | `get_course_sections` 호출 |
| MAJ101-001 상세 보여줘 | `get_section_details` 호출 |

응답에서 특히 확인할 필드:

- `changed`
- `partially_applied`
- `discovery_results`
- `candidate_courses`
- `needs_confirmation`
- `confirmation_request`
- `unresolved_requests`
- `executed_tools`

## 8. 실패했을 때 확인 순서

1. 기본 테스트가 실패하면 API 키 문제가 아니라 코드 변경 또는 테스트 데이터 문제입니다.
2. live 테스트가 skip되면 `RUN_LIVE_LLM_TESTS=1`과 `PROXY_TOKEN` 설정을 확인합니다.
3. live 테스트가 인증 오류로 실패하면 `PROXY_TOKEN`과 `CHAT_PROXY_URL`을 확인합니다.
4. live 테스트가 timeout이면 `LIVE_LLM_TIMEOUT_SECONDS`를 늘려 다시 실행합니다.
5. 특정 자연어 케이스만 실패하면 모델 응답 변화일 수 있으므로 trace의 case 이름과 실패 assertion을 함께 공유합니다.

## 9. 커밋 전 권장 명령

백엔드만 수정했다면:

```powershell
python -m pytest backend\tests
```

에이전트/LLM 관련 코드를 수정했다면:

```powershell
python -m pytest backend\tests\test_session_state_agent.py backend\tests\test_course_discovery.py
```

실제 LLM 동작까지 확인해야 하는 PR이라면:

```powershell
python -m pytest backend\tests\live_llm -m live_llm -v -s
```

