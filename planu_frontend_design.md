# PlaNU 프론트엔드 설계 문서

> 이 문서는 PlaNU MVP의 Flutter 프론트엔드 화면 흐름, 컴포넌트 구조, 상태관리, 백엔드 API 연결, 오류·로딩·접근성 기준을 정리한 2차 설계 문서이다. **전공 선택은 사용자가 직접 수행**하고, LLM은 구조화 선택지로 표현하기 어려운 **추가 요청 해석**에 제한적으로 사용한다. 구현은 한 화면의 완성도보다 전체 사용자 흐름의 종단 간 동작을 우선한다.

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
→ 필수 조건·시간표 스타일·추가 요청 입력
→ 추천 시간표 후보 비교
```

전공 과목은 사용자가 직접 선택한다. 교양 과목은 PlaNU가 확정된 전공 시간표 위에 추천한다.

### 구현 우선순위 원칙

```text
1. 모든 핵심 화면을 연결해 전체 흐름이 끝까지 동작하도록 한다.
2. 실제 API 연결 전에도 화면과 상태 모델의 계약을 확정한다.
3. 화면은 API 클라이언트를 직접 호출하지 않고 Repository를 통해 데이터를 요청한다.
4. 구조화 조건과 자유 입력은 별도 상태와 별도 요청 필드로 관리한다.
5. 오류·빈 상태·로딩 상태도 정상 화면과 동일한 수준으로 설계한다.
```

### 공통 화면 이동 원칙

- 모든 핵심 화면에 현재 단계와 전체 단계를 함께 표시한다.
- 사용자가 이전 화면으로 돌아가도 이미 입력한 값은 유지한다.
- 이전 단계의 핵심 데이터가 변경되면 이후 단계에서 파생된 데이터는 무효화한다.
- 중복 제출을 막기 위해 요청 중에는 주요 실행 버튼을 비활성화한다.
- 시스템 뒤로가기와 화면 내 이전 버튼의 동작을 일치시킨다.

---

## 2. 전체 화면 흐름

```text
GuideScreen
→ DepartmentSelectScreen
→ FileUploadScreen
→ CatalogPreviewScreen
→ MajorSelectScreen
→ GeneralPreferenceScreen
→ TimetableResultScreen
```

| 화면 | 역할 |
|---|---|
| GuideScreen | 부산대 학생지원시스템에서 수강편람을 다운로드하는 방법 안내 |
| DepartmentSelectScreen | 학과 자동완성 선택 |
| FileUploadScreen | 전공 수강편람 필수 업로드, 교양선택 수강편람 선택 업로드 |
| CatalogPreviewScreen | 업로드 파일 파싱 결과 확인 |
| MajorSelectScreen | 전공 과목/분반 직접 선택 |
| GeneralPreferenceScreen | 필수 조건, 시간표 스타일, 추가 요청 입력 |
| TimetableResultScreen | 후보 1~3, 필수 조건 충족 내역, 선호 적합도 근거 표시 |

### 단계 표시 규칙

```text
안내 → 학과 → 파일 → 분석 → 전공 → 조건 → 결과
```

모바일에서는 공간이 부족할 경우 다음 형식으로 축약한다.

```text
5 / 7  전공 선택
```

각 화면의 하단 주요 버튼 영역은 가능한 한 동일한 위치와 구조를 유지한다.

```text
[이전]                                  [다음 또는 주요 실행]
```

첫 화면에는 이전 버튼을 표시하지 않는다. 결과 화면에서는 이전 단계로 돌아가는 목적별 버튼을 제공한다.

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

### 데이터 및 상태 규칙

- UI에는 학과명과 필요한 경우 단과대학명을 함께 표시한다.
- 내부 상태에는 표시 문자열만 저장하지 않고 `departmentId`와 `departmentName`을 함께 저장한다.
- 검색어 변경으로 기존 선택과 입력 문자열이 달라지면 선택 상태를 해제한다.
- 학과 목록 로딩 실패 시 재시도 버튼을 제공한다.
- 서버 응답이 비어 있으면 검색어 수정 안내를 표시한다.

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

### 업로드 UX 규칙

- 선택한 파일명, 확장자, 파일 크기를 표시한다.
- 파일 변경과 삭제 기능을 제공한다.
- 업로드 중에는 파일 선택과 분석 버튼을 잠근다.
- 동일 요청을 중복 전송하지 않는다.
- 파일 선택 완료와 서버 업로드 완료를 구분해 표시한다.
- 업로드 실패 시 사용자가 선택한 로컬 파일 정보는 유지하고 재시도할 수 있게 한다.

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

### 표시 및 이동 규칙

- 전체 후보 수와 함께 과목명, 분반, 교수, 시간, 강의실의 일부 예시를 제공한다.
- 긴 목록 전체를 이 화면에서 탐색하게 하지 않는다.
- 분석 결과가 예상과 다르면 `[파일 다시 선택]` 경로를 명확히 제공한다.
- 파일을 다시 업로드하면 기존 `sessionId`, 전공 선택, 추천 조건, 추천 결과를 초기화한다.

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

### 프론트 검증과 서버 검증의 역할

```text
프론트:
- 선택 즉시 시간 충돌을 계산해 빠르게 피드백
- 같은 과목의 복수 분반 선택 방지
- 선택 요약과 총 학점 표시

