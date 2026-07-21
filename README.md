### 1. 프로젝트 소개

#### 1.1. 개발배경 및 필요성
> 편입생의 신분으로써, 부산대에 올해 입학하게 되었는데 과에서 안내가 지연되어 제대로 된 수강신청에 대한 안내를 뒤늦게 접하게 되었다.
> 확인을 하니 편입학의 최종결과가 나오기 이전 이미 희망과목에 대한 사전 수강신청(과목담기) 가 이미 종료된 상태였고, 부산대의 경우에는
> 단과대학교가 매우 많다보니 수강편람을 살펴봐도 과목수가 많아서 인식하는데 있어 어려움이 있었다. 특히 고전읽기와 토론, 인공지능과 컴퓨팅사고와 같은  
> 필수 교양의 경우 그 분반의 수만해도 50개가 넘어가며 시간표도 날짜별 정렬이 불가능하여 일일히 원하는 조건을 수강편람에서 찾아가야 하는 번거로움이 있었다. 
> 수강신청을 완료하고 , 개강을 한후 신입생에게 물어봤을때 대부분이 수강편람에 대한 가독성과 신청방법이 모호하다 보니 안내를 받아도 신청하는데 있어서 어려움 
> 이 많았고 몇몇 학우들은 원하는 과목을 놓쳐버려서 차선의 시간표를 구성하는데 시간과 노력을 많이 들였다고 답변하였다. 이처럼, 현 부산대 수강신청 프로세스에서
> 발견되는 문제점은 1) 방대한 수강과목으로 인한 가독성의 불편 , 2) 수강편람내 정렬기능의 부재로 원하는 정보를 찾아가는데 불편함 , 3) 일부 신/편입생의 경우 사전 시간표제
> 작에서 희망과목 수강담기가 불가능하므로 이상적 시간표의 구성이 어렵다 로 귀결될수 있었다.
> 아래는 24~26년도 부산대학교 편입학 합격자 수를 정리한 표이다. 표에서 볼 수 있듯이 몇백 명의 인원이 편입생의 신분으로 부산대학교에 들어오고, 여기에 추가 합격 신입생의 숫자도 더해지면, 적지 않은 수의 인원이 별다른 수강신청 안내 없이 혼자 수강신청을 진행해야 하는 상황에 놓이는 것이다.

|  연도   |  총 합격자 수  |
| :-----: | :----: |
| 2024학년도  | 336명 |
| 2025학년도 | 275명 |
| 2026학년도 | 203명 |


#### 1.2. 개발 목표 및 주요 내용

프로젝트의 목표 : 부산대 수강신청 도우미 프로그램 (PlaNU) 개발을 통한 수강정정기간 민원 감소 

주요 내용 : 사용자로부터 업로드된 수강편람 및 프롬프트를 기반으로 서버 및 LLM의 활용을 이용한 이상적 시간표 제시

#### 1.3. 세부내용

> 다음의 프로세스를 통한 앱의 작동이 예정되어있습니다.
> 1. 앱 : 사용자가 엑셀파일(수강편람) , 프롬프트(공강옵션, 외국어강의 옵션 과 같은 사용자가 희망하는 조건)를 업로드
> 2. 서버 : 엑셀파일을 텍스트로 변환하여 LLM 으로 전달
> 3. LLM : 전달받은 프롬포트(사용자) 및 자체적 프롬프트(개발자) 를 기반으로 시간표 제작 필터를 생성
>     1. 규칙 : 프롬포트를 토대로, 시간표 트리에 들어갈 엑셀파일(수강편람)의 과목을 선별하는 기준
> 4. 서버 : LLM의 규칙을 토대로, 백트래킹 알고리즘을 사용해 시간표 제작
>     1. 기준 : 강의실간의 거리, 사용자가 지향하는 희망학점 과의 편차 , 프롬포트의 조건
> 5. 앱 : 처리된 결과를 기반으로 '가장 이상적인 시간표' 를 시각화 하여 사용자에게 출력

#### 1.4. 기존 서비스 대비 차별성

