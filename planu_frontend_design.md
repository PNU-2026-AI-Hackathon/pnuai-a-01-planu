# PlaNU 프론트엔드 설계 문서

> 이 문서는 PlaNU MVP의 Flutter 프론트엔드 화면 흐름, 파일 구조, 각 파일 역할, 백엔드 API 연결 방식을 정리한 문서이다. 최신 결정 사항에 따라 **전공 선택은 LLM을 사용하지 않고 사용자가 직접 선택**하며, LLM은 **교양 조건 입력 해석**에만 사용한다.

---

## 1. 프론트엔드 핵심 방향

PlaNU 프론트엔드는 사용자가 복잡한 수강편람 파일을 준비하고, 전공 과목을 직접 선택한 뒤, 교양 추천 결과를 시간표 형태로 확인할 수 있도록 돕는다.

핵심 사용자 흐름은 다음과 같다.

```text
수강편람 다운로드 안내
→ 학과 선택
→ 전공 수강편람 업로드
→ 파싱 결과 확인
→ 전공 과목/분반 직접 선택
→ 교양 조건 입력
→ 추천 시간표 확인
```

전공 과목은 사용자가 직접 선택한다. 교양 과목은 PlaNU가 전공 시간표 위에 추천한다.

---

## 2. 전체 화면 흐름

```text
GuideScreen
→ DepartmentSelectScreen
→ FileUploadScreen
→ CatalogPreviewScreen
→ MajorSelectScreen
→ GeneralPromptScreen
→ TimetableResultScreen
```

| 화면 | 역할 |
|---|---|
| GuideScreen | 부산대 학생지원시스템에서 수강편람을 다운로드하는 방법 안내 |
| DepartmentSelectScreen | 학과 자동완성 선택 |
| FileUploadScreen | 전공 수강편람 필수 업로드, 교양선택 수강편람 선택 업로드 |
| CatalogPreviewScreen | 업로드 파일 파싱 결과 확인 |
| MajorSelectScreen | 전공 과목/분반 직접 선택 |
| GeneralPromptScreen | 교양 추천 조건 입력 |
| TimetableResultScreen | 추천 시간표 후보 1~3 표시 |

---

## 3. 화면별 상세 설계

## 3.1. GuideScreen — 수강편람 다운로드 안내

### 목적

앱을 처음 실행했을 때 사용자가 어떤 파일을 준비해야 하는지 안내한다.

### 핵심 안내 내용

```text
PlaNU를 사용하려면 1학년 전공기초/전공필수 수강편람 파일이 필요합니다.

부산대학교 학생지원시스템에서 수강편람을 조회한 뒤
엑셀 파일로 다운로드해주세요.

교양선택 수강편람은 선택 사항입니다.
업로드하지 않으면 PlaNU가 기본으로 보유한 교양선택 데이터를 사용합니다.
```

### 안내할 다운로드 절차

```text
1. 부산대학교 학생지원시스템 접속
2. 수업 메뉴 이동
3. 수강편람 조회
4. 학년도/학기 선택
5. 전공 또는 교양 영역 선택
6. 조회 후 엑셀 다운로드
```

### 버튼

```text
[파일 준비하러 가기]
[다음]
```

체크리스트는 사용하지 않는다. 전공 수강편람 업로드 여부는 FileUploadScreen에서 검증한다.

---

## 3.2. DepartmentSelectScreen — 학과 선택

### 목적

수강 제한 규칙 적용을 위해 사용자의 학과를 정확하게 선택한다.

학과명은 사용자가 자유 입력하지 않고, 백엔드가 제공하는 목록에서 선택한다.

### 백엔드 API

```text
GET /departments?keyword=컴퓨터
```

### UI 방식

HTML의 `datalist`와 유사한 자동완성 UI를 사용한다.

Flutter에서는 `Autocomplete<String>` 또는 유사한 커스텀 위젯을 사용한다.

### 화면 예시

```text
[학과 선택]

학과명을 입력하세요.
[ 컴퓨터 ]

검색 결과
- 정보컴퓨터공학부
- 컴퓨터공학전공
- 전기컴퓨터공학부

[다음]
```