서버:
- 후보 목록에 존재하는 과목인지 최종 검증
- 시간 데이터와 제한 규칙을 다시 검증
- 변조되거나 만료된 요청 거부
```

프론트에서 충돌이 없더라도 서버 검증 결과를 최종 기준으로 사용한다.

---

## 3.6. GeneralPreferenceScreen — 교양 조건 및 시간표 선호 입력

### 목적

확정된 전공 시간표 위에 어떤 교양을 추천받고 싶은지 입력한다.

사용자는 점수나 가중치를 직접 조정하지 않고, 의미가 명확한 조건과 시간표 스타일을 선택한다. 자유 입력란은 선택지로 표현하기 어려운 추가 요청을 입력하는 용도로 사용한다.

이 단계에서만 LLM이 사용되며, 구조화된 선택 조건과 자유 입력을 함께 해석한다.

### 화면 구성

화면은 다음 세 영역으로 구성한다.

```text
A. 꼭 지켜야 할 조건
B. 원하는 시간표 스타일
C. 추가 요청
```

#### A. 꼭 지켜야 할 조건

```text
조건을 만족하지 않는 시간표는 추천에서 제외됩니다.
```

선택 가능한 항목 예시:

```text
- 오전 수업 금지
- 특정 요일 공강 필수
- 최대 연속 수업 제한
- 특정 시간대 제외
```

#### B. 원하는 시간표 스타일

```text
조건을 더 잘 만족하는 시간표가 높은 순위로 추천됩니다.
```

선택 가능한 항목 예시:

```text
- 늦게 시작하기
- 몰아서 듣기
- 등교일 줄이기
- 연강 줄이기
- 특정 요일 공강 선호
```

향후 필요 시 `여유 있게 듣기`와 같은 스타일을 추가할 수 있다. 단, `몰아서 듣기`와 의미가 충돌하므로 동시에 선택되지 않도록 처리한다.

#### C. 추가 요청

자유 입력란에는 다음 안내를 표시한다.

```text
위 선택지로 표현하기 어려운 추가 요청을 적어 주세요.

예: 월요일은 수업을 적게 넣고, 수요일은 학교에 오래 있어도 괜찮아요.
```

카드에서 이미 선택한 조건을 다시 입력해야 한다는 인상을 주지 않도록 안내 문구를 명확하게 표시한다.

### 선택 카드 UI

일반 체크박스 목록 대신 제목과 설명이 함께 보이는 소형 선택 카드 형태로 구현한다.

```text
┌────────────────────────────┐
│ ✓ 늦게 시작하기            │
│ 오전 수업이 적은 시간표를  │
│ 우선합니다.                 │
└────────────────────────────┘
```

UI 규칙:

```text
- 카드 전체를 클릭할 수 있어야 한다.
- 여러 카드를 동시에 선택할 수 있어야 한다.
- 선택된 카드는 테두리, 배경, 체크 아이콘 중 하나 이상으로 명확히 구분한다.
- 한 개만 선택되는 일반 버튼 형태로 구현하지 않는다.
- 데스크톱에서는 2~3열, 모바일에서는 1열로 배치한다.
- Flutter의 Checkbox, Semantics 또는 동등한 접근성 속성을 적용한다.
- 색상만으로 선택 상태나 하드/소프트 조건을 구분하지 않는다.
```

### 카드별 세부 설정

일부 카드는 선택 시 추가 설정 영역을 펼친다. 선택을 해제하면 관련 상태를 초기화하고 백엔드 요청에서 제외한다.

#### 오전 수업 금지

```text
- 오전 기준 시간 선택
- 기본값: 12:00
```

#### 특정 요일 공강 필수

```text
- 월~금 요일 선택 버튼 표시
- 여러 요일 선택 가능
- 필수 공강임을 제목과 설명으로 명시
```

#### 특정 요일 공강 선호

```text
- 월~금 요일 선택 버튼 표시
- 여러 요일 선택 가능
- 필수 공강과 시각적·텍스트적으로 구분
```

#### 최대 연속 수업 제한

```text
- 최대 1개, 2개, 3개 등 선택
```

#### 특정 시간대 제외

```text
- 시작 시간 선택
- 종료 시간 선택
- 시작 시간이 종료 시간보다 늦지 않도록 검증
```

### 충돌 및 중복 조건 처리

```text
- 몰아서 듣기 / 여유 있게 듣기: 동시에 선택할 수 없도록 처리
- 오전 수업 금지 / 늦게 시작하기: 동시에 선택 가능
- 동일 요일의 공강 필수 / 공강 선호: 공강 필수 하나로 정리
```

현재 UI에서는 충돌 항목 선택 시 이전 선택을 해제하고 짧은 안내 문구를 표시하는 방식을 우선 적용한다.

예시:

```text
'몰아서 듣기'와 '여유 있게 듣기'는 함께 선택할 수 없어 이전 선택을 해제했습니다.
```

### 화면 예시

```text
[교양 추천 조건 입력]

