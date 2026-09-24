# LIPLAB - AI 기반 독화 훈련 플랫폼

청각장애인을 위한 한국어 독화(Speechreading) 훈련 웹앱입니다. 입모양 인지부터 단어·문장·대화까지 단계형
커리큘럼으로 배우는 **독화 트랙**과, 소리 내어 말하고 발음 점수를 받는 **발화 트랙**이 있습니다.

> 작업을 이어받는다면 [STATUS.md](STATUS.md)부터 읽습니다. 축별 현황은 [docs/고도화_현황_팀공유.md](docs/고도화_현황_팀공유.md),
> 화면 기준은 [LIPLAB_UI_HANDOFF.md](LIPLAB_UI_HANDOFF.md)(Figma), 배포는 [DEPLOY.md](DEPLOY.md)입니다.

## 주요 기능

**학습**
- 단계형 커리큘럼: 독화 5단계(입모양 인지 → 단어 → 문장 → 대화), 발화 단계별 레슨. 직전 단계를 숙달하면 다음 단계가 열리고,
  자가진단(배치검사)으로 시작 단계를 정할 수 있습니다.
- 3D 아바타 립싱크: 한국어 → 비심(15개 입모양 그룹) 변환과 동시조음 모델링, Character Creator 두상, 속도 조절(2x = 실제 말 빠르기),
  측면·투명 두상·성도 단면 보기.
- 연습: 상황별 시나리오(직접 입력), 다자 대화(2~4명), 자유 발화, 수어 함께 보기(국립국어원 한국수어사전 영상), 엔드리스 학습,
  문맥 추론, 입모양 교실(웹캠 따라 하기·조음 교정).
- 복습: 간격 반복(SRS) 오늘의 복습, 틀린 문장·북마크 다시 풀기, 말하기 복습.

**채점과 피드백**
- 독화: 음운론적 유사도 채점(시각적으로 비슷한 음소에 부분 점수), 자모 단위 혼동 진단, 안 보이는 자질(기식·긴장·비음)을
  보여 주는 시각 증강 기호.
- 발화: 전사에 기대지 않는 음소별 발음 점수(D-GOP, 서버 추론을 켠 경우). 입모양 점수는 발음 점수에 섞지 않고 따로 보여 줍니다.
- 웹캠: MediaPipe 입모양 점수와 자체 립리딩 모델(ONNX)을 브라우저에서만 돌립니다. 영상은 서버로 보내지 않습니다.

**분석**
- 분석 탭: 학습 시간·정확도 추이, 활동 캘린더, 회차 히스토리, 전체 통계.
- 학습 효과 리포트(`/analysis/eval`): 학습곡선, 초기 대비 최근 향상도, 표준검사 사전(A)·사후(B) 비교, 교사·언어재활사용 인쇄 결과지.

## 기술 스택

| 영역 | 스택 |
|------|------|
| Backend | Python 3.11+, FastAPI(async), SQLAlchemy(SQLite/PostgreSQL), PyJWT, Anthropic Claude API(시나리오·대화 생성) |
| 서버 추론(선택) | torch(CPU) + transformers: D-GOP 발음채점(wav2vec2), 음성구동 아바타(WavLM). `backend/requirements-infer.txt` |
| Frontend | React 18, Vite, Tailwind CSS(Figma 디자인 토큰), Zustand, React Router, Framer Motion, Three.js, MediaPipe, onnxruntime-web |
| 배포 | Docker(멀티스테이지), Fly.io |

## 로컬 실행

### 1. 환경 변수

```bash
cp .env.example .env
```

`.env`에 `JWT_SECRET`(아무 긴 문자열)과 `ANTHROPIC_API_KEY`를 넣습니다. 키가 없어도 앱은 돌고, AI 시나리오·대화는
준비된 문장으로 대신합니다.

### 2. Backend (http://localhost:8080)

```bash
cd backend
pip install -r requirements.txt
python -m uvicorn main:app --reload --port 8080
```

API 문서는 http://localhost:8080/docs 에서 볼 수 있습니다. D-GOP 발음채점까지 로컬에서 켜려면 `requirements-infer.txt`와
torch를 더 설치하고 `DGOP_ALIGNER_ID`를 설정합니다(`.env.example`의 D-GOP 절, `DEPLOY.md` 9항).

### 3. Frontend (http://localhost:5173)

```bash
cd frontend
npm install
npm run dev
```

로그인 화면의 **둘러보기 (데모)** 를 누르면 회원가입 없이 데모 계정으로 들어갑니다.

### 4. 테스트

```bash
cd backend && python -m pytest -q      # 백엔드
cd frontend && npm test                # 프론트(node --test)
cd frontend && npx vite build          # 프로덕션 빌드 확인
```

## Docker로 실행

```bash
docker build -t liplab .
docker run -p 8080:8080 -e JWT_SECRET="your-secret-key" -e ANTHROPIC_API_KEY="your-api-key" liplab
```

앱은 http://localhost:8080 에서 열립니다. `docker-compose up --build`도 됩니다.

## 배포(Fly.io)

두 앱을 나눠 운영합니다. 자세한 절차와 확인 방법은 [DEPLOY.md](DEPLOY.md)에 있습니다.