### 검증 규칙

```text
- 사용자가 목록에서 학과를 선택해야 다음으로 이동할 수 있다.
- 단순히 텍스트만 입력한 상태에서는 다음 버튼을 비활성화한다.
```

---

## 3.3. FileUploadScreen — 수강편람 파일 업로드

### 목적

전공 수강편람 파일과 선택적으로 교양선택 수강편람 파일을 업로드한다.

### 입력 파일

```text
필수:
- 1학년 전공기초/전공필수 수강편람 파일

선택:
- 교양선택 수강편람 파일
```

### UI 예시

```text
[수강편람 업로드]

1학년 전공 수강편람
[파일 선택] computer_major.xlsx

교양선택 수강편람
[파일 선택] general_area_3.xlsx
업로드하지 않으면 PlaNU 기본 데이터를 사용합니다.

[수강편람 분석하기]
```

### 검증 규칙

```text
- 전공 수강편람 파일이 없으면 분석 버튼 비활성화
- 교양선택 파일은 없어도 진행 가능
- 지원 형식: .xlsx
- 최대 크기: 백엔드 정책에 맞춰 안내
```

### 백엔드 API

```text
POST /catalog/parse
```

요청 형식:

```text
multipart/form-data

department
major_catalog_file
elective_catalog_file(optional)
```

응답에서 `session_id`, `major_candidates`, `elective_candidates_count`를 받는다.

---

## 3.4. CatalogPreviewScreen — 파싱 결과 확인

### 목적

업로드한 파일이 제대로 분석되었는지 사용자에게 보여준다.

### 화면 예시

```text
[수강편람 분석 결과]

전공 후보 과목: 12개
교양선택 후보 과목: 45개

전공 후보 예시
- 컴퓨터프로그래밍 001 / 김OO
- 이산수학 002 / 박OO
- 논리회로 001 / 최OO

[전공 과목 선택하기]
```

### 검증 규칙

```text
- 전공 후보 과목이 0개이면 다음 단계로 이동할 수 없다.
- 교양선택 후보 과목이 0개인 것은 허용한다.
  - 사용자가 교양선택 파일을 업로드하지 않은 경우 서버 기본 데이터를 사용한다.
```

### 전공 후보 0개 메시지

```text
전공 과목을 찾지 못했습니다.
1학년 전공기초/전공필수 수강편람 파일인지 확인해주세요.
```

---

## 3.5. MajorSelectScreen — 전공 과목/분반 직접 선택

### 목적

사용자가 업로드한 전공 수강편람에서 파싱된 전공 후보 목록을 보고 직접 전공 과목과 분반을 선택한다.

LLM은 사용하지 않는다.

### UI 방식

과목명별로 묶고, 각 과목 안에서 분반을 radio button으로 선택한다.

### 화면 예시

```text
[전공 과목 선택]

컴퓨터프로그래밍
○ 001분반 / 김OO / 월·수 09:00~10:15 / 제6공학관
○ 002분반 / 박OO / 월·수 10:30~11:45 / 제6공학관

이산수학
○ 001분반 / 최OO / 화·목 13:30~14:45 / 제6공학관
○ 002분반 / 이OO / 화·목 15:00~16:15 / 제6공학관

선택한 전공
- 컴퓨터프로그래밍 001
- 이산수학 002

[전공 시간표 확정]
```

### UI 규칙

```text
- 같은 과목에서는 한 분반만 선택 가능
- 서로 다른 과목은 여러 개 선택 가능
- 선택한 전공끼리 시간이 겹치면 경고 표시
- 시간 충돌이 있으면 확정 버튼 비활성화
```

### 선택 요약 표시

화면 하단에 사용자가 선택한 전공 목록을 항상 보여준다.

```text
선택한 전공
- 컴퓨터프로그래밍 001 / 김OO
- 이산수학 002 / 최OO
```

### 충돌 메시지 예시

