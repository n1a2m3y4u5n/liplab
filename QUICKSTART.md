# LIPLAB 빠른 시작 가이드

5분 안에 로컬에서 실행하기

## 전제 조건

- Python 3.11+
- Node.js 18+
- Anthropic API Key (https://console.anthropic.com/, 선택: 없으면 AI 시나리오·대화를 준비된 문장으로 대신한다)

---

## 방법 1: 자동 설정 스크립트 (권장)

### Windows
```powershell
cd liplab
.\scripts\setup.ps1
```

### macOS/Linux
```bash
cd liplab
chmod +x scripts/setup.sh
./scripts/setup.sh
```

스크립트 실행 후:
1. `.env` 파일 열기
2. `ANTHROPIC_API_KEY=your-key-here` 입력
3. 저장

---

## 방법 2: 수동 설정

### Step 1: 환경 변수 설정
```bash
cp .env.example .env
```

`.env` 파일 편집:
```
ANTHROPIC_API_KEY=your-anthropic-api-key-here
JWT_SECRET=any-random-string-for-development
```

### Step 2: Backend 설정
```bash
cd backend
pip install -r requirements.txt
cd ..
```

### Step 3: Frontend 설정
```bash
cd frontend
npm install
cd ..
```

---

## 실행

### Terminal 1: Backend
```bash
cd backend
python -m uvicorn main:app --reload --port 8080
```

### Terminal 2: Frontend
```bash
cd frontend
npm run dev
```

브라우저에서 http://localhost:5173 접속

---

## Docker로 실행 (가장 간단)

### 빌드 & 실행
```bash
docker-compose up --build
```

브라우저에서 http://localhost:8080 접속

### 중지
```bash
docker-compose down
```

---

## 첫 사용 가이드

1. **들어가기**
   - 로그인 화면에서 **둘러보기 (데모)** 를 누르면 가입 없이 데모 계정으로 들어간다.
   - 직접 쓰려면 **회원가입**(사용자명 2~50자, 비밀번호 6자 이상, 약관 동의).

2. **트랙 고르기**
   - 처음 들어오면 독화(입모양 읽기)와 발화(소리 내어 말하기) 중 하나를 고른다.
   - 자가진단(8문항)으로 시작 단계를 정할 수도 있다.

3. **학습 경로**
   - 학습 탭의 경로에서 지금 단계를 눌러 레슨을 시작한다.
   - 독화 레슨: 3D 아바타의 입모양을 보고 4지선다로 고른다(숫자 키 1~4). 발화 레슨: 마이크로 말하면 발음 점수가 나온다(서버 추론을 켜면 음소별 D-GOP 점수).
   - 직전 단계를 숙달하면 다음 단계가 열린다. 건너뛰기로 한 단계씩 먼저 열 수도 있다.

4. **복습과 분석**
   - 복습 탭: 틀린 문장·북마크·오늘의 복습.
   - 분석 탭: 학습 시간·정확도 추이, 활동 캘린더, 회차 히스토리, 학습 효과 리포트(사전·사후 검사).

---

## 문제 해결

### Backend가 실행되지 않음
```bash
# 가상환경 활성화 확인 (Python venv 사용 시)
cd backend
source venv/bin/activate  # macOS/Linux
.\venv\Scripts\Activate.ps1  # Windows

# 재설치
pip install -r requirements.txt
```

### Frontend가 실행되지 않음
```bash
cd frontend
rm -rf node_modules package-lock.json
npm install
```

### 2D 입모양 그림(3D를 못 쓰는 기기용)이 안 보임
```bash
cd frontend/public/visemes
python generate_placeholders.py
```

### API 키 오류
- `.env` 파일에 `ANTHROPIC_API_KEY`가 올바르게 설정되었는지 확인
- API 키에 사용 권한이 있는지 확인
- Backend를 재시작

---

## 다음 단계

- [README.md](README.md) - 전체 문서
- [STATUS.md](STATUS.md) - 지금 진행 상황
- [DEPLOY.md](DEPLOY.md) - 배포 가이드(전시앱 `liplab`, 개발 서버 `liplab-dev`)

