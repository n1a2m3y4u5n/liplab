# LIPLAB

**청각장애인·난청인을 위한 한국어 독화(입모양 읽기)·말하기 훈련 웹앱**

![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB) ![FastAPI](https://img.shields.io/badge/FastAPI-backend-009688) ![React](https://img.shields.io/badge/React-19-61DAFB) ![three.js](https://img.shields.io/badge/three.js-3D%20avatar-000000)

2026 K-AI Contents Award B트랙 대상 수상작 · 충남삼성고등학교 IT·공학 디플로마

LIPLAB은 3D 아바타의 입모양을 보고 한국어를 읽는 **독화 트랙**과, 소리 내어 말하고 음소 단위 점수를 받는 **말하기 트랙**으로
이루어진다. 입모양 인지에서 대화까지 단계를 밟아 올라가며, 학습 기록으로 시작 단계·출제·복습을 사람마다 맞춘다.

| 핵심 | 내용 |
|---|---|
| 한국어 입모양을 3D로 | 한국어 문장을 발음 규칙에 따라 비심(입모양 그룹) 열로 바꾸고 동시조음을 반영해 3D 두상으로 재생한다. 속도 조절과 투명 두상(혀·치아 노출)을 지원한다 |
| 안 보이는 소리를 기호로 | 입모양이 같은 소리(ㅂ·ㅃ·ㅍ·ㅁ 등)는 기식·긴장·비음으로만 갈린다. 이 자질에만 최소 시각 기호를 붙이고, 숙달하면 기호가 흐려진다 |
| 전사에 기대지 않는 발음 평가 | 목표 문장을 아는 상태에서 음소별 발음 정확도(D-GOP)를 계산한다. 음성인식이 무너지는 발화에서도 음소 단위 점수를 낸다 |
| 근거 있는 개인화 | 적응형 배치검사(EAP 능력 추정), 이동 평균 숙달 판정, 입모양별 지식추적을 가상 학습자 시뮬레이션으로 사전 기준을 세워 검증했다 |

> 작업을 이어받는다면 [STATUS.md](STATUS.md)부터 읽는다. 축별 현황은 [docs/고도화_현황_팀공유.md](docs/고도화_현황_팀공유.md)에 있다.

---

## 목차

- [기능](#기능)
- [연구·실험 단계 기능](#연구실험-단계-기능)
- [주요 검증 결과](#주요-검증-결과)
- [기술 구조](#기술-구조)
- [저장소 구조](#저장소-구조)
- [로컬 실행](#로컬-실행)
- [테스트](#테스트)
- [배포](#배포)
- [문서 안내](#문서-안내)
- [데이터와 라이선스 고지](#데이터와-라이선스-고지)
- [팀과 문의](#팀과-문의)

---

## 기능

### 독화 트랙(5단계)

직전 단계를 숙달해야 다음 단계가 열린다. 잠금은 학습 경로 화면, 라우트 가드, 시나리오 시작 버튼, 서버 기록에서 함께 적용된다.

| 단계 | 내용 | 방식 |
|---|---|---|
| 0. 입문·배치 | 독화 소개, 시작 단계 정하기 | 트랙 선택 또는 적응형 배치검사 |
| 1. 입모양 인지 | 10개 입모양 그룹 익히기 | 아바타 입모양을 보고 4지선다, 최소대립 짝 미리보기 |
| 2. 음절·단어 | 최소대립쌍 단어 독화 | 서버가 입모양이 똑같은 오답(동구형이음)을 빼고, 진도에 따라 보기 난이도를 올린다 |
| 3. 문장(상황별) | 상황별 문장 독화, 문맥 추론 | 4지선다·주관식·서술형. 문맥 추론은 입모양이 비슷한 후보(밥·맘·팝) 중 문맥에 맞는 말을 고른다 |
| 4. 대화 실전 | AI 상대와 대화하며 읽기 | 상대 발화를 읽고 적으면 입모양 기준 유사도로 이해도를 채점 |

- **채점.** 입모양 기준 자모 유사도(같은 입모양 무리는 부분 점수)와 우연 보정 정렬을 쓴다. 객관식은 정확 일치로 채점한다
  ([docs/scoring-v2.md](docs/scoring-v2.md)).
- **혼동 진단.** 틀린 답을 자모 단위로 비교해 어떤 입모양을 헷갈렸는지 보여 준다.

### 말하기 트랙(6단계)

청각장애 음성재활에서 쓰는 Ling 발화 발달 단계를 한국어에 맞게 옮겼다.

| 단계 | 목표 | 판정 |
|---|---|---|
| 0. 발성 | 유성음을 목표 길이 이상 안정적으로 | 가장 길게 이어 낸 소리의 길이, 크기 |
| 1. 운율 조절 | 크게·작게·길게·올리기·내리기 | 크기·길이·음높이(반음 단위) 지표 |
| 2. 모음 | 모음 조음 | 음소 점수 |
| 3. 자음 | 자음 조음 | 음소 점수, 목표 자모를 맞혔는지 확인 |
| 4. 음절·단어 | 단어 명료도 | 음소 점수 |
| 5. 문장·억양 | 문장 명료도와 문장 끝 억양 | 음소 점수, 끝 음높이 방향 판정([docs/sentence-intonation.md](docs/sentence-intonation.md)) |

- **발음 평가(D-GOP).** 서버 추론을 켜면 자체 학습한 정렬기·채점기로 음소별 발음 정확도를 계산한다. 끄면 음성인식(faster-whisper)
  전사와 음운 유사도로 채점한다. 입모양 점수는 발음 점수에 섞지 않고 따로 보여 준다.
- **코칭.** 약하게 잡힌 음소마다 조음 위치·방법을 설명하는 문장을 준다(규칙 문장, API 키가 있으면 LLM 문장).

### 3D 아바타

- Character Creator 두상(ARKit 블렌드셰이프)에 한국어 → 비심 변환 결과를 프레임 전환 시간·이징과 함께 재생한다.
- 발음 규칙(연음, ㅎ 탈락, 받침 중화, ㄴ 첨가 등)과 숫자 읽기(3시 → 세 시, 5,000원 → 오천 원)를 입모양에 반영한다.
- 속도 조절(2배속이 문장 낭독의 음절 속도에 가깝다), 투명 두상, 거울 모드, 한 화면 여러 아바타(다자 대화).
- 3D를 쓸 수 없는 기기에서는 2D 입모양 그림으로 대체한다.
- 서버 추론을 켜면 음성에서 바로 입모양을 만드는 음성구동 아바타(동결 WavLM + BiGRU, 20화자 학습)를 쓴다.

### 평가와 개인화

| 기능 | 방식 | 근거 문서 |
|---|---|---|
| 적응형 배치검사 | 문항마다 EAP 사후분포로 세 시작 단계의 확률을 구해, 최소 5문항 뒤 한 단계가 0.85 이상이면 끝내고 아니면 12문항까지 낸다 | [assessment-design](docs/assessment-design.md) |
| 사전·사후 표준검사 | 난이도를 맞춘 동형 폼 A·B(각 24문항), 교사·언어재활사용 인쇄 결과지 | [assessment-design](docs/assessment-design.md) |
| 숙달 판정 | 편향 보정 지수 이동 평균. 초반 실패가 끝까지 남는 누적 정답률보다 거짓 숙달과 지연이 모두 적다 | [mastery-ewma](docs/mastery-ewma.md) |
| 지식추적 | 입모양 그룹별 숙달도를 베타-이항 사후평균과 최근 오답 감쇠로 추정해 약점 입모양 순위, 문맥 추론 출제, 시나리오 표적에 쓴다 | `backend/knowledge_tracing.py` |
| 시각 증강 기호 | 기식(ㅋㅌㅍㅊㅎ)·긴장(ㄲㄸㅃㅆㅉ)·비음(ㄴㅁㅇ)에 기호를 붙이고, 해당 입모양 숙달도가 오르면 점진적으로 흐린다 | [cue-overlay](docs/cue-overlay.md) |
| 간격 반복 복습 | 틀린 문장을 복습 큐에 예약하고 오늘의 복습으로 다시 낸다 | `backend/srs.py` |

### 연습·복습·분석

- **연습 탭.** 상황별 시나리오(상황 직접 입력 가능), 다자 대화(2~4명), 자유 발화, 수어 함께 보기(국립국어원 한국수어사전 연결),
  엔드리스 학습, 입모양 교실(웹캠 따라 하기·조음 교정).
- **복습 탭.** 오늘의 복습, 틀린 문장·북마크 다시 풀기, 말하기 복습.
- **분석 탭.** 학습 시간·정확도 추이(문항 유형 구성 변화를 보정), 활동 캘린더, 입모양 혼동 지도, 회차 기록.
- **학습 효과 리포트**(`/analysis/eval`). 학습곡선, 유형별 초기 대비 최근 변화, 숙달 도달 시행수, 사전·사후 비교
  ([docs/eval-metrics.md](docs/eval-metrics.md)).

## 연구·실험 단계 기능

아래는 코드에 있지만 제품 판정에 쓰지 않거나, 성능이 제한적이어서 참고용으로 두는 것이다.

| 기능 | 현재 상태 |
|---|---|
| 웹캠 입모양 채점(MediaPipe), 자체 립리딩 모델(ONNX) | 브라우저 안에서만 돌고 영상은 서버로 보내지 않는다. 립리딩 모델은 처음 보는 사람에게 4지 우연 수준이라 참고용이다 |
| 모음 포먼트 교정, 성도 단면(VocalTractLab) | 입모양 교실에서 쓰는 조음 교정 도구. 성도 단면은 추정 혀 모양이며 학습자 음성에서 역추정한 것이 아니다 |
| 소리·입모양 융합 채점 | 판별력을 낮춰 채점에서 뺐다. `LIPLAB_AV_FUSION=1`일 때만 연구용으로 켠다 |
| 비음 추정 | 연구 빌드에서만 표시. 실제 화자 영상에서 비음 음절을 가르지 못해(음절 AUC 0.49) 제품에서는 껐다 |
| 촬영 영상 위 기호 | 연구용 페이지 `/lab/cue-video`. 공개 화면에 쓰려면 자체 촬영 영상이 필요하다 |

## 주요 검증 결과

수치는 모두 저장소의 문서에 원자료와 사전 기준이 함께 적혀 있다. 시뮬레이션 결과는 실제 학습자 파일럿 전의 값이다.

| 항목 | 결과 | 자료 | 출처 |
|---|---|---|---|
| D-GOP와 전사 정확도의 상관 | 0.986 | AI Hub 538, 합성 저하 포함 | [고도화 현황](docs/고도화_현황_팀공유.md) |
| 자체 채점 모델 재검 | 강도 순서 +3.8%p [2.3, 5.5], 사전 관문 통과 | 538 새 20화자 | [scorer-selftrain](docs/scorer-selftrain.md) |
| 실제 청각장애 발화 분리도 | 0.892 → 0.933(자체 모델) | AI Hub 608, 27명 669문장 | [고도화 현황](docs/고도화_현황_팀공유.md) |
| 독화 이해 채점 v2 | 무관한 문장 46.9 → 3.3점, 말을 덧붙인 답 100 → 42.3점 | 사전등록 시험 절반 | [scoring-v2](docs/scoring-v2.md) |
| 배치검사 시작 단계 일치 | 77.7 → 80.7%(평균 7.78문항) | 가상 학습자 시뮬레이션 | [assessment-design](docs/assessment-design.md) |
| 1·2단계 숙달 판정 | 거짓 숙달 12.4 → 6.5%, 숙달 지연 39 → 28시행 | 가상 학습자 시뮬레이션 | [mastery-ewma](docs/mastery-ewma.md) |
| 문장 끝 억양 판정 | 예/아니오 의문문 대 평서문 AUC 0.540 → 0.670 | 538 확인 절반 28명 | [sentence-intonation](docs/sentence-intonation.md) |

## 기술 구조

```
브라우저 (React + Vite + three.js)
  ├─ 3D 아바타 재생, 시각 증강 기호, 녹음·음높이 추정
  └─ 웹캠 입모양 채점(MediaPipe), 립리딩(onnxruntime-web)   ← 영상은 기기 밖으로 나가지 않음
        │  REST (/api/*)
        ▼
FastAPI 백엔드 (Python, SQLAlchemy + SQLite 기본, PostgreSQL 선택)
  ├─ 한국어 → 비심 변환·발음 규칙(engine.py), 채점, 커리큘럼·숙달·잠금
  ├─ 배치검사·표준검사, 지식추적, 간격 반복, 분석 집계
  ├─ 음성인식 전사 경로(faster-whisper)
  ├─ LLM(Claude): 상황 문장·대화 턴·코칭·수어 번역. 키가 없거나 하루 한도를 넘으면 저장 문장·대체 대사·규칙 코칭
  └─ 서버 추론(선택, WITH_ML=1): D-GOP 정렬기·채점기(int8), 음성구동 아바타 백본
```

| 영역 | 스택 |
|---|---|
| 프론트엔드 | React 19, Vite 5, Tailwind CSS, Zustand, React Router, Framer Motion, three.js(@react-three/fiber), MediaPipe, onnxruntime-web |
| 백엔드 | Python 3.11+, FastAPI(async), SQLAlchemy 2, python-jose(JWT), faster-whisper, Anthropic SDK |
| 서버 추론(선택) | torch(CPU) + transformers, `backend/requirements-infer.txt` |
| 배포 | Docker(멀티스테이지), Fly.io |

## 저장소 구조

```
backend/
  main.py               FastAPI 엔드포인트(인증·커리큘럼·채점·대화·복습·분석)
  curriculum.py         독화 커리큘럼 콘텐츠(순수 데이터·함수)
  speak_curriculum.py   말하기 6단계 콘텐츠와 판정
  engine.py             한국어 → 비심 변환, 발음 규칙, 동시조음
  scoring.py            독화 이해 채점
  dgop*.py, ctc_align.py 전사 비의존 발음 평가(D-GOP)
  assessment.py         배치검사·사전·사후 표준검사
  knowledge_tracing.py  입모양별 지식추적
  cue_overlay.py        시각 증강 기호
  audio2face.py         음성구동 아바타
  llm_service.py, llm_budget.py  LLM 생성과 하루 호출 한도
  test_*.py             백엔드 테스트(pytest)
frontend/src/
  App.jsx               라우팅, 로그인 게이트, 단계 잠금 가드
  pages/                학습 경로·레슨·연습·복습·분석 화면
  components/           3D 아바타, 웹캠, 기호, 성도 단면 등
  lib/                  채점 색, 음높이, 입모양 타이밍 등 보조 함수(*.test.mjs)
docs/                   설계 근거, 실험 기록, 파일럿 문서
scripts/                평가·시뮬레이션·데이터 준비 스크립트
release/                한국어 독화 표준 리소스 공개 묶음
hardware/               촉각(타도마) 얼굴 모형 펌웨어
```

## 로컬 실행

필요한 것: Python 3.11 이상, Node.js 18 이상. Anthropic API 키는 선택이다.

### 1. 환경 변수

```bash
cp .env.example .env
```

`.env`에 `JWT_SECRET`(임의의 긴 문자열)을 넣는다. `ANTHROPIC_API_KEY`가 없어도 앱은 동작하며, AI 시나리오·대화는 준비된 문장으로 대신한다.

### 2. 백엔드 (http://localhost:8080)

```bash
cd backend
pip install -r requirements.txt
python -m uvicorn main:app --reload --port 8080
```

API 문서는 http://localhost:8080/docs 에서 볼 수 있다.

### 3. 프론트엔드 (http://localhost:5173)

```bash
cd frontend
npm install
npm run dev
```

개발 서버는 `/api` 요청을 8080으로 넘긴다. 로그인 화면의 **둘러보기(데모)** 를 누르면 가입 없이 데모 계정으로 들어간다.

macOS/Linux는 `scripts/setup.sh`, Windows는 `scripts/setup.ps1`로 1~3의 설치를 한 번에 할 수 있다([QUICKSTART.md](QUICKSTART.md)).

### Docker

```bash
JWT_SECRET=<임의의 긴 문자열> docker-compose up --build
```

http://localhost:8080 에서 열린다. `JWT_SECRET`을 주지 않으면 compose가 시작하지 않는다.

### 서버 추론(선택)

D-GOP 발음 평가와 음성구동 아바타를 로컬에서 켜려면 `backend/requirements-infer.txt`와 torch를 더 설치하고 체크포인트 경로를
설정한다. 체크포인트는 저장소에 없다. 설정은 `.env.example`의 D-GOP 절과 [DEPLOY.md](DEPLOY.md) 9항을 따른다.

## 테스트

```bash
cd backend && pip install pytest && python -m pytest -q   # 백엔드
cd frontend && npm test                                   # 프론트엔드(node --test)
cd frontend && npx vite build                             # 프로덕션 빌드 확인
```

2026-09-28 기준 백엔드 398개, 프론트엔드 126개가 통과하고 프로덕션 빌드가 통과한다.

## 배포

Fly.io에 두 앱을 나눠 운영한다. 절차와 확인 방법은 [DEPLOY.md](DEPLOY.md)에 있다.

| 앱 | 설정 | 용도 |
|---|---|---|
| `liplab` | `fly.toml` | 전시용. 서버 추론 없이(`WITH_ML=0`) 동작한다. 배포는 팀 승인 뒤에만 한다 |
| `liplab-dev` | `fly.dev.toml` | 개발 확인용. 서버 추론을 켠다(`WITH_ML=1`, shared-cpu 2개·4GB) |

```bash
fly deploy -c fly.dev.toml -a liplab-dev --remote-only   # 개발 서버
```

옵션 없는 `fly deploy`는 전시앱을 덮어쓰므로 쓰지 않는다. LLM 하루 한도, 채점 대기열 상한, 방화벽 연결 절차는
[docs/ddos-firewall.md](docs/ddos-firewall.md)에 있다.

## 문서 안내

| 문서 | 내용 |
|---|---|
| [STATUS.md](STATUS.md) | 지금 진행 상황과 다음 작업 |
| [docs/고도화_현황_팀공유.md](docs/고도화_현황_팀공유.md) | 2기 고도화 축 A~K별 제품 반영, 실측, 한계 |
| [QUICKSTART.md](QUICKSTART.md) | 빠른 시작과 문제 해결 |
| [DEPLOY.md](DEPLOY.md) | 배포, 서버 추론 설정, 콜드 스타트 |
| [CLAUDE.md](CLAUDE.md) | 기여자용 구조 설명(커리큘럼·잠금 규칙·컨벤션) |
| [docs/assessment-design.md](docs/assessment-design.md) | 배치검사·표준검사 설계와 실증 |
| [docs/mastery-ewma.md](docs/mastery-ewma.md) | 숙달 판정 이동 평균 |
| [docs/scoring-v2.md](docs/scoring-v2.md) | 독화 이해 채점 v2 |
| [docs/scorer-selftrain.md](docs/scorer-selftrain.md) | 발음 채점 모델 자체 학습과 재검 |
| [docs/sentence-intonation.md](docs/sentence-intonation.md) | 문장 끝 억양 판정 |
| [docs/cue-overlay.md](docs/cue-overlay.md) | 시각 증강 기호 설계 |
| [docs/ddos-firewall.md](docs/ddos-firewall.md) | 요청 폭주·비용 대비 |
| [docs/report-notes.md](docs/report-notes.md) | 보고서용 근거와 계획 대비 달라진 설계 |
| [docs/pilot/](docs/pilot/) | 파일럿 운영 문서(동의서, 점검표) |

## 데이터와 라이선스 고지

- **AI Hub 데이터.** 학습·검증에 쓴 AI Hub 데이터(538 립리딩, 608 청각장애 발화)의 원자료(영상·음성·전사)는 재배포할 수 없어
  저장소와 앱에 포함하지 않는다. 앱의 예시 음성은 합성 음성이다. 538에서 계산한 자모 시각 유사도는 공개 자원 묶음에서 기본으로
  빼며, `LIPLAB_PUBLISH_DATA_DERIVED=1`일 때만 넣는다.
- **모델 체크포인트.** 발음 채점·음성구동 아바타 체크포인트와 데이터베이스 파일은 저장소에 없다.
- **수어.** 수어 함께 보기는 국립국어원 한국수어사전(공공데이터포털, 공공누리 출처표시)의 표제어 정보와 영상 연결을 쓴다.
- **공개 자원 묶음.** `release/korean-speechreading-resources-1.3.0/`(한국어 독화 표준 리소스)은 같은 폴더의
  [LICENSE.md](release/korean-speechreading-resources-1.3.0/LICENSE.md)에 적힌 CC BY 4.0을 따른다.

## 팀과 문의

충남삼성고등학교 IT·공학 디플로마

| 이름 | 역할 |
|---|---|
| 남윤수 | 팀장 · 개발 |
| 황성주 | UI 디자인 · 개발 |
| 염우진 | 개발 |
| 나현빈 | 개발 |
| 최윤건 | 타도마 기능 개발 |

문의: namyunsu1001@naver.com · [GitHub Issues](https://github.com/n1a2m3y4u5n/liplab/issues)