꼭 지켜야 할 조건
조건을 만족하지 않는 시간표는 추천에서 제외됩니다.

[오전 수업 금지] [특정 요일 공강 필수]
[최대 연속 수업 제한] [특정 시간대 제외]

원하는 시간표 스타일
조건을 더 잘 만족하는 시간표가 높은 순위로 추천됩니다.

[늦게 시작하기] [몰아서 듣기]
[등교일 줄이기] [연강 줄이기]
[특정 요일 공강 선호]

추가 요청
위 선택지로 표현하기 어려운 추가 요청을 적어 주세요.
[월요일 수업은 가능하면 적었으면 좋겠어요.]

교양필수 개수
[-] 1 [+]

교양선택 개수
[-] 1 [+]

[최종 시간표 추천받기]
```

### 상태 모델

구조화된 조건과 자유 입력을 분리하여 관리한다.

```text
- selectedPreferences
  - noMorningClasses
  - requiredFreeDays
  - preferFreeDays
  - maxConsecutiveClasses
  - excludedTimeRange
  - preferLateStart
  - compactSchedule
  - minimizeAttendanceDays
  - minimizeConsecutiveClasses
  - relaxedSchedule(optional)
- freeText
- requiredGeneralCount
- electiveGeneralCount
```

### 백엔드 API

```text
POST /recommend
```

요청 예시:

```json
{
  "session_id": "session-id",
  "required_general_count": 1,
  "elective_general_count": 1,
  "selected_preferences": {
    "no_morning_classes": {
      "enabled": true,
      "morning_end_time": "12:00"
    },
    "required_free_days": ["FRI"],
    "prefer_free_days": [],
    "max_consecutive_classes": 2,
    "excluded_time_range": null,
    "prefer_late_start": false,
    "compact_schedule": true,
    "minimize_attendance_days": true,
    "minimize_consecutive_classes": false
  },
  "free_text": "월요일 수업은 가능하면 적었으면 좋겠어요."
}
```

백엔드 모델이 확정되기 전에는 프론트 내부 타입과 API DTO를 분리한다. 실제 필드명은 최종 API 계약에 맞춰 교체한다.

선택하지 않은 카드의 값이 이전 상태로 남아 전송되지 않도록, 카드 해제 시 관련 세부 상태를 초기화한다.


## 3.7. TimetableResultScreen — 최종 추천 시간표

### 목적

추천 시간표 후보를 시간표 형태로 보여주고, 각 후보가 어떤 필수 조건을 만족했으며 어떤 선호 기준으로 순위가 결정되었는지 설명한다.

### UI 구성

```text
[추천 시간표]

[후보 1] [후보 2] [후보 3]

후보 1
선호 적합도 점수 92점

필수 조건
✓ 금요일 공강
✓ 최대 연속 수업 2개 이하
✓ 이동 불가능한 연강 없음

점수 계산 내역
+8 금요일 공강 선호 만족
+4 수업 사이 총 빈 시간 40분
-4 오전 수업 1개 포함
-3 연강 구간 1개 포함

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

### 선호 적합도 점수 표시

`추천 점수` 대신 다음 표현 중 하나를 사용한다.

```text
- 선호 적합도 점수
- 선호 반영 점수
```

표시 규칙:

```text
- 총점만 표시하지 않고 점수 계산 내역을 함께 제공한다.
- 양수 점수는 + 기호를 표시한다.
- 음수 점수는 - 기호를 표시한다.
- 0점 항목은 필요하지 않으면 숨긴다.
- 하드 조건 만족 내역은 점수 계산과 분리해 표시한다.
- 점수가 100을 넘거나 음수가 되더라도 원래 값을 그대로 표시한다.
- 진행률 막대나 100점 만점처럼 보이는 UI를 사용하지 않는다.
```

### 필수 조건 만족 내역

하드 조건은 점수와 분리하여 체크 목록으로 표시한다.

