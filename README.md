# 💱 환율 AI 챗봇 (USD/KRW)

원/달러 환율 시계열 데이터를 저장·관리하고, **저장된 데이터의 요약을 바탕으로 답하는 AI 챗봇** 서비스입니다.

## 서비스 소개

환율이 궁금할 때 "요즘 환율이 오르고 있나?", "올해 최고점은 언제였지?"를 차트·표에서 직접 찾기는 번거롭습니다.
이 서비스는 1년치 일별 환율(262개)을 Firestore에 저장해 두고, 질문할 때마다 **최신 데이터 요약(기간·개수·평균·최고/최저·추세)을 GPT의 시스템 프롬프트에 주입**합니다.
그래서 GPT가 일반 지식이 아니라 **실제 저장된 수치**로 답합니다. 데이터를 추가·수정·삭제하면 다음 답변부터 바로 반영됩니다.

| 기능 | 설명 |
| --- | --- |
| 데이터 기반 AI 채팅 | 질문 → 요약 주입 → GPT 답변, 로딩 표시, 필요 시 도구 호출(Function Calling) |
| 데이터 관리(CRUD) | (date, value, memo) 추가/수정/삭제, 목록 갱신, 저장 결과 토스트 |
| 대화 기록 | 채팅 시 자동 저장, 목록 조회, 클릭 시 불러오기, 삭제 |
| 데이터 요약 | 상단 요약 바(기간/개수/평균/최고·최저/최신값/추세) |
| 보너스 | 상세 통계 API, 추이 그래프(일별 값 + 7일 이동평균), CSV/JSON 내보내기, 다크 모드 |

## 배포 URL

| 구분 | URL |
| --- | --- |
| 프론트엔드 (Vercel) | `https://<your-app>.vercel.app` |
| 백엔드 API (Render) | `https://<your-api>.onrender.com` |
| Swagger UI | `https://<your-api>.onrender.com/docs` |

> ⏳ **Render 무료 플랜 안내**: 15분간 요청이 없으면 서버가 잠듭니다. 첫 접속 시 30초~1분 정도 걸릴 수 있습니다.
> 프론트엔드는 접속하자마자 `/health`로 서버를 깨우고, 2.5초 이상 걸리면 "서버를 깨우는 중" 안내 배너를 띄운 뒤 응답이 올 때까지 재시도합니다.

## 기술 스택

- **Backend**: Python 3.12, FastAPI, Uvicorn, Pydantic v2
- **DB**: Firebase Firestore (`firebase-admin`)
- **AI**: OpenAI Python SDK (`gpt-5-mini`, Codyssey 프록시 `https://copa.codyssey.kr/v1`), Function Calling
- **Frontend**: HTML / CSS / JavaScript (프레임워크 없음, 그래프는 Canvas로 직접 그림)
- **배포**: Render(백엔드), Vercel(프론트엔드)

## 데이터

