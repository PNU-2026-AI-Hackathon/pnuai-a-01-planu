# PlaNU Codex 작업 프롬프트(현 상태 반영 버전)

## 작업 저장소
- Repository: `PNU-2026-AI-Hackathon/pnuai-a-01-planu`
- Branch: `RemakeTest`

## 현재 확인된 구현 현실

이 프롬프트는 설계 문서 대신 실제 코드와 테스트를 기준으로 작성한다.

### 1) 현재 구조
- Backend: Python + FastAPI
- Frontend: Flutter + Dart
- 앱 진입점: `frontend/lib/main.dart`
- 핵심 상태 모델: `frontend/lib/models/app_flow_state.dart`
- API Client: `frontend/lib/services/planu_api.dart`
- Repository: `frontend/lib/repositories/major_repository.dart`
- 주요 화면: `frontend/lib/screens/`

### 2) 실제로 확인된 백엔드 API 계약
다음 라우트가 실제 구현 기준으로 사용된다.

- `GET /health`
- `POST /catalog/major`
- `GET /major/courses`
- `POST /major/preview`
- `POST /major/manual-preview`
- `POST /major/confirm`
- `POST /general/prepare`
- `POST /recommend/generate`
- `POST /recommend/rank`

### 3) 실제로 확인된 전공 선택 구조
- 전공 자동 선택 LLM 구조가 아니라, 사용자가 전공 과목과 분반을 직접 선택하는 구조가 현재 코드와 테스트에 맞는다.
- LLM은 교양 조건 해석과 추천 보조에 제한적으로 사용한다.
- 즉, 백엔드 최종 설계는 다음과 같이 정리해야 한다.
  - 전공: 사용자 직접 선택
  - 교양: LLM 조건 해석 보조
  - 추천 시간표: 서버 알고리즘과 랭킹 결과를 최종 기준으로 사용

### 4) 실제 검증 결과
다음 검증은 현재 워크스페이스에서 실행된 결과를 반영한다.

- `flutter analyze` 결과: `No issues found!`
- `flutter test test/timetable_result_screen_test.dart` 결과: `All tests passed!`
- 핵심 백엔드 API 테스트 결과:
  - `test_major_catalog_upload_api.py`
  - `test_major_preview_api.py`
  - `test_general_preparation_api.py`
  - `test_timetable_generation_api.py`
  - `test_timetable_ranking_api.py`
  - 결과: `46 passed, 1 warning in 0.95s`

### 5) 현재 확인된 차이
- 설계 문서의 일부 설명은 실제 구현과 다르다.
- 프롬프트 내 “LLM 자동 전공 선택” 표현은 현재 구현과 맞지 않는다.
- README와 실제 파일/라우트 구조 간 차이가 존재한다.
- 프론트엔드는 화면 흐름을 갖추었지만 일부 단계는 샘플/모크에 가까운 구현이 남아 있다.

---

## Codex에게 전달할 작업 원칙

1. 작업 전에 관련 파일과 기존 구현을 먼저 조사한다.
2. 설계 문서보다 실제 코드와 테스트를 우선한다.
3. 기존 구현을 무작정 삭제하거나 전체 구조를 재작성하지 않는다.
4. API 응답 필드와 오류 코드는 추측하지 않고 실제 코드에 맞춰서 사용한다.
5. 화면에서 직접 API를 호출하지 않고 Repository 또는 이에 준하는 계층을 사용한다.
6. 사용자가 이전 단계로 돌아갔을 때 기존 입력값을 유지한다.
7. 이전 단계 데이터가 변경되면 이후 단계에서 생성된 데이터만 무효화한다.
8. 비동기 요청 중에는 중복 제출을 막는다.
9. 정상 상태뿐 아니라 로딩, 빈 상태, 오류, 재시도 상태를 구현한다.
10. 현재 브랜치에서는 과도한 구조 변경을 한 번에 하지 않고 단계별로 진행한다.
11. 프롬프트 단계명, 파일명, API 명칭은 실 코드 기준으로 수정한다.
12. 최종 목표는 사용자 직접 전공 분반 선택 + LLM 제한적 교양 해석 구조를 구현하는 것이다.

---

## 단계별 작업 지시

