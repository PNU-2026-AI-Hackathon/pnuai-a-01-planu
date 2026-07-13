# PlaNU 백엔드 설계 최종 수정판

> 이 문서는 PlaNU MVP의 백엔드 구조를 정리한 문서이다. 최신 결정 사항을 반영하여 **전공 과목 선택에는 LLM을 사용하지 않고**, 사용자가 업로드한 전공 수강편람을 바탕으로 직접 과목/분반을 선택하는 구조로 수정하였다. LLM은 **교양 추천 조건 해석**에만 사용한다.

---

## 1. 프로젝트 핵심 방향

PlaNU는 부산대학교 1학년 신입생/편입생을 대상으로 한 수강신청 도우미이다.

MVP의 핵심 목표는 다음과 같다.

```text
사용자가 전공 수강편람을 업로드한다.
→ 전공 과목/분반은 사용자가 직접 선택한다.
→ 선택된 전공 시간표를 고정한다.
→ PlaNU가 교양 필수/교양 선택 과목을 추천한다.
→ 시간 충돌, 수강 제한, 연강 이동 가능성을 검사한다.
→ 상위 3개의 시간표 후보를 반환한다.
```

전공 과목은 교수 선호도, 강의 난이도, 에브리타임 평점 등 공식 데이터 밖의 요소가 중요하므로 서버가 자동 추천하지 않는다. 대신 사용자가 직접 선택하고, 서버는 시간 충돌 여부만 검증한다.

교양 과목은 수강 제한, 분반, 시간, 강의실 이동 가능성 등을 기준으로 서버가 추천한다.

---

## 2. 전체 백엔드 디렉토리 구조

```text
backend/
 ├─ app/
 │   ├─ main.py
 │   ├─ startup.py
 │   ├─ config.py
 │   ├─ deps.py
 │   │
 │   ├─ routes/
 │   │   ├─ departments.py
 │   │   ├─ catalog.py
 │   │   ├─ major.py
 │   │   └─ recommend.py
 │   │
 │   ├─ schemas/
 │   │   ├─ catalog_schema.py
 │   │   ├─ major_schema.py
 │   │   └─ recommend_schema.py
 │   │
 │   ├─ models/
 │   │   ├─ course.py
 │   │   ├─ input_timetable.py
 │   │   ├─ timetable.py
 │   │   └─ preference.py
 │   │
 │   ├─ services/
 │   │   ├─ course_parser.py
 │   │   ├─ uploaded_catalog_parser.py
 │   │   ├─ course_loader.py
 │   │   ├─ department_service.py
 │   │   ├─ session_store.py
 │   │   ├─ course_filter.py
 │   │   ├─ llm_preference_parser.py
 │   │   ├─ campus_rule_engine.py
 │   │   ├─ timetable_validator.py
 │   │   ├─ timetable_generator.py
 │   │   └─ timetable_ranker.py
 │   │
 │   └─ core/
 │       ├─ errors.py
 │       ├─ timeutil.py
 │       └─ logging.py
 │
 ├─ data/
 │   ├─ raw/
 │   │   ├─ general_required.xlsx
 │   │   ├─ general_elective_area_1.xlsx
 │   │   ├─ general_elective_area_2.xlsx
 │   │   ├─ general_elective_area_3.xlsx
 │   │   ├─ general_elective_area_4.xlsx
 │   │   ├─ general_elective_area_5.xlsx
 │   │   ├─ general_elective_area_6.xlsx
 │   │   ├─ general_elective_area_7.xlsx
 │   │   └─ course_restriction_rules.xlsx
 │   │
 │   ├─ processed/
 │   │   ├─ general_required_courses.json
 │   │   ├─ general_elective_courses.json
 │   │   ├─ course_restrictions.json
 │   │   └─ department_list.json
 │   │
 │   └─ rules/
 │       ├─ campus_rules.json
 │       └─ department_alias.json
 │
 └─ uploads/
     └─ temp/
```

---

## 3. 데이터 디렉토리 역할

### 3.1. `data/raw/`

학교 홈페이지에서 다운로드한 원본 엑셀 파일을 저장한다.

```text
general_required.xlsx
- 교양 필수 수강편람

general_elective_area_1.xlsx ~ general_elective_area_7.xlsx
- 교양 선택 1~7영역 수강편람
- 사용자가 교양선택 파일을 업로드하지 않았을 때 기본 데이터로 사용

course_restriction_rules.xlsx
- 수강신청 제한 교과목 현황
- 학과별 수강 가능/불가능 여부 판단
- 학과 자동완성 목록 생성에 활용
```

### 3.2. `data/processed/`