```text
선택한 전공 과목끼리 시간이 겹칩니다.

- 컴퓨터프로그래밍 001
- 이산수학 002
```

### 백엔드 API

```text
POST /major/confirm
```

요청:

```json
{
  "session_id": "session-id",
  "fixed_courses": []
}
```

서버는 선택된 전공이 실제 `major_candidates`에 포함되어 있는지, 시간 충돌이 없는지 검증한다.

---

## 3.6. GeneralPromptScreen — 교양 조건 입력

### 목적

확정된 전공 시간표 위에 어떤 교양을 추천받고 싶은지 입력한다.

이 단계에서만 LLM이 사용된다.

### 입력 요소

```text
- 교양 조건 프롬프트
- 교양필수 개수
- 교양선택 개수
```

### 화면 예시

```text
[교양 추천 조건 입력]

교양 수업에 대한 조건을 입력해주세요.

예시:
- 오전 수업은 피하고 싶어요.
- 금요일은 공강이면 좋겠어요.
- 연강 이동이 힘든 시간표는 싫어요.
- 공강이 하루 있었으면 좋겠어요.

교양필수 개수
[-] 1 [+]

교양선택 개수
[-] 1 [+]

[최종 시간표 추천받기]
```

### 백엔드 API

```text
POST /recommend
```

요청:

```json
{
  "session_id": "session-id",
  "required_general_count": 1,
  "elective_general_count": 1,
  "user_prompt": "오전 수업은 가능하면 피하고 싶고, 금요일은 공강이면 좋겠어요."
}
```

---

## 3.7. TimetableResultScreen — 최종 추천 시간표

### 목적

추천 시간표 후보를 시간표 형태로 보여준다.

### UI 구성

```text
[추천 시간표]

[후보 1] [후보 2] [후보 3]

후보 1
점수 92점

시간표 그리드

과목 목록
- 컴퓨터프로그래밍 001 / 김OO / 월·수 09:00
- 고전읽기와토론 023 / 박OO / 화 10:30
- 문학과상상력 002 / 최OO / 목 13:30

추천 이유
- 전공 수업과 시간 충돌이 없습니다.
- 금요일 공강 조건을 만족합니다.
- 연강 이동 위험이 없습니다.

주의사항
- 실제 수강 가능 여부와 정원은 학생지원시스템에서 확인해주세요.

[교양 조건 수정]
[전공 다시 선택]
[파일 다시 업로드]
```

### 후보 표시 방식

후보 3개는 탭 형태로 표시한다.

```text
[후보 1] [후보 2] [후보 3]
```

### 시간표 UI

`schedule_items`를 기반으로 그린다.

정렬 기준:

```text
요일: MON → TUE → WED → THU → FRI
시간: start 오름차순
```

### 과목 유형 색상

과목 유형별로 카드 색을 다르게 줄 수 있다.

```text
전공: 색상 A
교양필수: 색상 B
교양선택: 색상 C
```

단, 색상만으로 구분하지 않고 카드 안에 라벨도 함께 표시한다.

```text
[전공] 컴퓨터프로그래밍
[교양필수] 고전읽기와토론
[교양선택] 문학과상상력
```

---

## 4. Flutter 파일 구조

```text
lib/
 ├─ main.dart
 │
 ├─ models/
 │   ├─ course.dart
 │   ├─ class_time.dart
 │   ├─ timetable_recommendation.dart
 │   ├─ warning_message.dart
 │   └─ department.dart
 │
 ├─ services/
 │   ├─ api_client.dart
 │   ├─ department_api.dart
 │   ├─ catalog_api.dart
 │   ├─ major_api.dart
 │   └─ recommend_api.dart
 │
 ├─ screens/
 │   ├─ guide_screen.dart
 │   ├─ department_select_screen.dart
 │   ├─ file_upload_screen.dart
 │   ├─ catalog_preview_screen.dart
 │   ├─ major_select_screen.dart
 │   ├─ general_prompt_screen.dart
 │   └─ timetable_result_screen.dart
 │
 ├─ widgets/
 │   ├─ step_progress_bar.dart
 │   ├─ file_picker_card.dart
 │   ├─ course_group_card.dart
 │   ├─ course_option_tile.dart
 │   ├─ selected_course_summary.dart
 │   ├─ prompt_input_card.dart
 │   ├─ timetable_grid.dart
 │   ├─ recommendation_tabs.dart
 │   └─ warning_banner.dart
 │
 └─ state/
     └─ planu_flow_state.dart
```

