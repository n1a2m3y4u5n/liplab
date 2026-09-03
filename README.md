# LIPLAB - AI 기반 독화 훈련 플랫폼

청각장애인을 위한 인공지능 기반 독화(Speechreading) 훈련 플랫폼입니다.

## 주요 기능

- **15단계 정교한 Viseme 매핑**: 한국어 조음 음운론을 반영한 세밀한 입모양 분류
- **동시조음(Co-articulation) 모델링**: 자연스러운 입모양 전환 애니메이션
- **적응형 학습**: 사용자의 취약점을 분석하여 맞춤형 시나리오 생성
- **음운론적 유사도 채점**: 시각적으로 유사한 음소에 대한 부분 점수 제공
- **JWT 인증 및 학습 데이터 추적**: 개인별 진도 및 통계 관리

## 기술 스택

### Backend
- Python 3.11+
- FastAPI (비동기 웹 프레임워크)
- SQLAlchemy (ORM, SQLite/PostgreSQL 호환)
- G2P (한국어 발음 변환)
- Anthropic Claude API (시나리오 생성)
- PyJWT (인증)

### Frontend
- React 18
- Vite (빌드 도구)
- Tailwind CSS (스타일링)
- Zustand (상태 관리)
- React Router (라우팅)
- Framer Motion (애니메이션)

### Deployment
- Docker (멀티스테이지 빌드)
- Fly.io (프로덕션 배포)

## 로컬 개발 환경 설정

### 1. 환경 변수 설정

```bash
cp .env.example .env
```

