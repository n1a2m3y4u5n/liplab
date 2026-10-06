# LIPLAB — AI 기반 독화(Speechreading) 훈련 플랫폼

청각장애인을 위한 한국어 독화 훈련 웹앱. 입모양(viseme) 인지부터 단어·문장·실전 대화까지
**단계형 커리큘럼**으로 학습하며, 음운론적 유사도 기반 채점과 간격 반복 복습(SRS)을 제공한다.

> 이 문서는 Claude Code(및 신규 기여자)를 위한 프로젝트 오리엔테이션이다. 사용자용 설치·배포
> 안내는 `README.md`·`QUICKSTART.md`·`DEPLOY.md`를 참고.

> ## 👉 **작업을 이어받는다면 `STATUS.md`부터 읽는다.**
> 지금 어디까지 했고 다음에 뭘 해야 하는지가 한 화면에 정리돼 있다.
> 이 문서(CLAUDE.md)는 프로젝트 구조 설명이지 현황판이 아니다.

---

## 기술 스택

| 영역 | 스택 |
|------|------|
| Backend | Python 3.11+, FastAPI(async), SQLAlchemy(SQLite/PostgreSQL), python-jose(JWT), Anthropic Claude API |
| Frontend | React 19, Vite, Tailwind CSS 3.4, Zustand(상태), React Router, Framer Motion, Three.js(3D 아바타) |
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
- 비로그인 첫 화면은 랜딩(`/`)이고, 로그인 화면의 '둘러보기(데모)'로 회원가입 없이 들어갈 수 있다(`/api/auth/demo`).

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
  llm_service.py   Claude 기반 시나리오·대화 생성
  sign_service.py  한국수어(KSL) 학습 보조 변환
frontend/src/
  App.jsx          라우팅 + AuthGate(미인증이면 `/`는 Landing, 그 밖은 Login, '둘러보기'=데모) + StageGate(단계 잠금 가드)
  api.js           API 클라이언트 (authAPI, learningAPI, curriculumAPI, scoreAPI …)
  components/AppShell.jsx  Figma 셸 — 좌측 탭(학습·연습·과제·복습·분석), 모바일 상단 바+하단 탭 바
  pages/
    CurriculumPath.jsx  /learn/path — 학습 커리큘럼 경로(단계 노드·잠김 표시). 앱의 홈
    PracticeHub.jsx     /practice/hub — 연습 탭(상황별 시나리오·다자대화·자유발화·수어)
    ReviewTab.jsx / AnalysisTab.jsx / TasksPage.jsx / ProfilePage.jsx  복습·분석·과제·프로필 탭
    EvalReport.jsx      /analysis/eval — 학습 효과 리포트(학습곡선·향상도)
    Landing.jsx         비로그인 `/` 랜딩(Figma 02. Landing 9:12). 시작하기 → /signup, 계정이 이미 있습니다 → /login
    Login.jsx / Onboarding.jsx  로그인·회원가입 / 첫 방문 온보딩
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
| 1 | 8 | 85(최근 가중 정답률) | 없음(인지퀴즈: 정오답) |
| 2 | 6 | 85(최근 가중 정답률) | 없음(단어: 정오답) |
| 3 | 5 | 80(최근 가중 합격률) | 60점 |
| 4 | 4 | 75(최근 가중 합격률) | 55점 |

> 9/26 검토에서 이 표가 7/13 이후 코드와 달랐던 것을 바로잡았다(값은 `main.py`의 `_STAGEn_*`).
> 한번 숙달한 단계는 이후 오답으로 누적 정확도가 떨어져도 숙달을 유지한다(다음 단계가 다시 잠기지 않게).
> 1·2단계의 정답률은 9/27부터 편향 보정 지수 이동 평균(`main._ewma_mastery`, a 0.08)이다. 초반 실패가 끝까지 남던 누적 방식보다
> 거짓 숙달과 지연이 모두 줄었다(가상 학습자 시뮬레이션, `docs/mastery-ewma.md`). 3단계도 9/27 저녁부터 같은 추정값(문턱 80,
> 5절)이고, 9/29부터 4지선다 문장 답은 우연 보정(정답 1, 오답 −1/3, 10절)으로 들어간다. 4단계와 말하기 6단계는 9/27 밤부터(4단계 75, 말하기 85·90, 6절). 말하기 4·5단계는 9/28 실제 청각장애 발화 측정으로 68(확인용 화자 절반 합격률 73.1% − 5, 처음 77에서 리뷰 뒤 고침)과 개인 향상 경로(`speak_curriculum.gain_mastered`, 복습·무음 시도 제외, 최근 중앙값 50 이상).
> 말하기 모음·자음(2·3단계)은 9/28부터 이동 평균이 문턱에 닿은 뒤 4단계 단어 풀의 낱말 속 소리 확인(최근 3번 중 2번 합격, 첫 음절 목표 소리까지 맞아야 합격)까지 넘어야 숙달이다(8절).
> 처음 숙달한 순간의 시도 수·시각은 `stage_progress.mastered_attempts`·`mastered_at`에 남는다(`main._settle_mastery`, 학습 효과
> 리포트의 숙달 도달 시행수, `docs/eval-metrics.md`). 2단계 보기는 서버가 고른다(`visual_difficulty.stage2_plan`): 입모양이 똑같은
> 단어는 빼고, 숙달 전 '보이는 최소대립 1 + 입모양이 다른 단어 2', 숙달 뒤 '보이는 최소대립 3'. 풀은 단어 은행에서 표준검사 단어와
> `curriculum.STAGE2_EXCLUDED`(드문 말 등)를 뺀 것이다. 문맥 추론은 `check_closure`를 통과하고 `CLOSURE_EXCLUDED`에 없는 문항만 낸다.