---

## 5. 파일별 역할

## 5.1. `main.dart`

앱 진입점이다.

```text
- MaterialApp 생성
- 라우팅 설정
- 초기 화면 GuideScreen 지정
```

## 5.2. models

### `course.dart`

백엔드의 Course 데이터를 표현한다.

```text
- courseId
- courseName
- category
- area
- credit
- division
- professor
- classTimes
```

### `class_time.dart`

수업 시간 정보를 표현한다.

```text
- day
- start
- end
- classroom
- buildingCode
```

### `timetable_recommendation.dart`

추천 후보 하나를 표현한다.

```text
- rank
- score
- totalCredit
- courses
- scheduleItems
- reasons
- warnings
```

### `warning_message.dart`

경고 메시지를 표현한다.

```text
- type
- message
- fromCourse
- toCourse
```

### `department.dart`

학과 목록 데이터를 표현한다.

```text
- name
```

## 5.3. services

### `api_client.dart`

공통 HTTP 클라이언트이다.

```text
- baseUrl 관리
- 공통 header 설정
- 에러 응답 처리
```

### `department_api.dart`

```text
GET /departments
```

학과 자동완성 목록을 가져온다.

### `catalog_api.dart`

```text
POST /catalog/parse
```

전공 수강편람 및 선택 교양선택 수강편람을 업로드한다.

### `major_api.dart`

```text
POST /major/confirm
```

사용자가 선택한 전공 과목을 확정한다.

### `recommend_api.dart`

```text
POST /recommend
```

교양 추천 요청을 보낸다.

## 5.4. screens

### `guide_screen.dart`

수강편람 다운로드 방법을 안내한다.

### `department_select_screen.dart`

학과 자동완성 선택 화면이다.

### `file_upload_screen.dart`

전공 수강편람과 교양선택 수강편람을 업로드하는 화면이다.

### `catalog_preview_screen.dart`

파싱 결과를 보여준다.

### `major_select_screen.dart`

전공 과목/분반을 직접 선택하는 화면이다.

### `general_prompt_screen.dart`

교양 추천 조건을 입력하는 화면이다.

### `timetable_result_screen.dart`

최종 추천 시간표 후보를 보여주는 화면이다.

## 5.5. widgets

### `step_progress_bar.dart`

현재 진행 단계를 표시한다.

```text
안내 → 학과 → 파일 → 전공 → 교양 → 결과
```

### `file_picker_card.dart`

파일 선택 UI를 카드 형태로 제공한다.

### `course_group_card.dart`

전공 과목명을 기준으로 분반 목록을 묶어 보여준다.

### `course_option_tile.dart`

각 분반 선택 항목을 표시한다.

### `selected_course_summary.dart`

사용자가 선택한 전공 과목 요약을 보여준다.

### `prompt_input_card.dart`

교양 조건 프롬프트 입력창을 제공한다.

### `timetable_grid.dart`

`schedule_items`를 기반으로 시간표 그리드를 그린다.

### `recommendation_tabs.dart`

후보 1~3을 탭 형태로 전환한다.

### `warning_banner.dart`

오류, 경고, 연강 위험, 조건 완화 안내 등을 표시한다.

## 5.6. state

### `planu_flow_state.dart`

화면 간 상태를 저장한다.

```text
- selectedDepartment
- sessionId
- majorCatalogFile
- electiveCatalogFile
- majorCandidates
- selectedMajorCourses
- requiredGeneralCount
- electiveGeneralCount
- generalPrompt
- recommendations
```

MVP에서는 `StatefulWidget`과 화면 이동 arguments만으로도 구현 가능하다. 다만 화면이 여러 개이므로 `planu_flow_state.dart` 형태로 흐름 상태를 분리해두면 유지보수에 유리하다.