```text
필수 조건
✓ 금요일 공강
✓ 최대 연속 수업 2개 이하
✓ 이동 불가능한 연강 없음
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

### 결과 화면 상호작용

- 후보 탭을 변경해도 현재 스크롤 위치와 선택 후보 상태를 예측 가능하게 유지한다.
- 기본 선택 후보는 rank가 가장 높은 후보로 한다.
- 각 후보에서 총 학점, 등교일 수, 첫 수업 시간, 마지막 수업 시간 등 핵심 요약을 함께 표시한다.
- 하드 조건 충족 내역과 점수 계산 내역은 별도 섹션으로 구분한다.
- 0점인 점수 항목은 기본적으로 숨길 수 있다.
- 점수는 100점 범위로 제한하거나 진행률 막대로 표현하지 않는다.
- 조건을 수정하면 전공 선택은 유지하고 추천 결과만 다시 요청한다.
- 전공을 다시 선택하면 기존 추천 결과는 초기화한다.


## 4. Flutter 파일 구조

```text
lib/
 ├─ main.dart
 │
 ├─ models/
 │   ├─ department.dart
 │   ├─ course.dart
 │   ├─ class_time.dart
 │   ├─ schedule_preference.dart
 │   ├─ timetable_recommendation.dart
 │   ├─ preference_score_detail.dart
 │   └─ warning_message.dart
 │
 ├─ dto/
 │   ├─ department_dto.dart
 │   ├─ catalog_parse_response_dto.dart
 │   ├─ major_confirm_request_dto.dart
 │   ├─ recommendation_request_dto.dart
 │   └─ recommendation_response_dto.dart
 │
 ├─ services/
 │   ├─ api_client.dart
 │   ├─ department_api.dart
 │   ├─ catalog_api.dart
 │   ├─ major_api.dart
 │   └─ recommend_api.dart
 │
 ├─ repositories/
 │   ├─ department_repository.dart
 │   ├─ catalog_repository.dart
 │   ├─ major_repository.dart
 │   └─ recommendation_repository.dart
 │
 ├─ screens/
 │   ├─ guide_screen.dart
 │   ├─ department_select_screen.dart
 │   ├─ file_upload_screen.dart
 │   ├─ catalog_preview_screen.dart
 │   ├─ major_select_screen.dart
 │   ├─ general_preference_screen.dart
 │   └─ timetable_result_screen.dart
 │
 ├─ widgets/
 │   ├─ screen_header.dart
 │   ├─ step_progress_bar.dart
 │   ├─ primary_action_button.dart
 │   ├─ secondary_action_button.dart
 │   ├─ bottom_action_area.dart
 │   ├─ file_picker_card.dart
 │   ├─ course_group_card.dart
 │   ├─ course_option_tile.dart
 │   ├─ selected_course_summary.dart
 │   ├─ preference_section.dart
 │   ├─ preference_select_card.dart
 │   ├─ preference_detail_panel.dart
 │   ├─ weekday_selector.dart
 │   ├─ timetable_grid.dart
 │   ├─ recommendation_tabs.dart
 │   ├─ hard_constraint_summary.dart
 │   ├─ score_breakdown_card.dart
 │   ├─ loading_overlay.dart
 │   ├─ empty_state_view.dart
 │   ├─ error_state_view.dart
 │   └─ warning_banner.dart
 │
 ├─ state/
 │   ├─ planu_flow_state.dart
 │   └─ planu_flow_controller.dart
 │
 └─ utils/
     ├─ course_conflict_checker.dart
     ├─ request_state.dart
     └─ input_normalizer.dart
