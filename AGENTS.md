# LIPLAB — AI 기반 독화(Speechreading) 훈련 플랫폼

청각장애인을 위한 한국어 독화 훈련 웹앱. 입모양(viseme) 인지부터 단어·문장·실전 대화까지
**단계형 커리큘럼**으로 학습하며, 음운론적 유사도 기반 채점과 간격 반복 복습(SRS)을 제공한다.

> 이 문서는 Codex(및 신규 기여자)를 위한 프로젝트 오리엔테이션이다. 사용자용 설치·배포
> 안내는 `README.md`·`QUICKSTART.md`·`DEPLOY.md`를 참고.

---

## 기술 스택

| 영역 | 스택 |
|------|------|
| Backend | Python 3.11+, FastAPI(async), SQLAlchemy(SQLite/PostgreSQL), PyJWT, Anthropic Codex API |
| Frontend | React 18, Vite, Tailwind CSS, Zustand(상태), React Router, Framer Motion, Three.js(3D 아바타) |
| 배포 | Docker(멀티스테이지), Fly.io |

---

## 로컬 실행

```bash
# Backend — http://localhost:8080
cd backend
python -m uvicorn main:app --reload --port 8080   # 개발 시 --reload 권장

# Frontend — http://localhost:5173  (별도 터미널)
cd frontend
npm install
npm run dev
```

- 환경변수: `cp .env.example .env` 후 `ANTHROPIC_API_KEY`, `JWT_SECRET` 설정.
- 프론트 프로덕션 빌드 검증: `cd frontend && npx vite build`.
- 로그인은 **데모 계정 자동 입장**(`AuthGate` → `/api/auth/demo`)이라 별도 회원가입 불필요.

> ⚠️ 개발 중 `--reload` 없이 uvicorn을 띄웠다면 `main.py` 수정 후 **수동 재시작**해야 반영된다.

---

## 디렉터리 구조 (핵심)

```
backend/
  main.py          FastAPI 엔드포인트 전체 (인증·진행도·커리큘럼·채점·대화·SRS)
  curriculum.py    단계형 커리큘럼 콘텐츠(순수 데이터/함수): STAGES, VISEME_LESSONS, WORD_BANK, CLOSURE_ITEMS
  database.py      SQLAlchemy 모델 (User, Profile, StageProgress, Progress, WeakViseme, ReviewItem …)
  engine.py        한국어 → viseme 변환(VISEME_MAP), 동시조음 모델링
  scoring.py       음운론적 유사도 채점
  llm_service.py   Codex 기반 시나리오·대화 생성
  sign_service.py  한국수어(KSL) 학습 보조 변환
frontend/src/
  App.jsx          라우팅 + AuthGate(데모 자동 로그인) + StageGate(단계 잠금 가드)
  api.js           API 클라이언트 (authAPI, learningAPI, curriculumAPI, scoreAPI …)
  pages/
    Dashboard.jsx     학습 커리큘럼 카드 + 테스트 시작 + 복습 탭
    VisemeLiteracy.jsx  1단계 입모양 인지
    WordStage.jsx       2단계 음절·단어
    Practice.jsx        3단계 문장(상황별)
    Conversation.jsx    4단계 대화 실전
    Closure.jsx         문맥 추론 훈련
    Review.jsx          오늘의 복습(SRS)
```

---

## 핵심 개념: 단계형 커리큘럼 & 순차 잠금

학습은 5단계로 구성되며, **직전 단계를 일정 수준 이상 숙달해야 다음 단계가 해금**된다.

| 단계 | key | 콘텐츠 | route | 해금 조건 |
|------|-----|--------|-------|-----------|
| 0 | onboarding | 입문·배치(트랙 선택) | — | 항상 접근 가능 |
| 1 | viseme | 입모양 인지 (10그룹) | `/learn/viseme` | 트랙 선택(배치) 완료 시 |
| 2 | word | 음절·단어 (최소대립쌍) | `/learn/word` | **1단계 숙달** |
| 3 | sentence | 문장 (상황별) | `/practice` | **2단계 숙달** |
| 4 | conversation | 대화 실전 (AI) | `/conversation` | **3단계 숙달** |

### 상태(status)와 표시