---

## 6. 프론트 상태 흐름

```text
앱 시작
↓
GuideScreen
↓
DepartmentSelectScreen
  - selectedDepartment 저장
↓
FileUploadScreen
  - majorCatalogFile 선택
  - electiveCatalogFile 선택 optional
  - /catalog/parse 호출
↓
CatalogPreviewScreen
  - sessionId 저장
  - majorCandidates 저장
↓
MajorSelectScreen
  - majorCandidates를 과목별로 표시
  - 사용자가 전공 과목/분반 선택
  - /major/confirm 호출
↓
GeneralPromptScreen
  - generalPrompt 입력
  - requiredGeneralCount 선택
  - electiveGeneralCount 선택
  - /recommend 호출
↓
TimetableResultScreen
  - recommendations 표시
```

---

## 7. 백엔드 API 연결

| 화면 | API |
|---|---|
| DepartmentSelectScreen | `GET /departments` |
| FileUploadScreen | `POST /catalog/parse` |
| MajorSelectScreen | `POST /major/confirm` |
| GeneralPromptScreen | `POST /recommend` |
| TimetableResultScreen | API 응답 표시 |

---

## 8. 에러 처리 UI

### 8.1. 파일 형식 오류

```text
수강편람 형식을 인식하지 못했습니다.
학생지원시스템에서 다운로드한 .xlsx 파일인지 확인해주세요.
```

### 8.2. 전공 후보 0개

```text
전공 과목을 찾지 못했습니다.
1학년 전공기초/전공필수 수강편람 파일인지 확인해주세요.
```

### 8.3. 전공 시간 충돌

```text
선택한 전공 과목끼리 시간이 겹칩니다.
충돌하는 과목을 확인해주세요.
```

### 8.4. 세션 만료

```text
세션이 만료되었습니다.
수강편람 파일을 다시 업로드해주세요.
```

### 8.5. 추천 결과 없음

```text
조건을 만족하는 시간표를 찾지 못했습니다.
교양 조건을 조금 완화해 보세요.
```

---

## 9. 로딩 상태 문구

작업별로 다른 로딩 문구를 보여준다.

```text
수강편람을 분석하고 있어요.
전공 과목 목록을 정리하고 있어요.
선택한 전공 시간표를 확인하고 있어요.
교양 조건을 해석하고 있어요.
교양 시간표 후보를 만들고 있어요.
연강 이동 가능성을 확인하고 있어요.
```

---

## 10. 결과 화면 신뢰 문구

추천 결과 화면 하단에 다음 문구를 표시한다.

```text
PlaNU는 수강편람 기반으로 시간표 후보를 추천합니다.
실제 수강 가능 여부, 정원, 폐강 여부는 수강신청 시점의 학생지원시스템에서 반드시 확인해주세요.
```

---

## 11. 최종 프론트 흐름 요약

```text
1. 수강편람 다운로드 방법을 안내한다.
2. 사용자가 학과를 자동완성 목록에서 선택한다.
3. 전공 수강편람 파일을 필수로 업로드한다.
4. 선택적으로 교양선택 수강편람 파일을 업로드한다.
5. 업로드한 파일의 파싱 결과를 확인한다.
6. 전공 과목/분반은 사용자가 직접 선택한다.
7. 선택된 전공 시간표를 서버에 확정한다.
8. 교양 조건을 프롬프트로 입력한다.
9. 서버가 교양 시간표 후보를 추천한다.
10. 후보 1~3을 시간표 형태로 보여준다.
```

---

## 12. 한 줄 요약

PlaNU 프론트엔드는 사용자가 부산대 수강편람 파일을 준비하고, 전공 과목은 직접 선택하며, 교양 조건만 자연어로 입력해 추천 시간표를 확인할 수 있도록 단계형 화면 흐름을 제공한다. 전공 선택은 빠르고 확실한 직접 선택 방식으로 처리하고, LLM은 교양 조건 해석에만 사용한다.