```

### 구조 원칙

```text
Screen
↓
Flow Controller
↓
Repository
↓
API Service
↓
Server
```

- `screen`은 화면 렌더링과 사용자 이벤트 전달을 담당한다.
- `controller`는 흐름 상태 변경과 검증, 파생 상태 초기화를 담당한다.
- `repository`는 API 응답을 앱 모델로 변환하고 데이터 접근 방식을 캡슐화한다.
- `service`는 HTTP 요청, 직렬화, 공통 오류 변환을 담당한다.
- `dto`는 서버 계약을 표현하며 화면에서 직접 사용하지 않는다.
- `model`은 앱 내부에서 사용하는 안정적인 데이터 구조다.
- 단일 화면 파일에 API 호출, 변환, 상태 변경, 대형 하위 위젯을 함께 두지 않는다.

---

## 5. 파일별 역할

## 5.1. `main.dart`

앱 진입점이다.

```text
- MaterialApp 생성
- 라우트 또는 Router 설정
- 초기 화면 GuideScreen 지정
- PlanuFlowState 및 PlanuFlowController 주입
- 공통 네트워크 오류 처리 진입점 연결
```

초기 화면은 반드시 `GuideScreen`으로 한다.

## 5.2. models

### `department.dart`

```text
- id
- name
- collegeName(optional)
```

### `course.dart`

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

```text
- day
- start
- end
- classroom
- buildingCode
```

### `schedule_preference.dart`

구조화된 하드 조건과 소프트 선호를 앱 내부 모델로 표현한다.

```text
- noMorningClasses
- requiredFreeDays
- preferredFreeDays
- maxConsecutiveClasses
- excludedTimeRange
- preferLateStart
- compactSchedule
- relaxedSchedule
- minimizeAttendanceDays
- minimizeConsecutiveClasses
```

상충되는 상태를 동시에 보관하지 않도록 불변 객체와 `copyWith` 사용을 권장한다.

### `timetable_recommendation.dart`

```text
- rank
- preferenceScore
- totalCredit
- courses
- scheduleItems
- hardConstraintResults
- scoreBreakdown
- reasons
- warnings
```

### `preference_score_detail.dart`

```text
- value
- reason
- type
```

`value`는 양수, 음수, 0을 모두 허용한다.

### `warning_message.dart`

```text
- type
- message
- fromCourse
- toCourse
```

## 5.3. dto

DTO는 서버 요청·응답 필드에 맞춰 정의한다. UI와 상태 객체가 DTO에 직접 의존하지 않도록 Repository에서 변환한다.

### `recommendation_request_dto.dart`

```text
- sessionId
- requiredGeneralCount
- electiveGeneralCount
- selectedPreferences
- freeText
```

선택하지 않은 조건은 서버 계약에 따라 생략하거나 `null`로 전송한다. 비활성 카드의 이전 세부값은 전송하지 않는다.

## 5.4. services

### `api_client.dart`

```text
- baseUrl 관리
- 공통 header 설정
- 타임아웃 처리
- JSON 및 multipart 요청
- 서버 오류를 공통 예외로 변환
- 중복 요청 방지를 위한 요청 식별 지원
```

### API 서비스

```text
department_api.dart  → GET /departments
catalog_api.dart     → POST /catalog/parse
major_api.dart       → POST /major/confirm
recommend_api.dart   → POST /recommend
```

서비스는 UI 문구를 결정하지 않는다.

## 5.5. repositories

Repository는 API Service와 앱 내부 모델 사이의 경계를 담당한다.

```text
DepartmentRepository
- 검색어 기반 학과 조회
- DepartmentDto → Department 변환

CatalogRepository
- 파일 업로드
- 파싱 응답 변환

MajorRepository
- 선택 전공 확정
- 서버 검증 오류 변환

RecommendationRepository
- 구조화 조건과 자유 입력 전송
- 추천 결과와 점수 근거 변환
```

화면은 `ApiClient`나 개별 API 클래스를 직접 호출하지 않는다.

## 5.6. screens

각 화면은 다음 공통 규칙을 따른다.

```text
- 상태를 읽어 UI를 렌더링
- 사용자 이벤트를 Controller에 전달
- 요청 성공·실패에 따른 이동 또는 메시지 표시
- 복잡한 데이터 변환과 시간 충돌 계산을 직접 수행하지 않음
```

### `guide_screen.dart`

수강편람 준비 방법과 필요한 파일 종류를 안내한다.

### `department_select_screen.dart`

학과 자동완성 선택과 유효 선택 검증을 담당한다.

### `file_upload_screen.dart`

전공 필수 파일과 선택 교양 파일을 관리하고 분석 요청을 시작한다.

### `catalog_preview_screen.dart`

파싱 결과의 요약과 재업로드 경로를 제공한다.

### `major_select_screen.dart`

과목별 분반 선택, 실시간 충돌 안내, 선택 요약을 제공한다.

### `general_preference_screen.dart`

하드 조건, 소프트 선호, 자유 입력을 분리해 관리한다.

### `timetable_result_screen.dart`

후보 비교, 시간표, 필수 조건 충족 결과, 점수 근거, 경고를 표시한다.

## 5.7. widgets

### 공통 흐름 위젯

```text
screen_header.dart
step_progress_bar.dart
bottom_action_area.dart
primary_action_button.dart
secondary_action_button.dart
```

화면마다 동일한 버튼 높이, 로딩 상태, 비활성화 규칙을 재사용한다.

### 입력 및 선택 위젯

```text
file_picker_card.dart
course_group_card.dart
course_option_tile.dart
selected_course_summary.dart
preference_section.dart
preference_select_card.dart
preference_detail_panel.dart
weekday_selector.dart
```

### 결과 및 상태 위젯

```text
timetable_grid.dart
recommendation_tabs.dart
hard_constraint_summary.dart
score_breakdown_card.dart
loading_overlay.dart
empty_state_view.dart
error_state_view.dart
warning_banner.dart
```

## 5.8. state

### `planu_flow_state.dart`

화면 간 공유되는 데이터와 요청 상태를 보관한다.

```text
- currentStep
- selectedDepartment
- sessionId
- majorCatalogFile
- electiveCatalogFile
- majorCandidates
- selectedMajorCourses
- requiredGeneralCount
- electiveGeneralCount
- selectedPreferences
- freeText
- recommendations
- selectedRecommendationIndex
- departmentRequestState
- catalogParseRequestState
- majorConfirmRequestState
- recommendationRequestState
```

### `planu_flow_controller.dart`

```text
- 학과 선택 및 변경
- 파일 선택·삭제
- 수강편람 분석 요청
- 전공 선택과 충돌 검증
- 선호 조건 선택 및 충돌 처리
- 추천 요청
- 이전 단계 변경 시 하위 상태 초기화
- 재시도 처리
```

MVP에서는 `ChangeNotifier` 기반 구현으로 충분하다. 새 상태관리 패키지를 추가하는 것은 필수가 아니다.

---

## 6. 프론트 상태 흐름

```text
앱 시작
↓
GuideScreen
↓
DepartmentSelectScreen
  - selectedDepartment 저장
  - 학과 변경 시 이후 데이터 초기화
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
  - 선택 즉시 충돌 계산
  - /major/confirm 호출