`GET /api/curriculum/stages`가 사용자별로 각 단계 status를 계산한다
(`locked` | `unlocked` | `in_progress` | `mastered` | `coming_soon`).

- 잠긴 단계는 대시보드 카드에서 회색 **"잠김"** 배지 + 흐린 텍스트로 표시.
- 잠긴 카드를 클릭하면 **"직전 단계를 먼저 완료해주세요"** 안내(직전 단계 번호·제목 동적 표시).

### 0단계가 항상 "완료"로 보이는 이유

0단계는 학습 콘텐츠가 아니라 **트랙 선택(배치)** 자체가 완료 조건이다.
트랙을 고르면 `Profile.placed = True`가 되고, 이 플래그가 유지되는 한 0단계는 `mastered`로 표시된다.
"← 트랙 다시 선택"을 누르면 `placed = False`로 돌아가 미완료 상태가 된다.

### 숙달(mastery) 판정 기준 — `backend/main.py` 상단 상수

각 단계는 시도(attempts)·정답(correct)을 rolling 누적하고, 최소 시도수와 정답률을 함께 만족하면
`mastered`가 된다. 점수제(3·4단계)는 "PASS 점수 이상 = 성공 1회"로 환산한다.

| 단계 | 최소 시도 | 숙달 정답률 | PASS 점수 |
|------|-----------|-------------|-----------|
| 1 | 15 | 80% | — (인지퀴즈: 정오답) |
| 2 | 12 | 80% | — (단어: 정오답) |
| 3 | 10 | 75% | 70점 |
| 4 | 8 | 70% | 65점 |

### 잠금이 강제되는 3개 지점

순차 잠금은 표시뿐 아니라 진입까지 3중으로 막는다:

1. **커리큘럼 카드** — `Dashboard.jsx`의 `CurriculumPath`: 잠긴 카드는 흐리게 표시 + 클릭 시 안내.
2. **라우트 가드** — `App.jsx`의 `StageGate`: `/learn/word`(2), `/practice`(3), `/conversation`(4)에
   직접 URL·내비게이션으로 진입해도 잠겨 있으면 `/dashboard`로 리다이렉트.
   (단계 조회 실패 시엔 막지 않음 — 네트워크 오류로 학습 전체가 잠기지 않도록 가용성 우선.)
3. **테스트 시작 버튼** — `Dashboard.jsx`: 3단계 잠김이면 시나리오(LLM) 생성 전에 버튼 비활성화 +
   "🔒 2단계 완료 후 열려요" 표시로 API 낭비 방지.

### 진행도 기록 경로

- 1단계: `POST /api/curriculum/recognition` → StageProgress(stage=1)
- 2단계: `POST /api/curriculum/word-answer` → StageProgress(stage=2)
- 3단계: `POST /api/progress` (문장 채점 시) → `_bump_stage_progress(stage=3)`
- 4단계: `POST /api/score` (대화 이해도 채점 시) → `_bump_stage_progress(stage=4)`

`_bump_stage_progress(user_id, stage, passed, min_attempts, mastery_pct, db)` 헬퍼가
시도·정답 누적과 숙달 판정을 공통 처리한다. 오답은 SRS 복습 큐(`ReviewItem`)에 예약된다.

---

## 주요 API 엔드포인트

| Method | Path | 용도 |
|--------|------|------|
| POST | `/api/auth/demo` | 데모 계정 자동 로그인 |
| GET | `/api/curriculum/stages` | 단계 목록 + 사용자별 status(잠금/숙달) |
| POST | `/api/curriculum/track` | 트랙 선택(배치) → 1단계 해금 |
| POST | `/api/curriculum/track/reset` | 배치 취소(진행 데이터는 보존) |
| POST | `/api/curriculum/recognition` | 1단계 입모양 인지 채점 |
| GET/POST | `/api/curriculum/words`, `/word-answer` | 2단계 단어 콘텐츠·채점 |
| GET | `/api/curriculum/closure` | 문맥 추론 항목 |
| POST | `/api/progress` | 3단계 문장 연습 결과 제출·채점 |
| POST | `/api/score` | 임의 문장 채점(4단계 대화 이해도) |
| GET/POST | `/api/review/*` | 간격 반복 복습(SRS) |
| POST | `/api/conversation` | 4단계 대화 턴 생성 |