서버가 사용하기 쉽게 변환된 JSON 파일을 저장한다.

```text
general_required_courses.json
- 정규화된 교양 필수 과목 데이터

general_elective_courses.json
- 교양 선택 1~7영역 통합 데이터

course_restrictions.json
- 수강 제한 규칙 데이터

department_list.json
- 프론트 학과 자동완성에 사용하는 학과 목록
```

### 3.3. `data/rules/`

개발자가 직접 관리하는 규칙 데이터를 저장한다.

```text
campus_rules.json
- 부산대 건물 구역 기반 연강 이동 가능성 규칙

department_alias.json
- 학과명 표기 보정용 선택 규칙
- MVP에서는 비워두고, 문제가 생기는 학과만 추가한다.
```

---

## 4. 서버 시작 시 흐름

서버 시작 시 엑셀을 매번 요청마다 읽지 않고, 필요한 데이터를 미리 준비한다.

```text
서버 시작
→ raw 엑셀 파일 확인
→ 필요하면 processed JSON 생성/갱신
→ processed JSON 로딩
→ campus_rules.json 로딩
→ department_list 로딩
→ 메모리에 저장
→ API 요청 대기
```

담당 파일:

```text
startup.py
- 서버 시작 시 전체 초기화 흐름 담당

course_parser.py
- data/raw의 학교 기본 엑셀 파일을 파싱하여 data/processed JSON 생성

course_loader.py
- data/processed와 data/rules의 JSON 파일을 메모리에 로딩
```

---

## 5. 주요 데이터 모델

### 5.1. Course

```text
Course
- course_id
- course_name
- category
- area
- credit
- division
- professor
- class_times
```

### 5.2. Category enum

백엔드 내부에서는 자유 문자열 대신 enum을 사용한다.

```text
MAJOR_BASIC
MAJOR_REQUIRED
GENERAL_REQUIRED
GENERAL_ELECTIVE
```

프론트 표시용 한글은 별도로 매핑한다.

```text
MAJOR_BASIC       → 전공기초
MAJOR_REQUIRED    → 전공필수
GENERAL_REQUIRED  → 교양필수
GENERAL_ELECTIVE  → 교양선택
```

### 5.3. ClassTime

```text
ClassTime
- day
- start
- end
- classroom
- building_code
```

`classroom`은 과목 최상위 필드가 아니라 `class_times` 내부에만 둔다. 요일별 강의실이 다를 수 있기 때문이다.

### 5.4. Day enum

```text
MON
TUE
WED
THU
FRI
```

### 5.5. InputTimetable

사용자가 직접 선택한 고정 전공 시간표는 추천 결과용 `Timetable`과 분리하여 검증한다.

```text
InputTimetable
- courses
- total_credit
- schedule_items
```

담당 파일:

```text
models/input_timetable.py
```

검증 및 생성 규칙:

```text
- course_id 중복 금지
- Course.conflicts_with를 이용한 입력 전공 과목 간 시간 충돌 검사
- total_credit 미입력 시 courses의 학점 합으로 자동 계산
- 입력된 total_credit과 실제 학점 합이 다르면 거부
- schedule_items 미입력 시 class_times를 바탕으로 자동 생성 및 정렬
```

추천 결과용 `Timetable`은 백트래킹 생성 과정의 후보를 표현하므로 모델 자체에서 시간 충돌을 검사하지 않는다. 추천 후보의 충돌 검사는 `timetable_validator.py`가 담당한다.

### 5.6. 내부 시간 표현

API 응답에서는 `"09:00"` 형식을 사용한다. 서버 내부 비교에서는 분 단위 정수로 변환한다.

```text
"09:00" → 540
"10:15" → 615
```

담당 파일:

```text
core/timeutil.py
```

---

## 6. 사용자 업로드 파일 처리

MVP에서 사용자가 업로드하는 파일은 다음과 같다.

```text
필수:
- 1학년 전공기초/전공필수 수강편람 파일

선택:
- 교양선택 수강편람 파일
```

교양선택 파일을 업로드하지 않으면 서버가 기본으로 보유한 `general_elective_courses.json`을 사용한다.

### 6.1. 업로드 파일 파싱

담당 파일:

```text
uploaded_catalog_parser.py
```

역할:

```text
사용자 전공 수강편람
→ major_candidates 추출

사용자 교양선택 수강편람
→ elective_candidates 추출
```

### 6.2. 업로드 보안 정책

```text
허용 확장자: .xlsx
최대 크기: 파일당 5MB
파일명: 서버에서 UUID로 재명명
저장 위치: uploads/temp/{session_id}/
삭제 정책: 파싱 직후 삭제 또는 세션 만료 시 삭제
```