↓
GeneralPreferenceScreen
  - selectedPreferences 저장
  - freeText 저장
  - /recommend 호출
↓
TimetableResultScreen
  - recommendations 표시
  - selectedRecommendationIndex 저장
```

### 파생 상태 초기화 규칙

| 변경된 데이터 | 초기화할 데이터 |
|---|---|
| 학과 | 파일, 세션, 전공 후보, 전공 선택, 추천 조건, 추천 결과 |
| 전공 파일 | 세션, 전공 후보, 전공 선택, 추천 결과 |
| 교양 파일 | 세션, 추천 결과 |
| 전공 선택 | 추천 결과 |
| 추천 조건 또는 자유 입력 | 추천 결과 |

### 요청 상태

각 비동기 요청은 다음 상태를 가진다.

```text
idle
loading
success
empty
failure
```

오류 메시지 문자열만 상태에 저장하지 않고 오류 유형과 재시도 가능 여부를 함께 저장한다.

### 화면 복귀 규칙

- 결과에서 조건 화면으로 돌아가면 전공 선택과 파일은 유지한다.
- 결과에서 전공 화면으로 돌아가 전공을 변경하면 추천 결과만 무효화한다.
- 파일 화면으로 돌아가 파일을 변경하면 세션 이후 데이터는 모두 무효화한다.
- 앱 프로세스가 유지되는 동안 입력값은 화면 이동으로 사라지지 않는다.

---

## 7. 백엔드 API 연결

| 화면 | Repository | API |
|---|---|---|
| DepartmentSelectScreen | DepartmentRepository | `GET /departments` |
| FileUploadScreen | CatalogRepository | `POST /catalog/parse` |
| MajorSelectScreen | MajorRepository | `POST /major/confirm` |
| GeneralPreferenceScreen | RecommendationRepository | `POST /recommend` |
| TimetableResultScreen | 없음 | 저장된 추천 결과 표시 |

### API 연결 원칙

```text
Screen → Controller → Repository → API Service → Server
```

- Screen은 HTTP 상태코드나 JSON 필드명을 해석하지 않는다.
- Repository는 DTO를 앱 모델로 변환한다.
- Controller는 성공 시 상태를 갱신하고 다음 화면 이동 가능 여부를 결정한다.
- API 오류는 공통 오류 유형으로 변환한다.
- 모든 요청에 타임아웃과 중복 제출 방지를 적용한다.
- 세션 만료 응답을 받으면 파일 업로드 단계로 복귀할 수 있는 행동을 제공한다.

### `/recommend` 요청 예시

```json
{
  "session_id": "session-id",
  "required_general_count": 1,
  "elective_general_count": 1,
  "selected_preferences": {
    "no_morning_classes": {
      "enabled": true,
      "morning_end_time": "12:00"
    },
    "required_free_days": ["FRI"],
    "prefer_free_days": [],
    "max_consecutive_classes": 2,
    "excluded_time_range": null,
    "prefer_late_start": false,
    "compact_schedule": true,
    "relaxed_schedule": false,
    "minimize_attendance_days": true,
    "minimize_consecutive_classes": false
  },
  "free_text": "월요일 수업은 가능하면 적었으면 좋겠어요."
}
```

### `/recommend` 응답에 필요한 정보

```text
- rank
- preference_score
- total_credit
- courses
- schedule_items
- hard_constraint_results
- score_breakdown
- reasons
- warnings
```

API 필드가 확정되기 전에는 DTO를 별도 파일에 두어 실제 계약 변경이 화면과 앱 모델에 직접 전파되지 않게 한다.

---

## 8. 에러·빈 상태 처리 UI

오류 화면에는 가능한 경우 다음 네 요소를 제공한다.

```text
무엇이 잘못되었는지
사용자가 확인할 내용
다시 시도할 수 있는 행동
이전 단계로 돌아가는 행동
```

### 8.1. 파일 형식 오류

```text
수강편람 형식을 인식하지 못했습니다.
학생지원시스템에서 다운로드한 .xlsx 파일인지 확인해주세요.