> 부산대 수강신청을 직접적으로 연습할수 있는 페이지는 총 2건 웹으로 되어있으나, 이것은 수강신청 자체를 연습하는데 그 목적이 있습니다.
> 따라서, 사용자가 사전에 시간표를 만들어보거나 수강편람을 익숙하게 다루고 원하는 조건대로 정렬할수 있도록 하는데는 거리가 멀고
> 각각 23년도와 24년도의 수강과목 및 교육과정을 포함하고 있어서 시간적 괴리가 존재하는 한계가 있습니다.
> PlaNU 의 경우에는, 개발자가 교양과목에 대한 수강편람을 주기적으로 갱신하고 사용자가 직접 최신의 전공 수강편람을 업로드 하는 방식이기 때문에
> 업데이트를 통해 시간적 괴리를 극복할수 있으며 수강편람을 일일히 정렬하거나 조건을 설정하는것 역시도 간편하게 할수 있으므로 사용자의 편리성을 보장합니다.
> 또한, 앱을 통한 개발이므로 기존의 PC환경의 웹과는 차별화를 가지고 있으며 최근 증가하는 모바일 사용에 맞춰서 사용자의 간편함을 최대로 추구할수 있습니다.

#### 1.5. 사회적 가치 도입 계획

> 본 서비스는 학사 시스템에 익숙하지 않은 신입생·편입생의 수강신청 정보 비대칭을 해소한다. 복잡한 제약 조건을 인지하지 못해 발생하는 오신청을 줄임으로써, 개강 직후 정정 기간에 집중되는 민원을 감소시키고 행정 인력 낭비를 절감할 것으로 기대된다. 나아가 유사한 문제를 겪는 타 대학으로 서비스를 확장해 대학 전반의 수강신청 경험을 개선하는 범용 솔루션으로 발전시킬 수 있다.

### 2.상세설계

#### 2.1. 시스템 구성도

<img width="1693" height="929" alt="KakaoTalk_20260608_163633376" src="https://github.com/user-attachments/assets/fb0da75f-d4e5-4543-8071-984cfa47c58e" />


<br/>

#### 2.3. 사용기술

|  이름   |  버전  |
| :-----: | :----: |
| Python  | 3.14.0 |
| Flutter | 3.41.0 |

LLM API는 테스트 후 가장 적합한 모델 사용 예정
<br/>

### 3. 개발결과

