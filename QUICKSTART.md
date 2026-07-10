# LIPLAB 빠른 시작 가이드 ⚡ 

5분 안에 로컬에서 실행하기

## 전제 조건

- Python 3.11+
- Node.js 18+
- Anthropic API Key (https://console.anthropic.com/)

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

1. **회원가입**
   - 이메일, 사용자 이름, 비밀번호 입력
   - "회원가입" 버튼 클릭

2. **연습 시작**
   - 상황 선택 (예: 카페)
   - 난이도 선택 (1~5)
   - "연습 시작" 버튼 클릭

3. **입모양 보고 연습**
   - 애니메이션 재생
   - 입모양을 보고 문장 추측
   - 답변 입력 후 제출
   - 점수 및 피드백 확인

4. **진도 확인**
   - 대시보드에서 통계 확인
   - 취약 입모양 파악
   - 레벨 업 진행

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

### Viseme 이미지가 안 보임
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
- [DEPLOY.md](DEPLOY.md) - 프로덕션 배포 가이드

---

**즐거운 개발 되세요! 🎉**