[파일 다시 선택]
```

### 8.2. 파일 업로드 실패

```text
파일을 업로드하지 못했습니다.
네트워크 연결을 확인한 뒤 다시 시도해주세요.

[다시 시도] [파일 변경]
```

선택한 로컬 파일 정보는 유지한다.

### 8.3. 전공 후보 0개

```text
전공 과목을 찾지 못했습니다.
1학년 전공기초/전공필수 수강편람 파일인지 확인해주세요.

[파일 다시 선택]
```

### 8.4. 전공 시간 충돌

```text
선택한 전공 과목끼리 시간이 겹칩니다.
충돌하는 분반을 변경해주세요.
```

충돌 과목명을 함께 표시하고 확정 버튼을 비활성화한다.

### 8.5. 조건 충돌

```text
'몰아서 듣기'와 '여유 있게 듣기'는 함께 선택할 수 없습니다.
기존 선택을 해제하고 새 선택을 적용했습니다.
```

동일 요일이 공강 필수와 공강 선호에 모두 들어가면 필수 조건만 유지한다.

### 8.6. 네트워크 오류 또는 시간 초과

```text
서버와 연결하지 못했습니다.
잠시 후 다시 시도해주세요.

[다시 시도]
```

재시도 시 사용자가 입력한 값은 유지한다.

### 8.7. 세션 만료

```text
분석 세션이 만료되었습니다.
수강편람 파일을 다시 분석해주세요.

[파일 업로드로 이동]
```

### 8.8. 추천 결과 없음

```text
현재 조건을 모두 만족하는 시간표를 찾지 못했습니다.
필수 조건을 줄이거나 교양 개수를 조정해보세요.

[조건 수정]
```

서버가 완화 가능한 조건을 제공하면 구체적인 제안을 함께 표시한다.

### 8.9. 예상하지 못한 오류

```text
일시적인 문제가 발생했습니다.
입력한 내용은 유지됩니다.