- **출처**: 유럽중앙은행(ECB) 기준 환율, [Frankfurter API](https://www.frankfurter.app/)
- **범위**: 2025-10-01 ~ 2026-10-09 영업일 기준 **262개** (`backend/data/usd_krw.csv`)
- **요약 정보** (`GET /api/data/summary`)
  - 기간, 개수, 평균, 최고/최저(날짜 포함), 시작값/최신값, 기간 변화율
  - **최근 추세**: 최근 20개 값에 선형회귀 기울기를 구해 구간 동안의 예상 변화율이 +1% 이상이면 `증가`, -1% 이하면 `감소`, 그 사이면 `유지`
- **상세 통계** (`GET /api/data/statistics`, 보너스): 표준편차, 중앙값, 일간 변동성, 최대 낙폭(MDD), 7/30일 이동평균, 월별 평균/최고/최저

## 프로젝트 구조

```
Codyssey-M1-2/
├── backend/
│   ├── main.py                  # 앱 생성, CORS, 라우터 등록, 전역 예외 처리
│   ├── app/
│   │   ├── config.py            # 환경 변수 로드
│   │   ├── db.py                # Firestore 연결 + 저장소(Repo) 추상화
│   │   ├── schemas.py           # Pydantic 요청/응답 모델(검증 규칙)
│   │   ├── routers/             # HTTP 계층: 경로, 상태 코드, 에러 변환
│   │   │   ├── data.py
│   │   │   ├── conversations.py
│   │   │   └── chat.py
│   │   └── services/            # 비즈니스 로직: 분석, 저장, GPT 호출
│   │       ├── data_service.py
│   │       ├── conversation_service.py
│   │       └── chat_service.py
│   ├── scripts/seed.py          # CSV → Firestore 초기 적재
│   ├── data/usd_krw.csv
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── public/                  # index.html, style.css, app.js (+ 빌드 시 생성되는 config.js)
│   ├── build.js                 # API_BASE_URL 환경 변수 → public/config.js
│   └── vercel.json
├── render.yaml                  # Render 배포 설정(Blueprint)
└── docs/screenshots/
```

**분리 기준**: `routers`는 "요청을 받고 응답을 돌려주는 일"(경로, 상태 코드, 404 변환)만, `services`는 "무엇을 계산하고 저장하는지"만 담당합니다. 그래서 채팅 서비스가 HTTP를 거치지 않고 `data_service.get_summary()`를 직접 호출해 재사용할 수 있고, Firestore 접근은 `db.py`의 Repo 한 곳에 모여 있습니다.

## API

Swagger UI(`/docs`)에서 모든 API를 직접 실행해 볼 수 있습니다.

| Method | Path | 설명 |
| --- | --- | --- |
| POST | `/api/data` | 새 데이터 추가 |
| GET | `/api/data` | 데이터 목록(날짜 오름차순, `start`/`end` 필터) |
| PUT | `/api/data/{id}` | 데이터 수정(보낸 필드만 변경) |
| DELETE | `/api/data/{id}` | 데이터 삭제 |
| GET | `/api/data/summary` | 데이터 요약(프롬프트 주입용) |
| GET | `/api/data/statistics` | 상세 통계 (보너스) |
| GET | `/api/data/export?format=csv\|json` | 내보내기 (보너스) |
| POST | `/api/conversations` | 대화 저장 |
| GET | `/api/conversations` | 대화 목록 — **messages 미포함**(id, title, message_count, 시각) |
| GET | `/api/conversations/{id}` | 특정 대화의 전체 messages 조회 (방식 A) |
| DELETE | `/api/conversations/{id}` | 대화 삭제 |
| POST | `/api/chat` | AI 채팅(요약 주입 + 자동 저장) |
| GET | `/health` | 헬스 체크(콜드스타트 깨우기) |

### Firestore 컬렉션 구조

```
data/{autoId}
  date: "2026-10-09"   value: 1341.49   memo: "ECB 기준 USD/KRW"
  created_at, updated_at (ISO 문자열)

conversations/{autoId}
  title: "최근 환율 추세가 어때?"
  messages: [ { role: "user"|"assistant", content, created_at }, ... ]
  created_at, updated_at
```

### 입력 검증 (Pydantic)

잘못된 값이 DB에 들어가기 전에 FastAPI가 자동으로 **422** 응답을 돌려줍니다.

- `date`: `YYYY-MM-DD` 날짜만 허용, 미래 날짜 거부
- `value`: 0보다 크고 1,000,000 미만
- `memo`: 최대 200자, 앞뒤 공백 제거
- 채팅 `message`: 1~2000자, 공백만 있는 메시지 거부
- 대화 `role`: `user` / `assistant`만 허용
- 존재하지 않는 id는 404, 수정할 필드가 없으면 400, OpenAI 장애는 502, 키 미설정은 503

## 컨텍스트 주입과 도구 호출 흐름

```
사용자 질문
   │
   ▼
POST /api/chat
   │ 1. data_service.get_summary()  ← Firestore data 컬렉션 전체로 요약 계산
   │ 2. 요약을 시스템 프롬프트의 [데이터 요약] 자리에 삽입
   │ 3. (이어지는 대화면) 이전 메시지 최대 10개 + 새 질문
   ▼
GPT 호출 (tools 4개 제공)
   ├─ 요약만으로 답할 수 있음 → 바로 답변
   └─ 세부 정보 필요 → tool_call ─▶ 서버가 내부 함수 실행 ─▶ 결과를 tool 메시지로 전달 ─▶ GPT 재호출 (최대 3회)
   │
   ▼
4. conversations 컬렉션에 user/assistant 메시지 자동 저장
   │
   ▼
응답: { conversation_id, reply, summary, tool_calls }
```

### 도구(Function Calling) 목록과 호출 근거

| 도구 | 언제 호출하나 |
| --- | --- |
| `get_data_summary(start_date, end_date)` | 전체가 아닌 **특정 기간**의 요약이 필요할 때 |
| `get_statistics(start_date, end_date)` | 변동성, 표준편차, 이동평균, 월별 평균처럼 **요약에 없는 지표**가 필요할 때 |
| `list_data(start_date, end_date, limit)` | **특정 날짜의 원본 값**이 필요할 때 |
| `list_conversations()` | 사용자가 **이전 대화**를 물을 때 |

모든 도구에는 필수 인자 `reason`이 있어, GPT가 **왜 그 도구를 호출하는지**를 한 문장으로 남깁니다. 이 값은 응답의 `tool_calls`와 서버 로그에 기록되고, 채팅 화면에서는 답변 아래 "🔧 사용한 도구"에 마우스를 올리면 보입니다.

실제 호출 예시:

| 질문 | 도구 호출 | GPT가 남긴 근거(reason) |
| --- | --- | --- |
| 최근 환율 추세가 어때? | 없음 | (주입된 요약의 "최근 추세"로 충분) |
| 2026년 7월의 변동성과 월평균도 알려줘 | `get_statistics(2026-07-01, 2026-07-31)` | "2026년 7월의 변동성(표준편차, 일간 변동성 등)과 월평균을 계산하기 위해" |

## 로컬 실행 방법

### 1) 백엔드

```bash
cd backend
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env        # 값 채우기 (아래 환경 변수 참고)

python -m scripts.seed      # 최초 1회: CSV 262개를 Firestore에 적재
uvicorn main:app --reload   # http://localhost:8000/docs
```

> Firebase 자격 증명이 없으면 서버는 **메모리 저장소 + CSV 샘플**로 뜹니다(개발용, 재시작하면 초기화). `GET /` 응답의 `storage` 값으로 `firestore`/`memory`를 확인할 수 있습니다.

### 2) 프론트엔드

```bash
cd frontend
node build.js                          # public/config.js 생성 (기본 http://localhost:8000)
python -m http.server 5500 -d public   # http://localhost:5500
```

다른 API 주소를 쓰려면 `API_BASE_URL=https://... node build.js`로 빌드합니다.

## 환경 변수

### 백엔드 (Render)

| 이름 | 필수 | 설명 |
| --- | --- | --- |
| `OPENAI_API_KEY` | ✅ | OpenAI(또는 Codyssey 프록시) API 키 |
| `OPENAI_BASE_URL` | | OpenAI 호환 프록시 주소. 예: `https://copa.codyssey.kr/v1` |
| `OPENAI_MODEL` | | 기본 `gpt-5-mini` |
| `OPENAI_MAX_TOKENS` | | 응답 최대 토큰(비용 제한), 기본 `2000` |
| `FIREBASE_SERVICE_ACCOUNT_JSON` | ✅* | 서비스 계정 키 JSON **전체 내용**(배포용) |
| `FIREBASE_SERVICE_ACCOUNT_PATH` | ✅* | 서비스 계정 키 파일 경로(로컬용) |
| `ALLOWED_ORIGINS` | ✅ | CORS 허용 도메인, 쉼표 구분. 예: `https://<your-app>.vercel.app,http://localhost:5500` |

\* 둘 중 하나만 있으면 됩니다.

### 프론트엔드 (Vercel)

| 이름 | 필수 | 설명 |
| --- | --- | --- |
| `API_BASE_URL` | ✅ | 백엔드 주소. 예: `https://<your-api>.onrender.com` |

### 키 관리와 CORS를 이렇게 한 이유

- **키는 환경 변수로만**: `.env`와 서비스 계정 JSON은 `.gitignore`에 들어 있어 GitHub에 올라가지 않습니다. 코드가 공개돼도 키가 새지 않고, 키를 바꿀 때 코드를 고칠 필요가 없습니다.
- **OpenAI 키는 백엔드에만**: 프론트엔드 JS는 누구나 볼 수 있으므로 키를 두면 바로 유출됩니다. 프론트는 백엔드 주소(`API_BASE_URL`)만 압니다.
- **CORS**: 브라우저는 다른 도메인(Vercel → Render)으로의 요청을 기본적으로 막습니다. `ALLOWED_ORIGINS`에 등록한 내 프론트 도메인만 허용해, 다른 사이트가 내 API를 브라우저에서 호출해 OpenAI 비용을 쓰는 것을 줄입니다.
- **비용 제한**: `max_completion_tokens`, 이전 대화 최대 10개, 도구 호출 최대 3회, 메시지 2000자 제한을 둡니다.

## 배포

### 백엔드 — Render

1. 이 저장소를 GitHub에 푸시합니다.
2. Render → **New → Web Service** → 저장소 선택
   - Root Directory: `backend`
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
   - (또는 **New → Blueprint**로 `render.yaml` 사용)
3. Environment에 위 백엔드 환경 변수를 입력합니다. `FIREBASE_SERVICE_ACCOUNT_JSON`에는 키 파일 내용을 그대로 붙여 넣습니다.
4. 배포 후 `https://<your-api>.onrender.com/docs`에서 Swagger UI를 확인합니다.

### 프론트엔드 — Vercel

1. Vercel → **Add New Project** → 같은 저장소 선택
2. Root Directory: `frontend` (Build Command/Output은 `vercel.json`에 지정됨)
3. Environment Variables에 `API_BASE_URL=https://<your-api>.onrender.com` 추가 후 배포
4. 발급된 Vercel 도메인을 Render의 `ALLOWED_ORIGINS`에 추가합니다.

## 제출 스크린샷

| 화면 | 이미지 |
| --- | --- |
| 데이터 요약이 보이는 채팅 화면 (질문 + 답변) | ![chat](docs/screenshots/chat.png) |
| 데이터 관리 화면 (추가/수정/삭제 결과) | ![data](docs/screenshots/data.png) |
| 대화 기록 화면 (불러오기) | ![history](docs/screenshots/history.png) |