`.env` 파일을 열어 다음 값들을 설정하세요:
- `ANTHROPIC_API_KEY`: Claude API 키 (https://console.anthropic.com/)
- `JWT_SECRET`: 강력한 랜덤 문자열

### 2. Backend 실행

```bash
cd backend
pip install -r requirements.txt
python -m uvicorn main:app --reload --port 8080
```

Backend는 http://localhost:8080 에서 실행됩니다.

### 3. Frontend 실행

새 터미널에서:

```bash
cd frontend
npm install
npm run dev
```

Frontend는 http://localhost:5173 에서 실행됩니다.

### 4. Viseme 이미지 생성 (선택사항)

```bash
cd frontend/public/visemes
python generate_placeholders.py
```

실제 입모양 이미지로 교체하려면 `frontend/public/visemes/1.png` ~ `15.png` 파일을 준비하세요.

## Docker로 실행

### 빌드

```bash
docker build -t liplab .
```

### 실행

```bash
docker run -p 8080:8080 \
  -e JWT_SECRET="your-secret-key" \
  -e ANTHROPIC_API_KEY="your-api-key" \
  liplab
```

앱은 http://localhost:8080 에서 접근 가능합니다.

## Fly.io 배포

### 1. Fly.io CLI 설치

```bash
# macOS/Linux
curl -L https://fly.io/install.sh | sh

# Windows (PowerShell)
iwr https://fly.io/install.ps1 -useb | iex
```

### 2. 로그인

```bash
fly auth login
```

### 3. 앱 생성 (최초 1회)

```bash
fly launch
```

프롬프트에서:
- App name: 원하는 이름 입력 (예: liplab-prod)
- Region: 가까운 리전 선택 (nrt = 도쿄)
- PostgreSQL 추가 여부: Yes 선택 (권장) 또는 No (SQLite 사용)

### 4. 환경 변수 설정

```bash
fly secrets set JWT_SECRET="your-super-secret-jwt-key-here"
fly secrets set ANTHROPIC_API_KEY="your-anthropic-api-key-here"
```

PostgreSQL을 사용하는 경우:
```bash
fly secrets set DATABASE_URL="postgresql+asyncpg://user:pass@host:port/db"
```

### 5. 배포

```bash
fly deploy
```

### 6. 앱 열기

```bash
fly open
```

### 배포 후 관리

```bash
# 로그 확인
fly logs

# 스케일 조정
fly scale count 2

# SSH 접속
fly ssh console

# 상태 확인
fly status
```

## API 엔드포인트

### 인증
- `POST /api/auth/register` - 회원가입
- `POST /api/auth/login` - 로그인
- `GET /api/auth/me` - 현재 사용자 정보

### 학습
- `GET /api/viseme?text={text}` - 텍스트를 Viseme 배열로 변환
- `GET /api/scenario?situation={situation}&level={level}` - 시나리오 생성
- `POST /api/progress` - 학습 결과 제출
- `GET /api/statistics` - 사용자 통계 조회

### 시스템
- `GET /health` - 헬스 체크

## 프로젝트 구조

```
liplab/
├── backend/
│   ├── main.py              # FastAPI 앱
│   ├── database.py          # SQLAlchemy 모델
│   ├── auth.py              # JWT 인증
│   ├── engine.py            # Viseme 변환 엔진
│   ├── llm_service.py       # Claude API 연동
│   ├── scoring.py           # 채점 알고리즘
│   └── requirements.txt     # Python 의존성
├── frontend/
│   ├── src/
│   │   ├── pages/          # 페이지 컴포넌트
│   │   ├── components/     # 재사용 컴포넌트
│   │   ├── store/          # Zustand 상태 관리
│   │   └── api.js          # API 클라이언트
│   ├── public/visemes/     # Viseme 이미지
│   └── package.json        # Node.js 의존성
├── Dockerfile              # 프로덕션 빌드
├── fly.toml               # Fly.io 설정
└── .env.example           # 환경 변수 템플릿
```

## Viseme 분류 체계 (15단계)

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

## 개발 로드맵

### 현재 버전 (v1.0)
- ✅ 15단계 Viseme 시스템
- ✅ Claude API 시나리오 생성
- ✅ 음운론적 채점 알고리즘
- ✅ JWT 인증 및 진도 추적
- ✅ 적응형 난이도 조정

### 향후 계획
- [ ] 실제 입모양 영상 데이터셋 통합
- [ ] 3D 아바타 렌더링 (Three.js)
- [ ] 음성 인식 연동 (발화 연습)
- [ ] 모바일 앱 (React Native)
- [ ] 다국어 지원 (영어, 일본어 등)
- [ ] 소셜 기능 (친구와 경쟁, 리더보드)

## 라이선스

MIT License

## 기여

이슈 및 PR을 환영합니다!

## 문의

프로젝트 관련 문의: [GitHub Issues](https://github.com/yourusername/liplab/issues)

---

**LIPLAB** - 모두를 위한 독화 교육

## 2기 고도화 (K-AI 콘텐츠 공모전)

계획서 「멀티모달 발음·독화 평가를 중심으로 한 LIPLAB 고도화」의 축 A~K 중, 데이터·GPU 없이
로컬에서 가능한 부분을 구현했다. 상세 개발 과정은 [DEVELOPMENT_LOG.md](DEVELOPMENT_LOG.md).

**완료 (로컬)**
- **G** 콘텐츠 대량화·개인화 — LLM 생성 + 비심 규칙 게이트 + 지식추적 개인화 + 사람 검수
- **J** 시각 증강 — 안 보이는 자질(기식·긴장·비음)을 시각 기호로 오버레이(큐드 스피치 재해석)
- **D** 웹캠 입모양 채점 — MediaPipe blendshape 코사인 채점, 개인 캘리브레이션, 영상 서버 전송 없음
- **B** 전사 비의존 D-GOP(로직) — 불확실성 보정으로 과신 방지 + 오디오·비주얼 후기 융합
- **C** 지각 자원(규칙) — 동구형이음 사전·독화 난이도 지수 공개(`docs/perceptual-resources.json`)
- **I** 디지털 독화 표준검사 — 난이도 통제 배치검사 + 음소별 오류 프로파일
- **K** 입술 너머 확장 단서 — 얼굴 전체(턱·볼·코) 보조 신호
- **H** 다자 대화 시나리오 독화 — 여러 화자 번갈아 말하기, 화자 식별 + 입모양 읽기
- 부가: OLKAVS 립리딩 데이터 전처리 파이프라인(`scripts/preprocess_olkavs.py`)

**Phase 2 (torch·GPU·데이터 필요)**: A 공유 백본+농인 발화 합성 · B 음향 추론(wav2vec2) ·
C 지각공간 임베딩 · D 자체 립리딩 모델 · E 조음 진단+성도 시뮬레이터 · F 실사·투명 아바타