사용자 파일명은 신뢰하지 않는다.

---

## 7. 세션 기반 상태 관리

MVP에서는 DB 없이 서버 메모리 기반 세션을 사용한다.

담당 파일:

```text
session_store.py
```

### 7.1. SessionData

```text
SessionData
- session_id
- department
- major_candidates
- elective_candidates
- fixed_courses
- created_at
- updated_at
```

### 7.2. 세션 흐름

```text
POST /catalog/parse
→ session_id 발급
→ major_candidates, elective_candidates 저장

POST /major/confirm
→ 사용자가 선택한 전공 과목을 fixed_courses로 저장

POST /recommend
→ session_id로 fixed_courses와 elective_candidates 조회
→ 교양 추천 수행
```

세션 TTL은 기본 30분으로 둔다.

---

## 8. API 계층

### 8.1. 엔드포인트 목록

| Method | Path                    | 역할                           |
| ------ | ----------------------- | ------------------------------ |
| GET    | `/departments?keyword=` | 학과 자동완성 목록 조회        |
| POST   | `/catalog/parse`        | 업로드 파일 파싱, 세션 생성    |
| POST   | `/major/confirm`        | 사용자가 선택한 전공 과목 확정 |
| POST   | `/recommend`            | 교양 시간표 추천               |
| GET    | `/health`               | 서버 상태 확인                 |

기존에 논의했던 `/major/preview`는 제거한다. 전공 선택에는 LLM을 사용하지 않고 사용자가 직접 과목/분반을 선택하기 때문이다.

---

## 9. API 흐름

### 9.1. 학과 목록 조회

```text
GET /departments?keyword=컴퓨터
```

응답 예시:

```json
{
  "departments": ["정보컴퓨터공학부", "컴퓨터공학전공", "전기컴퓨터공학부"]
}
```

학과는 자유 입력이 아니라, 서버가 제공한 목록에서 선택해야 한다.

### 9.2. 수강편람 파싱

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

응답 예시:

```json
{
  "session_id": "b3b7b477-24b5-4f4d-8a0e-9d5b9f0a1a12",
  "major_candidates": [
    {
      "course_id": "MAJ001-001",
      "course_name": "컴퓨터프로그래밍",
      "category": "MAJOR_BASIC",
      "credit": 3,
      "division": "001",
      "professor": "김OO",
      "class_times": [
        {
          "day": "MON",
          "start": "09:00",
          "end": "10:15",
          "classroom": "제6공학관 6201",
          "building_code": "6201"
        }
      ]
    }
  ],
  "elective_candidates_count": 42
}
```

프론트는 `major_candidates`를 과목별로 묶어서 보여주고, 사용자가 전공 분반을 직접 선택하게 한다.

### 9.3. 전공 시간표 확정

```text
POST /major/confirm
```

요청 예시:

```json
{
  "session_id": "b3b7b477-24b5-4f4d-8a0e-9d5b9f0a1a12",
  "fixed_courses": [
    {
      "course_id": "MAJ001-001",
      "course_name": "컴퓨터프로그래밍",
      "category": "MAJOR_BASIC",
      "credit": 3,
      "division": "001",
      "professor": "김OO",
      "class_times": [
        {
          "day": "MON",
          "start": "09:00",
          "end": "10:15",
          "classroom": "제6공학관 6201",
          "building_code": "6201"
        }
      ]
    }
  ]
}
```

서버 처리:

```text
1. session_id 검증
2. fixed_courses가 major_candidates에서 나온 값인지 검증
3. 같은 과목에서 여러 분반을 선택했는지 검사
4. InputTimetable로 course_id 중복, 전공끼리 시간 충돌, 총학점 검사
5. 통과하면 세션에 fixed_courses 저장
```

응답 예시:

```json
{
  "session_id": "b3b7b477-24b5-4f4d-8a0e-9d5b9f0a1a12",
  "confirmed": true,
  "fixed_courses_count": 3
}
```

### 9.4. 교양 추천

```text
POST /recommend
```

요청 예시:

```json
{
  "session_id": "b3b7b477-24b5-4f4d-8a0e-9d5b9f0a1a12",
  "required_general_count": 1,
  "elective_general_count": 1,
  "user_prompt": "오전 수업은 가능하면 피하고 싶고, 금요일은 공강이면 좋겠어요."
}
```

서버 처리:

```text
1. session_id로 fixed_courses 조회
2. user_prompt를 LLM으로 PreferenceRules 변환
3. 교양 필수 후보 로딩
4. 교양 선택 후보 결정
   - 사용자 업로드 교양선택 파일이 있으면 세션의 elective_candidates 사용
   - 없으면 서버 기본 general_elective_courses 사용
5. 수강 제한 규칙 적용
6. fixed_courses와 시간 충돌하는 교양 제거
7. 연강 이동 불가능한 조합 제거
8. 교양 조합 생성
9. 점수화 후 상위 3개 반환
```

응답 예시:

```json
{
  "recommendations": [
    {
      "rank": 1,
      "score": 92,
      "total_credit": 18,
      "courses": [
        {
          "course_id": "MAJ001-001",
          "course_name": "컴퓨터프로그래밍",
          "category": "MAJOR_BASIC",
          "division": "001",
          "professor": "김OO",
          "credit": 3
        },
        {
          "course_id": "GEN001-023",
          "course_name": "고전읽기와토론",
          "category": "GENERAL_REQUIRED",
          "division": "023",
          "professor": "박OO",
          "credit": 2
        }
      ],
      "schedule_items": [
        {
          "day": "MON",
          "start": "09:00",
          "end": "10:15",
          "course_name": "컴퓨터프로그래밍",
          "category": "MAJOR_BASIC",
          "division": "001",
          "professor": "김OO",
          "classroom": "제6공학관 6201"
        },
        {
          "day": "TUE",
          "start": "10:30",
          "end": "11:45",
          "course_name": "고전읽기와토론",
          "category": "GENERAL_REQUIRED",
          "division": "023",
          "professor": "박OO",
          "classroom": "인문관 301"
        }
      ],
      "reasons": [
        "전공 수업과 시간 충돌이 없습니다.",
        "금요일 공강 조건을 만족합니다.",
        "연강 이동 위험이 없습니다."
      ],
      "warnings": []
    }
  ]
}
```

`schedule_items`는 다음 기준으로 정렬한다.

```text
1차: MON → TUE → WED → THU → FRI
2차: start 오름차순
```

---

## 10. 서비스 파일 역할

### 10.1. `course_parser.py`

서버 기본 데이터를 생성한다.

```text
data/raw/*.xlsx
→ data/processed/*.json
```

처리 대상:

```text
- 교양 필수 수강편람
- 교양 선택 1~7영역 수강편람
- 수강 제한 교과목 파일
- 학과 목록 생성
```

### 10.2. `uploaded_catalog_parser.py`

사용자 업로드 파일을 파싱한다.

```text
전공 수강편람 파일
→ major_candidates

교양선택 수강편람 파일
→ elective_candidates
```

### 10.3. `course_loader.py`

JSON 파일을 서버 메모리에 로딩한다.

```text
processed JSON
rules JSON
→ Python 객체/list/dict
```

### 10.4. `department_service.py`

학과 자동완성과 검증을 담당한다.

```text
- department_list.json 로딩
- keyword 기반 학과 검색
- 선택된 학과가 유효한지 검증
```

### 10.5. `session_store.py`

MVP용 메모리 세션을 관리한다.

```text
- session 생성
- session 조회
- session 업데이트
- TTL 만료 세션 삭제
```

### 10.6. `llm_preference_parser.py`

교양 조건 프롬프트만 처리한다.

```text
사용자 자연어 교양 조건
→ PreferenceRules JSON
```

LLM은 시간표를 직접 만들지 않는다. LLM은 전공 과목을 선택하지 않는다. LLM은 교양 조건을 구조화된 JSON으로 바꾸는 역할만 한다.

검증 단계:

```text
1. LangChain structured output
2. Pydantic 모델 검증
3. 도메인 검증
4. 실패 시 빈 PreferenceRules로 fallback
```

### 10.7. `course_filter.py`

교양 후보를 1차 필터링한다.

```text
- 학과별 수강 제한 적용
- LLM hard filter 적용
- 전공 시간표와 충돌하는 교양 제거
- 교양 필수/교양 선택 구분
```

### 10.8. `campus_rule_engine.py`

연강 이동 가능성을 판단한다.

```text
- building_code 기반 구역 추출
- campus_rules.json 적용
- 두 수업 사이 이동 가능 여부 반환
```

### 10.9. `timetable_validator.py`

시간표 후보의 유효성을 검사한다.

```text
- 시간 충돌 검사
- 전공 fixed_courses와 충돌 검사
- 연강 이동 가능성 검사
- 총 학점 검사
```

### 10.10. `timetable_generator.py`

가능한 교양 조합을 생성한다.

```text
전공 fixed_courses 고정
→ 교양 필수 N개 선택
→ 교양 선택 M개 선택
→ 유효한 시간표 후보 생성
```

### 10.11. `timetable_ranker.py`

유효한 후보를 점수화하고 정렬한다.