---

## 작업 컨벤션

- 백엔드 주석·프론트 UI 문구는 **한국어**. 기존 파일의 주석 밀도·톤을 맞춘다.
- `curriculum.py`는 DB·네트워크 의존이 없는 **순수 데이터/함수** — 결정론적으로 테스트 가능하게 유지.
- 새 잠금/숙달 규칙을 바꿀 때는 (1)`main.py`의 status 계산, (2)`StageGate`, (3)대시보드 버튼 가드
  세 지점의 정합성을 함께 확인한다.
- 숙달 임계값은 `main.py` 상단 `_STAGEn_*` 상수에서만 조정한다.

---

## 로드맵 — 진행 중인 개선 작업

크게 두 갈래로 진행한다: **(1) 3D 모델 모션 개선**, **(2) 기능 추가**.

### 3D 모션 파이프라인 현황 (개선 대상)

- 백엔드 `engine.py`: 한글 → viseme 프레임(`viseme`, `duration_ms`, `transition_ms`) + 동시조음 전환 프레임(11~13).
- 프론트 `AvatarVRM.jsx`: 단일 GLB(`/models/realistic_face.glb`), ARKit 블렌드셰이프를
  `useFrame`에서 **고정 속도**(`delta*22`)로 lerp. 카메라는 입 클로즈업 정면 고정.
- `LipSyncPlayer3D.jsx`: `setTimeout`으로 프레임 스테핑(속도·프레임 이동·리플레이 지원).

### 트랙 1: 3D 모션 개선 (구현 순서 **A → B → F → D**)

| 코드 | 작업 | 핵심 | 상태 |
|------|------|------|------|
| **A** | `transition_ms` 실제 반영 | 프레임별 `transition_ms`(+재생 속도)로 보간 속도 결정. `LipSyncPlayer3D`→`AvatarVRM`→`RealisticFace`로 전달 | ✅ 완료 |
| **B** | 이징 + 피크 도달 보장 | 시간추적 ease-in-out 보간, 전환은 프레임 길이의 60% 내 완료→목표 도달 후 유지(`durationMs` 전달) | ✅ 완료 |
| **F** | 측면(프로필) 뷰 토글 | `AvatarVRM`에 `view`('front'/'side') + `CameraRig`·`VIEW_CONFIG`. 플레이어 좌상단 정면/측면 버튼 | ✅ 완료 |
| **D** | 아이들 모션 | `RealisticFace` useFrame에 눈 깜빡임(`eyeBlinkLeft/Right`)·미세 머리 흔들림·호흡. 입모양 모프와 독립 | ✅ 완료 |
| **E** | 선행 동시조음 | 원순음 등에서 다음 viseme을 미리 블렌딩(anticipatory) | 백로그 |

> A~D 구현 지점: `frontend/src/components/AvatarVRM.jsx`(보간·뷰·아이들 모션),
> `frontend/src/components/LipSyncPlayer3D.jsx`(프레임 데이터·뷰 토글 UI 전달).
> 전부 프론트 전용이라 백엔드 재시작 불필요(vite HMR로 반영).

### 트랙 2: 기능 추가 (백로그, 우선순위 미정)

- **웹캠 미러 모드** ⭐ — 아바타 옆에 사용자 입 표시. 확장: MediaPipe FaceMesh로 사용자 입모양을
  목표 viseme과 비교·채점("따라 말하기").
- **최소대립쌍 A/B 아바타** — `MINIMAL_PAIRS` 재활용, 밥 vs 맘을 두 아바타로 동시 비교(2단계 강화).
- **혼동 매트릭스 분석** — `WeakViseme` + `HOMOPHENE_CLUSTERS`로 개인별 헷갈림 리포트.
- **약점 기반 적응 템포** — 취약 viseme 프레임 자동 감속.
- **내 문장 연습(Custom phrase)** — 실생활 문구 입력 → 즉시 드릴.
- **실제 화자 영상 라이브러리** — 음소별 실제 입 영상 토글(아바타 ↔ 실제).
- **TTS 오디오 동기화** — 잔존 청력 대상 멀티모달(입+소리+자막).
- **일일 챌린지/배지/스트릭 강화**, **PWA 오프라인 모드**.