| 앱 | 설정 | 용도 |
|----|------|------|
| `liplab` | `fly.toml` | 전시용. 서버 추론 없이(`WITH_ML=0`) 가볍게 돈다. 바꿀 때는 팀이 먼저 정한다 |
| `liplab-dev` | `fly.dev.toml` | 개발 확인용. 서버 추론을 켠다(`WITH_ML=1`: D-GOP 발음채점·음성구동 아바타, shared-cpu 2개·4GB), 데모 계정만 전 단계 열림 |

```bash
fly deploy -c fly.dev.toml -a liplab-dev --remote-only    # 개발 서버
```

## API 엔드포인트(주요)

전체 목록은 `/docs`(FastAPI 자동 문서)에서 봅니다.

- 인증: `POST /api/auth/register` · `POST /api/auth/login` · `POST /api/auth/demo` · `GET /api/auth/me`
- 커리큘럼: `GET /api/curriculum/stages` · `POST /api/curriculum/track` · `POST /api/curriculum/recognition` · `POST /api/curriculum/word-answer`
- 발화: `GET /api/speak/curriculum` · `POST /api/speak/assess` · `POST /api/speak/skip`
- 연습·채점: `GET /api/viseme` · `GET /api/scenario` · `POST /api/progress` · `POST /api/score` · `POST /api/conversation`
- 복습: `GET /api/review/due` · `GET /api/review-sentences` · `GET/POST /api/bookmarks`
- 분석: `GET /api/analysis/overview` · `GET /api/calendar/activities` · `GET /api/statistics` · `GET /api/eval/summary`
- 시스템: `GET /health`

## 프로젝트 구조

```
backend/
  main.py            FastAPI 엔드포인트(인증·커리큘럼·채점·대화·복습·분석)
  curriculum.py      독화 커리큘럼 콘텐츠(순수 데이터·함수)
  engine.py          한국어 → 비심 변환, 동시조음
  scoring.py         음운론적 유사도 채점
  dgop*.py           전사 비의존 발음채점(D-GOP)
  audio2face.py      음성구동 아바타(음성 → 블렌드셰이프)
  analytics.py       분석 탭 집계(회차·연속 학습·배지)
  llm_service.py     Claude 기반 시나리오·대화 생성
frontend/src/
  App.jsx            라우팅, 로그인 게이트, 단계 잠금 가드
  components/        AppShell(Figma 셸), 3D 아바타, 웹캠, 로딩 화면 등
  pages/             학습 경로·레슨·탭 화면
  lib/               채점 색, 립리딩 모델, 상대 날짜 등 보조 함수(node --test)
docs/                보고서 메모, 파일럿 문서, 축별 검증 기록
scripts/             평가·데이터 준비 스크립트
```

## 비심(Viseme) 분류 체계(15단계)

1. **양순음** (ㅂ, ㅃ, ㅍ, ㅁ) - 입술 닫힘
2. **개방 모음** (ㅏ, ㅐ, ㅑ, ㅒ) - 턱 벌림
3. **전설 모음** (ㅣ, ㅔ, ㅖ) - 입술 좌우 벌림
4. **원순 모음** (ㅗ, ㅛ, ㅜ, ㅠ) - 입술 둥글게
5. **중설 모음** (ㅓ, ㅕ, ㅡ) - 중립 입모양
6. **치경음** (ㄷ, ㄸ, ㅌ, ㄴ, ㄹ, ㅅ, ㅆ) - 혀끝이 잇몸
7. **연구개음** (ㄱ, ㄲ, ㅋ, ㅇ) - 입 약간 벌림
8. **성문음** (ㅎ) - 목구멍 발음
9. **이중모음** (ㅘ, ㅙ, ㅚ, ㅝ, ㅞ, ㅟ, ㅢ) - 연속 전환
10. **경구개음** (ㅈ, ㅉ, ㅊ) - 혀와 입천장
11-13. **전환 상태** - 동시조음 모델링
14. **휴지기** - 침묵/공백
15. **중립** - 알 수 없는 상태

## 2기 고도화(K-AI)

계획서 「멀티모달 발음·독화 평가를 중심으로 한 LIPLAB 고도화」의 축 A~K를 통합 브랜치 `integrate/2026-09-23`에서 진행합니다.
축별로 제품에 들어간 것, 실측 수치, 한계는 [docs/고도화_현황_팀공유.md](docs/고도화_현황_팀공유.md)에, 보고서에 쓸 근거와 계획 대비
달라진 설계는 [docs/report-notes.md](docs/report-notes.md)에 있습니다. 예전 개발 기록은 [DEVELOPMENT_LOG.md](DEVELOPMENT_LOG.md)입니다.

AI Hub 데이터(538·608)는 재배포할 수 없어 앱에 넣지 않습니다(앱의 예시 음성은 합성 음성). 공개 자원 묶음도 AI Hub에서
나온 자모 시각유사도는 기본으로 빼고, `LIPLAB_PUBLISH_DATA_DERIVED=1`일 때만 넣습니다.

## 라이선스

MIT License

## 문의

[GitHub Issues](https://github.com/n1a2m3y4u5n/liplab/issues)

---

**LIPLAB** - 모두를 위한 독화 교육