### 0단계: 현 상태 분석
- 현재 브랜치와 구현 상태를 확인한다.
- 실제 화면/라우트/API 구조와 테스트 상태를 점검한다.
- 문서와 실제 구현 차이를 정리한다.

### 1단계: 개발 기준선 정리
- Flutter 앱의 화면 이동 구조와 상태관리 구조를 정리한다.
- 기존 구현을 최대한 재사용한다.
- 앱 라우팅 구조, 7단계 상태 모델, 공통 레이아웃, 로딩/오류 UI, API 설정을 정리한다.
- 새 패키지는 꼭 필요한 경우만 추가한다.

### 2단계: 백엔드 API 계약 검증 및 프론트엔드 API Client 구현
- 실제 백엔드 라우트를 기준으로 API Client와 Repository를 검증한다.
- `GET /health`, `POST /catalog/major`, `POST /major/preview`, `POST /major/manual-preview`, `POST /major/confirm`, `POST /general/prepare`, `POST /recommend/generate`, `POST /recommend/rank`를 코드 기준으로 맞춘다.
- 세션 ID, preview ID 등 중간 식별자를 안전하게 관리한다.
- 서버 오류 코드는 실 코드와 응답 모델에 맞춰 처리한다.

### 3단계: 안내·학과 선택·파일 업로드 화면 구현
- `GuideScreen`, `DepartmentSelectScreen`, `FileUploadScreen` 흐름을 실제 파일 구조에 맞춰 연결한다.
- 파일 업로드는 `.xlsx` 우선 검증을 수행하되 서버 검증을 최종 기준으로 한다.
- 이전 입력값을 유지하고 후속 상태를 무효화하는 규칙을 적용한다.

### 4단계: 수강편람 분석 결과와 전공 선택 구현
- `CatalogPreviewScreen`과 `MajorSelectScreen` 구조를 실제 코드 기준으로 연결한다.
- 전공은 사용자가 직접 분반을 선택한다.
- `can_confirm=false`이면 확정 API를 호출하지 않는다.
- 선택 변경 시 이후 교양 및 추천 단계 결과를 무효화한다.

### 5단계: 교양 조건 입력 화면 구현
- 교양 조건은 구조화된 입력과 자유 입력을 분리하여 관리한다.
- `unsupported_conditions`, `warnings`, `truncated`, `diagnostics`를 손실 없이 처리한다.
- `general/prepare`와 `recommend/generate` 호출 순서는 실제 백엔드 계약에 맞춘다.

### 6단계: 시간표 결과 화면 구현
- 후보 1~3개를 보여주고, 템플릿만 바뀌면 `rank` API만 다시 호출한다.
- `rank` 응답의 `rank`, `raw_score`, `score_components`, `load_satisfaction`를 사용자에게 의미 있게 보여준다.
- 빈 결과, 부분 결과, 경고, 오류 상태를 별도로 처리한다.

### 7단계: 전체 사용자 흐름 통합
- Guide → Department → Major Upload → Major Preview/Manual Select → Major Confirm → General Preference → Recommend Generate → Rank → Result 흐름을 연결한다.
- 세션 만료, 중복 제출, 뒤로가기, 상태 무효화 규칙을 유지한다.

### 8단계: 테스트 보강
- 기존 테스트를 훼손하지 않는다.
- 새 기능에 맞는 회귀 테스트와 실패 테스트를 추가한다.
- 실제 실행 환경에 맞는 경로와 모듈 구조로 테스트를 조정한다.

### 9단계: 최종 품질 점검
- README와 현재 구현의 차이를 점검한다.
- 하드코딩, 오래된 문구, 잘못된 명칭, mock 흐름을 정리한다.
- 최종 검증 결과를 보고한다.

---

## 최종 체크리스트

Codex는 아래 조건을 만족해야 한다.

- 설계 문서보다 실제 코드와 API 테스트를 우선한다.
- 전공은 사용자가 직접 분반을 선택하는 구조를 유지한다.
- LLM은 교양 조건 해석과 추천 보조에 제한적으로 사용한다.
- 각 단계별로 작은 수정만 수행한다.
- 실행 전 검증 결과를 기준으로 상태를 보고한다.
- 새 작업을 끝낼 때 수정 파일, 구현 내용, 테스트 결과, 남은 문제를 포함해 보고한다.