[코딩역량강화플랫폼 Online Judge](http://10.125.121.115:8080/)를 예시로 작성하였습니다.

#### 3.1. 전체시스템 흐름도

- 유저 플로우 차트

  > 코딩 역량강화 플랫폼의 회원가입 부분만 작성했습니다. <br/>
  > 사용자의 행동 흐름을 도식화하여 보여줍니다.
  > <img width="400px" alt="유저 플로우 차트" src="https://github.com/pnuswedu/SW-Hackathon-2024/assets/34933690/c8de7c98-efd8-4f64-a39a-720faabccd78" />

- 테스크 플로우 차트

  > 코딩 역량강화 플랫폼의 로그인 부분만 작성했습니다. <br/>
  > 주요 테스크의 프로세스를 도식화하여 보여줍니다.
  > <img width="400px" alt="테스크 플로우 차트" src="https://github.com/pnuswedu/SW-Hackathon-2024/assets/34933690/b83502a9-032d-4453-8687-428d54643610" />

- 시스템 플로우 차트
  > 코딩 역량강화 플랫폼의 로그인 부분만 작성했습니다. <br/>
  > 테스크의 흐름에 따른 데이터 처리를 도식화하여 보여줍니다.
  > <img width="600px" alt="시스템 플로우 차트" src="https://github.com/pnuswedu/SW-Hackathon-2024/assets/34933690/1bfb66f0-446c-4450-8a81-a78bfe5ac9ce" />
- IA(Information Architecture)
  > 정보나 시스템의 구조를 도식화하여 보여줍니다. <br/>
  > <img width="600px" alt="IA" src="https://github.com/pnuswedu/SW-Hackathon-2024/assets/34933690/07d842fe-fb73-4079-97a3-58b2495ff331" />

<br/>

#### 3.2. 기능설명

##### `메인 페이지`

- 상단 배너
  - 3초에 마다 자동으로 내용이 넘어갑니다. <br/>
    ![상단 배너](https://github.com/pnuswedu/SW-Hackathon-2024/assets/34933690/4640389f-dcaf-4b78-916e-188c8e9c6ee7)

- 공지사항
  - 최근 5개의 공지사항을 보여줍니다.
  - 발행된지 일주일이 안 된 공지사항은 new라는 mark표시를 해줍니다.
  - 공지사항 글을 클릭하면 해당 공지사항 게시글로 이동합니다.
  - 상단의 더보기 버튼을 클릭하면 공지사항 페이지로 이동합니다.<br/>
    <img width="600px" alt="공지사항" src="https://github.com/pnuswedu/SW-Hackathon-2024/assets/34933690/7c425946-ff06-4b32-8b18-4119cc86e308">

- 이번 주 보너스 문제
  - 이번 주의 보너스 점수를 주는 문제를 보여줍니다.
  - 문제를 클릭하면, 해당 문제의 게시글로 이동합니다. <br/>
    <img width="600px" alt="이번 주 보너스 문제" src="https://github.com/pnuswedu/SW-Hackathon-2024/assets/34933690/5c603984-8cf6-4524-84a6-5410bb6a8cbf">

- 실시간 랭킹
  - 상위 랭킹 10명의 유저를 보여줍니다.
  - 상단의 더보기 버튼을 클릭하면 전체 랭킹 페이지로 이동합니다.<br/>
    <img width="200px" alt="실시간 랭킹" src="https://github.com/pnuswedu/SW-Hackathon-2024/assets/34933690/8492e285-5423-4c00-bc46-400cbe733d35">
    <br/>

##### `문제 페이지`

- 문제 목록
  - 사용자가 설정한 한 번에 보여줄 문제 갯수 만큼 한 화면에 문제를 띄워줍니다.
  - 검색창에서 문제의 제목 및 번호로 문제를 검색할 수 있습니다.
  - 난이도, 영역, 카테고리 별로 문제를 볼 수 있습니다.
  - 상단의 shuffle 이모지를 클릭하면 랜덤으로 선택된 문제 푸는 페이지로 이동합니다.
  - 목록에서 문제를 클릭하면 해당 문제를 푸는 페이지로 이동합니다.
    ![문제 목록](https://github.com/pnuswedu/SW-Hackathon-2024/assets/34933690/95afd0db-b5a7-4628-ac9c-164513a9e51b)
    <br/>

#### 3.3. 기능명세서

<img width="200px" alt="실시간 랭킹" src="https://github.com/pnuswedu/SW-Hackathon-2024/assets/34933690/97ad3fea-f90a-437a-b611-3fb8cd24070e" />

| 라벨 |               이름               | 상세                                                                                                  |
| :--: | :------------------------------: | :---------------------------------------------------------------------------------------------------- |
|  S1  |        부산대학교 웹메일         | - 부산대 웹메일 형식인지 검증 <br/>- 중복되는 이메일인지 검증                                         |
|  S2  | 부산대학교 웹메일 인증 코드 전송 | - 클릭 시 인증 코드 메일로 전송                                                                       |
|  S3  |          메일 인증 코드          | - 인증 요청 버튼 클릭 후 활성화 <br/>- 유효시간 5분                                                   |
|  S4  |       메일 인증 코드 확인        | - 인증코드 검증                                                                                       |
|  S5  |              닉네임              | - 4 ~ 12자 영어, 숫자, '\_' 가능                                                                      |
|  S6  |          단과대학 선택           | -부산대학교 단과대학 리스트 보여주기                                                                  |
|  S7  |            학과 선택             | - 단과대학 안의 학과 리스트 보여주기                                                                  |
|  S8  |             비밀번호             | - 입력 시 텍스트 보이지 않도록 •로 표현해주기 <br/>- 6자 이상 20자 이하, 영어와 숫자 조합 필수        |
|  S9  |          비밀번호 확인           | - 입력 시 텍스트 보이지 않도록 •로 표현해주기 <br/>- 비밀번호와 동일한 지 검증                        |
| S10  |          회원가입 완료           | - 비어 있는 입력 칸이 없는지 검증 <br/>-메일 인증 완료했는지 확인 <br/>-조건을 만족하면 회원가입 성공 |
| S11  |              로그인              | - 클릭 시 로그인 모달로 전환                                                                          |

<br/>

#### 3.4. 디렉토리 구조

```
├── build/                      # webpack 설정 파일
├── config/                     # 프로젝트 설정 파일
├── deplay/                     # 배포 설정 파일
├── src/                        # 소스 코드
│   ├── assets/                 # 이미지, 폰트 등의 정적 파일
│   ├── pages/                  # 화면에 나타나는 페이지
│   │   ├── page1/              # 페이지1
│   │   ├── page2/              # 페이지2
│   │   ├── components/         # 여러 페이지에서 공통적으로 사용되는 컴포넌트
│   ├── router/                 # 라우터
│   ├── store/                  # global state store
│   ├── styles/                 # 스타일
│   ├── utils/                  # 유틸리티
├── static/                     # 정적 파일
```

<br/>

### 4. 설치 및 사용 방법

**필요 패키지**

- 위의 사용 기술 참고

```bash
$ git clone https://github.com/test/test.git
$ cd test/frontend
$ npm i
$ export NODE_ENV="development" # windows: set NODE_ENV=development
$ npm run build:dll
$ export TARGET="http://localhost:8000"  # windows: set NODE_ENV=http://localhost:8000
$ npm run dev
```

<br/>

#### 4.1. PlaNU 백엔드 API 흐름

프론트엔드는 아래 순서로 하나의 `session_id`를 이어서 사용합니다. 세션이 만료되어 `SESSION_NOT_FOUND`가 반환되면 전공 수강편람 업로드부터 다시 시작해야 합니다.

1. `GET /health`
   - 서버 상태 확인용입니다.
   - 성공 응답 예: `{"status":"ok"}`

2. `POST /catalog/major`
   - Content-Type: `multipart/form-data`
   - 필수 필드: `department`, `major_catalog` (`.xlsx`)
   - 다음 단계에서 `session_id`를 재사용합니다.
   - 주요 성공 필드: `session_id`, `session_stage="catalog_parsed"`, `parsed_course_count`, `warnings`

3. `POST /major/preview`
   - Content-Type: `application/json`
   - 필수 필드: `session_id`, `prompt`
   - 다음 단계에서 `preview_id`를 재사용합니다.
   - `can_confirm=false`이면 `/major/confirm`을 호출하지 말고 사용자가 프롬프트를 수정해야 합니다.

4. `POST /major/confirm`
   - Content-Type: `application/json`
   - 필수 필드: `session_id`, `preview_id`
   - 성공 시 세션 단계는 `major_confirmed`입니다.

5. `POST /general/prepare`
   - Content-Type: `multipart/form-data`
   - 필수 필드: `session_id`, `elective_area`
   - 선택 필드: `elective_catalog` (`.xlsx`). 파일이 없으면 서버 fallback 교양선택 데이터를 사용합니다.
   - 성공 시 세션 단계는 `general_ready`입니다.

6. `POST /recommend/generate`
   - Content-Type: `application/json`
   - 필수 필드: `session_id`
   - 선택 필드: `target_total_credits`, `additional_elective_count`, `hard_conditions`, `preference_prompt`, `max_candidates`
   - 프롬프트나 학점 목표가 바뀌면 이 단계부터 다시 호출합니다.
   - 성공 시 세션 단계는 `candidates_generated`이고, `unsupported_conditions`, `warnings`, `truncated`, `diagnostics`를 함께 확인합니다.

7. `POST /recommend/rank`
   - Content-Type: `application/json`
   - 필수 필드: `session_id`
   - 선택 필드: `template` (`balanced`, `free_day_priority`, `no_morning_priority`, `compact_schedule`), `top_n`
   - 템플릿만 바뀌면 `/recommend/generate`를 다시 호출하지 않고 이 API만 다시 호출합니다.
   - 성공 시 세션 단계는 `ranking_completed`이며, `ranked_candidates`의 각 항목은 `rank`, `raw_score`, `score_components`, `load_satisfaction`을 포함합니다.

대표 오류 응답 형식:

```json
{
  "error": {
    "code": "INVALID_SESSION_STAGE",
    "message": "전공 확정과 교양 후보 준비가 완료된 세션에서만 시간표를 생성할 수 있습니다.",
    "hint": null,
    "details": {}
  }
}
```

주요 오류 코드: `MAJOR_CATALOG_REQUIRED`, `INVALID_FILE_EXTENSION`, `INVALID_EXCEL_FILE`, `FILE_TOO_LARGE`, `SESSION_NOT_FOUND`, `INVALID_SESSION_STAGE`, `MAJOR_PREVIEW_NOT_CONFIRMABLE`, `INVALID_ELECTIVE_AREA`, `UNKNOWN_RANKING_TEMPLATE`, `INVALID_TOP_N`.

테스트 실행:

```bash
cd C:\hackerton
python -m pytest backend\tests -v
python -m pytest backend\tests\integration -v
python -m pytest backend\tests -m "not llm_live" -v
python -m pytest backend\tests -m llm_live -v
```

실제 LLM 파서 테스트는 비용과 네트워크 상태의 영향을 받으므로 기본 테스트에서 제외됩니다. 운영 경로와 같은 LLM/proxy를 호출하려면 명시적으로 환경 변수를 설정한 뒤 `live_llm` marker만 실행합니다. 인증값은 로그에 출력하지 않으며, trace에는 모델명, proxy 사용 여부, case 이름, latency, 성공/실패 요약만 남깁니다.

```bash
cd C:\hackerton
set RUN_LIVE_LLM_TESTS=1
set PROXY_TOKEN=...
set OPENAI_MODEL=openai/gpt-4.1-mini
set CHAT_PROXY_URL=https://mlapi.run/.../v1
python -m pytest backend\tests\live_llm -m live_llm -v -s
```

PowerShell을 쓰는 경우:

```powershell
cd C:\hackerton
$env:RUN_LIVE_LLM_TESTS = "1"
$env:PROXY_TOKEN = "..."
$env:OPENAI_MODEL = "openai/gpt-4.1-mini"
$env:CHAT_PROXY_URL = "https://mlapi.run/.../v1"
python -m pytest backend\tests\live_llm -m live_llm -v -s
```

특정 parser만 실행:

```bash
python -m pytest backend\tests\live_llm\test_major_selection_live.py -m live_llm -v -s
python -m pytest backend\tests\live_llm\test_general_preference_live.py -m live_llm -v -s
python -m pytest backend\tests\live_llm\test_live_llm_smoke.py -m live_llm -v -s
```

`RUN_LIVE_LLM_TESTS=1`이 없거나 `PROXY_TOKEN`이 설정되지 않은 경우 실제 호출 없이 skip됩니다. timeout은 기본 60초이며 필요하면 `LIVE_LLM_TIMEOUT_SECONDS`로 조정할 수 있습니다.

<br/>

### 5. 소개 및 시연영상

[<img width="700px" alt="소개 및 시연영상" src="https://github.com/pnuswedu/SW-Hackathon-2024/assets/34933690/162132cd-9af5-4154-9b9a-41c96cf5e8fd" />](https://www.youtube.com/watch?v=EfEgTrm5_u4)

<br/>

### 6. 팀 소개

|                                                                   MEMBER1                                                                    |                                                                   MEMBER2                                                                    |                                                                   MEMBER3                                                                    |
| :------------------------------------------------------------------------------------------------------------------------------------------: | :------------------------------------------------------------------------------------------------------------------------------------------: | :------------------------------------------------------------------------------------------------------------------------------------------: |
| <img width="100px" alt="MEMBER1" src="https://github.com/pnuswedu/SW-Hackathon-2024/assets/34933690/f5b5df2a-e174-437d-86b2-a5a23d9ee75d" /> | <img width="100px" alt="MEMBER2" src="https://github.com/pnuswedu/SW-Hackathon-2024/assets/34933690/fe4e8910-4565-4f3f-9bd1-f135e74cb39d" /> | <img width="100px" alt="MEMBER3" src="https://github.com/pnuswedu/SW-Hackathon-2024/assets/34933690/675d8471-19b9-4abc-bf8a-be426989b318" /> |
|                                                             member1@pusan.ac.kr                                                              |                                                              member2@gmail.com                                                               |                                                              member3@naver.com                                                               |
|                                                               프론트앤드 개발                                                                |                                                        인프라 구축 <br/> 백앤드 개발                                                         |                                                          DB 설계 <br/> 백앤드 개발                                                           |

<br/>

### 7. 해커톤 참여 후기

- MEMBER1
  > 작성하세요.
- MEMBER2
  > 작성하세요.
- MEMBER3
  > 작성하세요.
  > <br/>