### 잠금이 강제되는 4개 지점

순차 잠금은 표시뿐 아니라 진입과 기록까지 막는다:

1. **커리큘럼 경로 노드** — `pages/CurriculumPath.jsx`: 잠긴 단계 노드는 회색 + 버튼 `disabled`.
2. **라우트 가드** — `App.jsx`의 `StageGate`: `/learn/word`(2), `/practice`(3), `/conversation`(4)에
   직접 URL·내비게이션으로 진입해도 잠겨 있으면 `/learn/path`로 리다이렉트.
   (단계 조회 실패 시엔 막지 않음 — 네트워크 오류로 학습 전체가 잠기지 않도록 가용성 우선.)
3. **시나리오 시작 버튼** — `pages/ScenarioHub.jsx`: 3·4단계 잠김이면 시나리오(LLM) 생성 전에 버튼
   비활성화 + "🔒 잠김" 표시로 API 낭비 방지(클릭 시 인앱 안내 배너).
4. **서버 기록**: `main.py`의 `_compute_stages`·`_stage_open`: 2~4단계는 직전 단계가 (이번 계산에서) 열려 있고
   숙달됐거나 배치 포인터가 그 단계 이상일 때만 열린다. 잠긴 단계의 답(문맥 추론은 3단계, 대화는 4단계에 쌓임)은
   숙달에 넣지 않는다(API를 바로 불러 순서를 건너뛰지 못하게). 정답을 본 뒤의 제출은 `practice_only`로 점수만 준다.

### 진행도 기록 경로

- 1단계: `POST /api/curriculum/recognition` → StageProgress(stage=1)
- 2단계: `POST /api/curriculum/word-answer` → StageProgress(stage=2)
- 3단계: `POST /api/progress` (문장 채점 시) → `_bump_stage_progress(stage=3)`
- 4단계: `POST /api/score` (대화 이해도 채점 시) → `_bump_stage_progress(stage=4)`

`_bump_stage_progress(user_id, stage, passed, min_attempts, mastery_pct, db)` 헬퍼가
시도·정답 누적과 숙달 판정을 공통 처리한다. 오답은 SRS 복습 큐(`ReviewItem`)에 예약된다.
3단계 문장도 합격선(60) 아래면 kind 'sentence'로 예약되고(9/28), 오늘의 복습(`/review/scheduled`)에 하루 5개까지 나온다
(`main._SENTENCE_REVIEW_DAILY`). 그 답은 `srs_review_` 세션으로 채점돼 간격만 조정하고 3단계 숙달에는 넣지 않는다.

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
- 프론트 `AvatarVRM.jsx`: 단일 GLB(`/models/realistic_face.glb` — 2026-09-21부터 Character Creator 두상,
  ARKit 52종 + CC 혀 모프), ARKit 블렌드셰이프를 `useFrame`에서 **고정 속도**(`delta*22`)로 lerp.
  이 모델은 `jawOpen` 모프가 피부를 안 움직여 **턱 뼈(`CC_Base_JawRoot`) 회전**으로 벌림을 만든다.
  카메라는 입 클로즈업 정면이 기본이고, `view='side'`면 `CameraRig`가 얼굴 둘레로 옆 70°까지 이징 회전한다(문장 플레이어의
  '측면 보기' 버튼, 손으로 돌리는 범위도 측면까지).
  9/29부터 코드가 안 쓰는 CC 전용 모프를 지우고 입 클로즈업에서 안 보이는 텍스처(몸·팔·속눈썹·눈)를 512로 줄인 판이다
  (GPU 약 120MB → 70MB, `scripts/glb-slim`, 원본은 git 9f08043). 모델을 바꾸면 이 스크립트를 다시 돌리고 sw.js CACHE를 올린다.
- `LipSyncPlayer3D.jsx`: `setTimeout`으로 프레임 스테핑(속도·프레임 이동·리플레이 지원).

### 트랙 1: 3D 모션 개선 (구현 순서 **A → B → F → D**)