[다시 시도] [이전 단계]
```

내부 예외 내용이나 서버 스택 정보는 사용자에게 노출하지 않는다.

---

## 9. 로딩 및 비동기 UX

작업별로 현재 수행 중인 단계를 명확하게 표시한다.

```text
학과 목록을 불러오고 있어요.
수강편람을 업로드하고 있어요.
수강편람을 분석하고 있어요.
전공 과목 목록을 정리하고 있어요.
선택한 전공 시간표를 확인하고 있어요.
교양 조건을 정리하고 있어요.
시간표 후보를 만들고 있어요.
연강 이동 가능성을 확인하고 있어요.
추천 결과를 정리하고 있어요.
```

### 로딩 처리 규칙

- 1초 미만의 짧은 작업에는 불필요한 전체 화면 로딩 전환을 피한다.
- 파일 분석과 추천 생성처럼 긴 작업은 진행 중인 단계와 취소 불가 여부를 설명한다.
- 요청 중 실행 버튼에는 로딩 상태를 표시하고 중복 클릭을 막는다.
- 로딩 중에도 현재 입력 내용을 가능한 한 화면에 유지한다.
- 실패 후 재시도할 때 전체 흐름을 처음부터 다시 시작하게 하지 않는다.
- 로딩 문구가 실제 백엔드 처리 단계와 다를 경우 단정적인 가짜 진행률을 사용하지 않는다.
- 시간 기반 퍼센트 진행률은 실제 진행 데이터가 있을 때만 표시한다.

---

## 10. 결과 화면 신뢰 문구

추천 결과 화면 하단에 다음 문구를 표시한다.

```text
PlaNU는 수강편람 기반으로 시간표 후보를 추천합니다.
실제 수강 가능 여부, 정원, 폐강 여부는 수강신청 시점의 학생지원시스템에서 반드시 확인해주세요.
```

---

## 11. 접근성 기준

### 공통 기준

- 모든 주요 터치 영역은 최소 48dp를 확보한다.
- 색상만으로 선택, 오류, 과목 유형, 점수 증감을 구분하지 않는다.
- 텍스트와 아이콘 또는 라벨을 함께 사용한다.
- 본문과 배경의 명도 대비를 충분히 확보한다.
- 시스템 글자 크기가 커져도 주요 버튼과 설명이 잘리지 않게 한다.
- 스크린 리더가 화면 제목, 현재 단계, 선택 상태, 오류를 읽을 수 있게 한다.
- 키보드와 보조 입력 장치로 포커스 이동과 선택이 가능하도록 한다.

### 선택 카드

```dart
Semantics(
  button: true,
  checked: isSelected,
  label: title,
  hint: description,
  child: ...
)
```

실제 `Checkbox`를 시각적으로 포함하거나 동일한 의미를 제공하는 접근성 상태를 지정한다.

### 시간표

시간표 그리드만 제공하지 않고 동일한 정보를 읽을 수 있는 과목 목록을 함께 제공한다.

```text
월요일 09:00~10:15
컴퓨터프로그래밍 001분반
제6공학관
```

### 오류 및 로딩 알림

- 오류 발생 시 포커스를 오류 요약 또는 첫 오류 항목으로 이동한다.
- 로딩 시작과 완료 상태가 스크린 리더에 전달되도록 한다.
- 필드 오류는 해당 필드 주변에 텍스트로 표시한다.

---

## 12. 테스트 및 완료 기준

### 핵심 Widget 테스트

```text
1. 학과를 선택하지 않으면 다음 버튼 비활성화
2. 목록에 없는 텍스트만 입력하면 진행 불가
3. 전공 파일이 없으면 분석 버튼 비활성화
4. 같은 과목의 분반은 하나만 선택 가능
5. 전공 시간 충돌 시 확정 불가
6. 선호 카드 여러 개 동시 선택 가능
7. 카드 해제 시 세부 설정 초기화
8. 상충되는 스타일 선택 처리
9. 필수 공강과 선호 공강의 같은 요일 중복 정리
10. 점수의 양수·음수 기호 표시
11. API 실패 후 입력값 유지 및 재시도 가능
12. 세션 만료 시 파일 업로드 단계 이동
```

### 핵심 통합 테스트

```text
Guide
→ 학과 선택
→ 파일 업로드
→ 분석 결과 확인
→ 전공 선택
→ 선호 조건 입력
→ 추천 결과 확인
```

### 화면 완료 기준

각 화면은 다음 항목을 충족해야 완료로 본다.

```text
- 정상 상태 구현
- 로딩 상태 구현
- 빈 상태 또는 입력 없음 상태 구현
- 오류 상태 구현
- 이전·다음 이동 구현
- 상태 보존 확인
- 접근성 라벨 확인
- 주요 Widget 테스트 통과
```

---

## 13. 구현 우선순위

### P0 — 전체 시연 흐름 완성

```text
- 전체 라우팅
- GuideScreen
- FileUploadScreen
- CatalogPreviewScreen
- MajorSelectScreen
- GeneralPreferenceScreen
- TimetableResultScreen
- 후보별 점수 근거
- 오류 및 로딩 기본 상태
```

### P1 — 실제 백엔드 통합

```text
- Repository 계층
- 실제 학과 검색
- multipart 파일 업로드
- 전공 확정 API
- 추천 API
- 세션 만료와 오류 코드 처리
```

### P2 — 품질 보강

```text
- 공통 위젯 정리
- 접근성 검증
- Widget 및 통합 테스트
- 긴 목록 성능 최적화
- 사용자 안내 문구 보정
```

한 화면의 세부 시각 요소를 반복 수정하기보다 P0 전체 흐름을 먼저 완성한다.

---

## 14. 최종 프론트 흐름 요약

```text
1. 수강편람 다운로드 방법을 안내한다.
2. 사용자가 학과를 자동완성 목록에서 선택한다.
3. 전공 수강편람 파일을 필수로 업로드한다.
4. 선택적으로 교양선택 수강편람 파일을 업로드한다.
5. 업로드한 파일의 파싱 결과를 확인한다.
6. 전공 과목/분반은 사용자가 직접 선택한다.
7. 선택된 전공 시간표를 서버에 확정한다.
8. 교양 하드 조건, 소프트 선호, 추가 요청을 구분해 입력한다.
9. 구조화된 조건과 자유 입력을 분리해 서버로 전달한다.
10. 서버가 교양 시간표 후보를 추천한다.
11. 후보 1~3을 시간표와 점수 근거 형태로 보여준다.
```

---

## 15. 한 줄 요약

PlaNU 프론트엔드는 사용자가 부산대 수강편람 파일을 준비하고 전공 과목은 직접 선택하며, 교양 조건은 구조화된 하드 조건·소프트 선호·추가 요청으로 입력해 추천 시간표와 선호 적합도 근거를 확인할 수 있도록 단계형 화면 흐름을 제공한다. 전공 선택은 직접 선택 방식으로 처리하고, LLM은 교양 조건과 추가 요청 해석에만 사용한다.
