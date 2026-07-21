# PlaNU 프런트엔드 화면 흐름

조사 기준: `origin/main` 및 2026-07-21에 fetch한 모든 비백엔드 원격 브랜치. 앱은 `Navigator`와 최상위 `AppFlowState` 하나를 사용한다. API 기본 주소는 `--dart-define=PLANU_API_BASE_URL=...`로 지정하며 Android 에뮬레이터 기본값은 `http://10.0.2.2:8000`이다.

## 핵심 흐름

`GuideScreen` → `DepartmentSelectScreen` → `FileUploadScreen2` → `MajorPromptScreen` → `MajorPreviewScreen` → `FileUploadScreen3` → `GeneralPreferenceScreen` → `TimetableLoadingScreen` → `TimetableResultScreen`

`CatalogDownloadGuideScreen`은 GuideScreen에서 선택적으로 열고 뒤로 돌아오는 보조 화면이다. `MajorSelectScreen`은 백엔드 직접 선택 확정 계약이 없어 핵심 흐름에서 완료 처리하지 않는다.

## 화면별 명세

### PlaNU 안내

- 실제 구현 파일: `frontend/lib/screens/guide_screen.dart`
- 현재 구현 여부: 완료
- 이전/다음: 앱 시작 / 학과 입력, 선택적으로 다운로드 상세 안내
- 역할: 준비물, 세션·개인정보 안내와 학생지원시스템 링크
- 입력/전달/API: 없음 / 없음 / 외부 URL
- 성공/실패: 화면 이동 또는 링크 실행 / SnackBar 안내
- mock·미완성: 없음
- 완료 조건: 다음 버튼이 학과 화면으로 이동

### 수강편람 다운로드 상세 안내

- 실제 구현 파일: `frontend/lib/screens/catalog_download_guide_screen.dart`
- 현재 구현 여부: 완료
- 이전/다음: 안내 / 시스템 뒤로 가기로 안내 복귀
- 역할: 다운로드 절차와 실제 이미지 표시
- 입력/전달/API: 없음
- 성공/실패: 안내 표시 / asset 누락 시 Flutter 이미지 오류
- mock·미완성: 없음
- 완료 조건: 선택 진입 및 정상 복귀

### 학과 입력