| 코드 | 작업 | 핵심 | 상태 |
|------|------|------|------|
| **A** | `transition_ms` 실제 반영 | 프레임별 `transition_ms`(+재생 속도)로 보간 속도 결정. `LipSyncPlayer3D`→`AvatarVRM`→`RealisticFace`로 전달 | 완료(9/27 dd8bbf6 재구현, 퀴즈 아바타 `MouthAvatar`까지 9ee48ad) |
| **B** | 이징 + 피크 도달 보장 | 시간추적 ease-in-out 보간, 전환은 프레임 길이의 60% 내 완료→목표 도달 후 유지(`durationMs` 전달) | 완료(9/27 dd8bbf6·9ee48ad, `lib/visemeTiming.js`) |
| **F** | 측면(프로필) 뷰 토글 | `AvatarVRM`에 `view`('front'/'side') + `CameraRig`(`SIDE_AZIMUTH` 70°, 도는 동안만 그림). `LipSyncPlayer3D`의 '측면 보기' 버튼 | 완료(9/28 37190ae 재구현) |
| **D** | 아이들 모션 | `RealisticFace` useFrame에 눈 깜빡임(`eyeBlinkLeft/Right`, 2.5~6초마다, 깜빡이는 동안만 그림). 텍스트 입모양에만(음성구동·거울 제외). 쉴 때 그리지 않는 원칙 때문에 머리 흔들림·호흡은 넣지 않았다 | 완료(9/28 37190ae, 눈 깜빡임만) |
| **E** | 선행 동시조음 | 원순음 등에서 다음 viseme을 미리 블렌딩(anticipatory). `lib/coarticulation.js`, 빌드 플래그 `VITE_COART_E=1`일 때만 | 구현했으나 사전 기준 미달로 기본 끔(9/29 파드 확인 Δ_R +0.044 < +0.05, `docs/coarticulation-e.md` 6절) |

> A~D는 7/13(ee5366f)에 `AvatarVRM.jsx`·`LipSyncPlayer3D.jsx`에 들어갔다가 7/14 병합 정합(d3605d3)에서 빠졌다.
> A·B는 9/27 다시 넣었고(dd8bbf6, 퀴즈 아바타 9ee48ad), 측면 보기(F)·눈 깜빡임(D)은 9/28 다시 넣었다(37190ae). 모두 프론트 전용이라
> 백엔드 재시작이 필요 없다. E는 켜면 둥글림 상관이 꾸준히 오르지만(구간이 0을 넘음) 사전 기준 크기에 못 닿아 꺼 두었다.

### 트랙 2: 기능 추가 (백로그, 우선순위 미정)

- ~~웹캠 미러 모드~~ — 구현됨: `components/WebcamMouthCheck.jsx`(MediaPipe 실시간 채점 + 아바타 미러
  `AvatarVRM mirrorRef/bsFrameRef` + K 분류기·조음 교정), 자체 립리딩 ONNX `lib/lipreadModel.js`.
- ~~최소대립쌍 A/B 아바타~~ — 구현됨(9/28 937c0c6): `components/MouthCompare.jsx`. 2단계 단어 문항을 틀리면 정답과 고른 말의
  입모양을 두 아바타로 나란히 재생한다(누를 때만 열고, 입모양이 같은 무리면 입만으로는 못 가른다고 알림).
- ~~혼동 매트릭스 분석~~ — 구현됨: `AnalysisDetail.jsx`(비심 혼동행렬 카드) + `EvalReport.jsx`(학습 효과 리포트).
- ~~약점 기반 적응 템포~~ — 구현됨(9/28 f56c36a): `lib/visemeTiming.js`의 `slowWeakFrames`·`pickSlowVisemes`와 `hooks/useSlowWeak.js`.
  자주 틀리는 입모양(숙달도 0.7 미만, 5번 이상 본 것 상위 3개) 프레임만 1.35배 천천히, 연습 화면(단어·문장·대화·문맥)에만 쓴다.
  감속 정답은 숙달에 0.5로 들어가고 숙달 추정 70 이상이면 감속을 끈다(`docs/curriculum-roadmap.md` 1-1, `docs/mastery-ewma.md` 7절).
- **내 문장 연습(Custom phrase)** — 실생활 문구 입력 → 즉시 드릴. 입력 문장의 입모양을 보는 것까지는 있다(`/pronounce`
  '내 문장 발음 보기', `pages/FreeSpeak.jsx`). 그 문장으로 읽기 문제를 내는 드릴은 없다.
- **실제 화자 영상 라이브러리** — 음소별 실제 입 영상 토글(아바타 ↔ 실제).
- **TTS 오디오 동기화** — 잔존 청력 대상 멀티모달(입+소리+자막).
- **일일 챌린지/배지/스트릭 강화**, **PWA 오프라인 모드**(설치와 앱 셸 오프라인은 `public/sw.js`에 있고, API·학습 데이터는 캐시하지 않는다).