```text
- 공강일 선호 반영
- 오전 수업 회피 반영
- 연강 최소화 반영
- 희망 조건 만족도 반영
- 상위 3개 반환
```

---

## 11. 에러 처리

### 11.1. 표준 에러 응답

```json
{
  "error": {
    "code": "NO_VALID_TIMETABLE",
    "message": "조건을 만족하는 시간표를 찾지 못했습니다.",
    "hint": "오전 회피 조건을 완화해 보세요.",
    "details": {}
  }
}
```

### 11.2. 주요 에러 케이스

| 상황                | code                        | 처리                                |
| ------------------- | --------------------------- | ----------------------------------- |
| 세션 없음/만료      | `SESSION_NOT_FOUND`         | 파일 업로드 단계부터 다시 안내      |
| 전공 파일 형식 오류 | `INVALID_MAJOR_CATALOG`     | 올바른 수강편람 파일 안내           |
| 전공 후보 0개       | `NO_MAJOR_CANDIDATE`        | 파일 확인 요청                      |
| 전공 시간 충돌      | `MAJOR_TIME_CONFLICT`       | 충돌 과목 표시                      |
| LLM 파싱 실패       | `LLM_PARSE_FALLBACK`        | 빈 조건으로 추천 계속, warning 추가 |
| 교양 후보 0개       | `NO_CANDIDATE_AFTER_FILTER` | 조건 완화 안내                      |
| 유효 시간표 0개     | `NO_VALID_TIMETABLE`        | 조건 완화 안내                      |

---

## 12. 핵심 검증 로직

### 12.1. 시간 충돌 검사

같은 요일이고 다음 조건을 만족하면 충돌이다.

```text
a.start < b.end AND b.start < a.end
```

단, `a.end == b.start`는 충돌이 아니다.

### 12.2. 전공 선택 검증

```text
- 선택된 과목이 세션의 major_candidates 안에 존재해야 한다.
- 같은 course_name에서 여러 division을 선택하면 안 된다.
- InputTimetable에서 course_id가 중복되면 안 된다.
- InputTimetable에서 선택한 전공끼리 시간이 겹치면 안 된다.
- InputTimetable의 total_credit은 실제 선택 과목의 학점 합과 같아야 한다.
```

### 12.3. 연강 이동 검사

```text
같은 요일에서 연속된 두 수업을 찾는다.
gap = next.start - prev.end

gap이 짧으면 campus_rule_engine으로 이동 가능 여부를 판단한다.
이동 불가능하면 후보에서 제외한다.
```

---

## 13. 최종 백엔드 흐름 요약

```text
1. 서버 시작
   - 기본 교양 필수/선택 데이터 로딩
   - 제한 교과목 데이터 로딩
   - 학과 목록 로딩
   - 캠퍼스 이동 규칙 로딩

2. 사용자가 학과 선택
   - /departments 사용

3. 사용자가 전공 수강편람 업로드
   - /catalog/parse
   - major_candidates 생성
   - session_id 발급

4. 사용자가 전공 과목/분반 직접 선택
   - /major/confirm
   - fixed_courses 저장

5. 사용자가 교양 조건 입력
   - /recommend
   - LLM이 교양 조건만 JSON으로 변환

6. 서버가 교양 추천
   - 수강 제한 적용
   - 시간 충돌 제거
   - 연강 이동 검사
   - 점수화
   - 상위 3개 반환
```

---

## 14. schemas 파일 역할

schemas/는 FastAPI 요청/응답 스키마를 정의하며, Pydantic을 이용해 사용자 입력의 1차 검증을 담당한다.

- catalog_schema.py
  - /catalog/parse 요청/응답 스키마
  - department 필수 여부
  - elective_area 1~7 범위
  - 교양선택 파일 업로드 시 elective_area 필수 조건

- major_schema.py
  - /major/confirm 요청/응답 스키마
  - session_id 필수 여부
  - fixed_courses 리스트 구조

- recommend_schema.py
  - /recommend 요청/응답 스키마
  - session_id 필수 여부
  - 추천받을 교양 개수 범위
  - user_prompt 최대 길이

---

## 15. 한 줄 요약

PlaNU 백엔드는 사용자가 업로드한 전공 수강편람을 바탕으로 전공 과목/분반을 직접 선택하게 하고, 선택된 전공 시간표를 고정한 뒤, LLM이 해석한 교양 조건과 학교 공식 데이터를 기반으로 교양 시간표를 추천한다. LLM은 전공 선택이나 시간표 생성을 담당하지 않고, 교양 조건을 JSON 규칙으로 변환하는 역할만 수행한다.