- 실제 구현 파일: `frontend/lib/screens/department_select_screen.dart`
- 현재 구현 여부: 완료(PR #14가 main에 병합됨)
- 이전/다음: 안내 / 전공 수강편람 업로드
- 역할: 제한 대상 학과 자동완성 및 임의 학과 직접 입력
- 입력/전달/API: 학과 문자열 / `department` / 없음
- 성공/실패: 비어 있지 않은 값을 전달 / JSON 로드 실패를 표시하되 직접 입력 허용
- mock·미완성: mock 없음. 자동완성 원본은 `frontend/src/data/departments.json`, 변수는 `_departments`, asset 상수는 `_departmentsAsset`
- 완료 조건: 목록 밖 학과도 허용

### 전공 수강편람 업로드

- 실제 구현 파일: `frontend/lib/screens/file_upload_screen2.dart`
- 현재 구현 여부: 완료
- 이전/다음: 학과 입력 / 전공 프롬프트
- 역할: `.xlsx` 선택, 확장자·10MB 용량 검증
- 입력/전달/API: 파일 / 파일명·bytes·sessionId / `POST /catalog/major` multipart(`major_catalog`, `department`)
- 성공/실패: sessionId 저장 후 이동 / 현재 화면 입력 유지 및 오류 표시
- mock·미완성: 파일 선택 콜백은 앱 루트에서 실제 `file_picker`로 주입
- 완료 조건: 업로드 성공 전 이동 금지

### 전공 프롬프트 입력

- 실제 구현 파일: `frontend/lib/screens/major_prompt_screen.dart`
- 현재 구현 여부: 완료
- 이전/다음: 전공 업로드 / 전공 검증
- 역할: 과목명·분반 자연어 입력
- 입력/전달/API: prompt·sessionId / MajorPreviewResponse / `POST /major/preview`
- 성공/실패: 미리보기 이동 / 입력 유지, 오류 및 재시도
- mock·미완성: 없음
- 완료 조건: 공백 차단, 중복 요청 차단

### 전공 시간표 검증

- 실제 구현 파일: `frontend/lib/screens/major_preview_screen.dart`
- 현재 구현 여부: 완료
- 이전/다음: 전공 프롬프트 / 교양 조건 또는 직접 선택·재입력
- 역할: matched/ambiguous/unmatched/conflict와 총 학점 검증
- 입력/전달/API: MajorPreviewResponse / 확정 과목 / `POST /major/preview`(피드백), `POST /major/confirm`
- 성공/실패: 확정 후 교양 화면 / 입력 유지, 세션 만료 시 초기화
- mock·미완성: 없음
- 완료 조건: `can_confirm` false이면 확정 불가

### 전공 직접 선택

- 실제 구현 파일: `frontend/lib/screens/major_select_screen.dart`
- 현재 구현 여부: UI 구현, API 계약 미완성
- 이전/다음: 전공 검증 / 계약 확정 전 연결 보류
- 역할: 파싱된 과목·분반 직접 선택
- 입력/전달/API: 후보 목록 / 선택 과목의 `course_id` 목록이 필요 / 현재 지원 API 없음
- 성공/실패: 구현하지 않음 / mock 확정 금지
- mock·미완성: 브랜치 UI의 샘플 모델은 핵심 흐름에서 사용하지 않음
- 완료 조건: `/major/confirm`은 `preview_id`만 받으므로, 선택 ID를 받는 preview 생성/confirm API가 필요

### 교양 조건 및 템플릿

- 실제 구현 파일: `frontend/lib/screens/general_preference_screen.dart`
- 현재 구현 여부: 핵심 입력·연결 완료
- 이전/다음: 전공 확정 / 생성 중
- 역할: 교양 영역 9종(7개 효원균형 영역, 효원브릿지, 인성과사회봉사), 프롬프트, 템플릿, 목표 학점, 추가 교양 수 입력
- 입력/전달/API: 관련 AppFlowState 값 / 생성 입력 / 다음 화면에서 `/general/prepare`
- 성공/실패: 생성 화면 이동 / 교양 영역 미선택 또는 빈 프롬프트는 현 화면 표시
- mock·미완성: 교양 파일 선택 UI는 아직 없음(백엔드는 파일 생략 시 fallback catalog 지원)
- 완료 조건: 입력 상태 유지 및 템플릿 코드 매핑

### 교양 수강편람 업로드

- 실제 구현 파일: `frontend/lib/screens/file_upload_screen3.dart`
- 현재 구현 여부: 완료(`origin/Fileuploadscreen3` UI를 현재 상태 흐름에 맞게 통합)
- 이전/다음: 전공 확정 / 교양 조건 및 템플릿
- 역할: 교양선택 수강편람 `.xlsx` 선택 및 검증
- 입력/전달/API: 파일 / `electiveCatalogName`, `electiveCatalogBytes` / 다음 생성 단계에서 `POST /general/prepare`
- 성공/실패: 파일을 상태에 저장하고 교양 조건 화면으로 이동 / 현재 화면에 검증 오류 표시
- mock·미완성: 없음
- 완료 조건: 교양 조건 화면 진입 전에 실제 파일 bytes 저장

### 시간표 생성 중

- 실제 구현 파일: `frontend/lib/screens/timetable_loading_screen.dart`
- 현재 구현 여부: 완료
- 이전/다음: 교양 조건 / 결과
- 역할: 연속 API 상태 표시 및 중복 요청 차단
- 입력/전달/API: AppFlowState / generatedCandidates·rankedCandidates / `POST /general/prepare`, `/recommend/generate`, `/recommend/rank`
- 성공/실패: 결과로 replace / SnackBar 후 교양 화면 복귀, 세션 만료 시 처음으로
- mock·미완성: 없음
- 완료 조건: 각 API 성공 뒤 다음 호출

### 추천 결과

- 실제 구현 파일: `frontend/lib/screens/timetable_result_screen.dart`
- 현재 구현 여부: API 데이터 목록과 재랭킹 완료
- 이전/다음: 생성 중 / 교양 조건 수정 또는 처음부터
- 역할: 후보 비교, 템플릿 변경
- 입력/전달/API: rankedCandidates·template / 변경 template / 템플릿 변경 시 `POST /recommend/rank`만 호출
- 성공/실패: 결과 갱신 / 기존 후보 유지 및 오류 표시
- mock·미완성: 고급 시간표 그리드 UI는 미통합
- 완료 조건: 재랭킹 시 prepare/generate 재호출 금지

## 브랜치 조사

- `origin/PreludeEllakin-patch-1`, `origin/feedback`: main에 병합됨. 재병합하지 않음.
- `origin/FileUploadScreen2`: 전공 업로드와 `major_select_screen.dart`. 현재 흐름에 필요한 구현을 기존 통합 브랜치에서 사용.
- `origin/Fileuploadscreen3`: FileUploadScreen2의 중복 후속안. 중복이라 제외.
- `origin/K/FileUploadScreen`: 학과 화면을 삭제하는 오래된 업로드안. 제외.
- `origin/K/GeneralPromptScreen`: 오래된 요청 모델과 빈 기본 callback 포함. UI 전체 병합 대신 현재 백엔드 계약에 맞는 화면을 구현.
- `origin/K/TimetableResultScreen`: 샘플 데이터 중심 결과 UI와 빈 callback 포함. API 연결 부분을 새 흐름에 맞춰 구현.
- `origin/kys-catalog-preview`: 현재 요구 흐름에 없는 별도 catalog preview라 제외.
- `origin/kys-major-llm-preview`: 실제 전공 preview/confirm 모델·서비스·상태를 통합.
- `origin/kys-major-select`: 직접 선택 UI. 백엔드 계약 부재로 핵심 흐름 연결 제외.

## 공통 오류

`ApiError`가 서버 `error.code/message/details`를 보존한다. `SESSION_NOT_FOUND`는 상태를 초기화하고 GuideScreen으로 돌아간다. 파일 오류는 업로드 단계에 표시하고, `INVALID_SESSION_STAGE`를 포함한 단계 오류는 현재 입력을 유지한 채 이전 입력 화면에서 재시도하게 한다.
