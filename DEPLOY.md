# LIPLAB 배포 가이드

## 빠른 시작 체크리스트

### ✅ 배포 전 준비사항

1. **Anthropic API 키 발급**
   - https://console.anthropic.com/ 접속
   - API 키 생성 (Claude 3.5 Sonnet 사용 권한 필요)

2. **환경 변수 준비**
   ```bash
   JWT_SECRET=<강력한-랜덤-문자열>
   ANTHROPIC_API_KEY=<발급받은-API-키>
   DATABASE_URL=<선택사항-PostgreSQL-URL>
   ```

3. **Docker 설치 확인**
   ```bash
   docker --version
   ```

4. **Fly.io 계정 생성** (프로덕션 배포 시)
   - https://fly.io/app/sign-up

---

## 로컬 Docker 테스트

### 1. 빌드

```bash
cd liplab
docker build -t liplab:latest .
```

### 2. 실행

```bash
docker run -d \
  --name liplab-test \
  -p 8080:8080 \
  -e JWT_SECRET="test-secret-key-change-in-production" \
  -e ANTHROPIC_API_KEY="your-api-key" \
  -e DATABASE_URL="sqlite+aiosqlite:///./liplab.db" \
  liplab:latest
```

### 3. 확인

브라우저에서 http://localhost:8080 접속

### 4. 로그 확인

```bash
docker logs -f liplab-test
```

### 5. 중지 및 제거

```bash
docker stop liplab-test
docker rm liplab-test
```

---

## Fly.io 프로덕션 배포

### Phase 1: 초기 설정

#### 1-1. Fly CLI 설치

**macOS/Linux:**
```bash
curl -L https://fly.io/install.sh | sh
```

**Windows (PowerShell):**
```powershell
iwr https://fly.io/install.ps1 -useb | iex
```

#### 1-2. 로그인

```bash
fly auth login
```

#### 1-3. 앱 생성

```bash
cd liplab
fly launch
```

프롬프트 응답:
- **App name**: `liplab` (또는 원하는 이름)
- **Region**: `nrt` (Tokyo) 또는 가까운 리전
- **PostgreSQL**: `Yes` (권장) 또는 `No` (SQLite 사용)
- **Deploy now**: `No` (환경 변수 설정 후 배포)

### Phase 2: 데이터베이스 설정 (PostgreSQL 선택 시)

#### 2-1. PostgreSQL 앱 생성

```bash
fly postgres create
```

설정:
- Name: `liplab-db`
- Region: 앱과 동일한 리전
- Configuration: Development (무료)

#### 2-2. 데이터베이스 연결

```bash
fly postgres attach liplab-db --app liplab
```

이 명령은 자동으로 `DATABASE_URL` 환경 변수를 설정합니다.

### Phase 3: 환경 변수 설정

```bash
# JWT Secret (강력한 랜덤 문자열 생성)
fly secrets set JWT_SECRET="$(openssl rand -base64 32)" --app liplab

# Anthropic API Key
fly secrets set ANTHROPIC_API_KEY="your-anthropic-api-key-here" --app liplab
```

**Windows에서 랜덤 키 생성:**
```powershell
$bytes = New-Object Byte[] 32
[Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
$secret = [Convert]::ToBase64String($bytes)
fly secrets set JWT_SECRET="$secret" --app liplab
```

### Phase 4: 배포

```bash
fly deploy --app liplab
```

빌드 및 배포 과정:
1. Dockerfile 빌드 (5-10분 소요)
2. 이미지 푸시
3. VM 생성 및 실행
4. 헬스 체크 확인

### Phase 5: 배포 확인

#### 5-1. 상태 확인

```bash
fly status --app liplab
```

#### 5-2. 로그 확인

```bash
fly logs --app liplab
```

#### 5-3. 앱 열기

```bash
fly open --app liplab
```

---

## 배포 후 운영

### 모니터링

#### 실시간 로그
```bash
fly logs --app liplab -f
```

#### 메트릭 확인
```bash
fly dashboard liplab
```

### 스케일링

#### VM 개수 조정
```bash
# 인스턴스 2개로 증가
fly scale count 2 --app liplab

# 특정 리전에만 배포
fly scale count 1 --region nrt --app liplab
```

#### VM 크기 조정
```bash
# 메모리 1GB로 증가
fly scale memory 1024 --app liplab

# CPU 2개로 증가
fly scale vm shared-cpu-2x --app liplab
```

### 환경 변수 수정

```bash
# 목록 확인
fly secrets list --app liplab

# 추가/수정
fly secrets set KEY=VALUE --app liplab

# 삭제
fly secrets unset KEY --app liplab
```

### 데이터베이스 관리

#### PostgreSQL 접속
```bash
fly postgres connect -a liplab-db
```

#### 백업
```bash
# 자동 백업은 Fly.io가 관리
# 수동 백업
fly postgres backup --app liplab-db
```

#### 복원
```bash
fly postgres restore --app liplab-db --backup <backup-id>
```

### 롤백

#### 이전 버전으로 복구
```bash
# 릴리스 히스토리 확인
fly releases --app liplab

# 특정 버전으로 롤백
fly releases rollback <version> --app liplab
```

### SSH 접속

```bash
fly ssh console --app liplab
```

컨테이너 내부에서:
```bash
# 데이터베이스 확인
python -c "from database import engine; print(engine.url)"

# 로그 확인
tail -f /var/log/*.log

# 프로세스 확인
ps aux | grep uvicorn
```

---

## 커스텀 도메인 설정

### 1. 도메인 추가

```bash
fly certs add yourdomain.com --app liplab
```

### 2. DNS 레코드 설정

Fly.io가 제공하는 IP 주소를 도메인의 DNS 레코드에 추가:

```
Type: A
Name: @
Value: <fly-ip-address>
TTL: Auto
```

서브도메인 (예: app.yourdomain.com):
```
Type: CNAME
Name: app
Value: liplab.fly.dev
TTL: Auto
```

### 3. 인증서 확인

```bash
fly certs show yourdomain.com --app liplab
```

---

## 비용 최적화

### 무료 티어 활용

Fly.io 무료 티어:
- 최대 3개 VM (shared-cpu-1x, 256MB RAM)
- 월 160GB 아웃바운드 트래픽
- PostgreSQL 3GB 스토리지

### Auto-scaling 설정

`fly.toml`에서:
```toml
[http_service]
  auto_stop_machines = true
  auto_start_machines = true
  min_machines_running = 0  # 트래픽 없으면 0으로
```

### 비활성화 시 중지

```bash
fly scale count 0 --app liplab
```

재시작:
```bash
fly scale count 1 --app liplab
```

---

## 트러블슈팅

### 빌드 실패

**증상**: Docker 빌드 중 오류
```bash
Error: failed to build image
```

**해결**:
1. 로컬에서 빌드 테스트
   ```bash
   docker build -t liplab .
   ```
2. 빌드 로그 확인
   ```bash
   fly logs --app liplab
   ```

### 헬스 체크 실패

**증상**: VM이 계속 재시작됨
```bash
Health check failed
```

**해결**:
1. `/health` 엔드포인트 확인
   ```bash
   curl https://liplab.fly.dev/health
   ```
2. 타임아웃 증가 (`fly.toml`):
   ```toml
   [[http_service.checks]]
     timeout = "10s"
     grace_period = "15s"
   ```

### 데이터베이스 연결 오류

**증상**: Database connection failed
```bash
sqlalchemy.exc.OperationalError
```

**해결**:
1. DATABASE_URL 확인
   ```bash
   fly secrets list --app liplab
   ```
2. PostgreSQL 상태 확인
   ```bash
   fly status --app liplab-db
   ```
3. 연결 테스트
   ```bash
   fly ssh console --app liplab
   python -c "from database import engine; import asyncio; asyncio.run(engine.connect())"
   ```

### Anthropic API 오류

**증상**: LLM scenario generation failed
```bash
anthropic.APIError
```

**해결**:
1. API 키 확인
   ```bash
   fly secrets list --app liplab | grep ANTHROPIC
   ```
2. API 사용량 확인 (https://console.anthropic.com/)
3. Fallback 동작 확인 (기본 문장 사용)

### 메모리 부족

**증상**: Out of memory errors
```bash
MemoryError or OOMKilled
```

**해결**:
```bash
# 메모리 증가
fly scale memory 512 --app liplab

# 또는 더 큰 VM으로 업그레이드
fly scale vm shared-cpu-2x --app liplab
```

---

## 보안 체크리스트

### ✅ 배포 전 확인사항

- [ ] JWT_SECRET은 강력한 랜덤 문자열인가?
- [ ] ANTHROPIC_API_KEY는 secrets로 설정했는가?
- [ ] DATABASE_URL에 비밀번호가 노출되지 않았는가?
- [ ] `.env` 파일이 `.gitignore`에 포함되었는가?
- [ ] CORS 설정이 프로덕션 도메인으로 제한되었는가?
- [ ] HTTPS가 강제 적용되는가? (`force_https = true`)
- [ ] 불필요한 디버그 로그가 비활성화되었는가?

### 추가 보안 강화

#### Rate Limiting 추가 (선택사항)

`main.py`에 추가:
```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

@app.post("/api/auth/login")
@limiter.limit("5/minute")
async def login(...):
    ...
```

#### CORS 제한

`main.py` 수정:
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://yourdomain.com"],  # 특정 도메인만
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
```

---

## 성능 최적화

### 1. CDN 설정 (선택사항)

Cloudflare를 프록시로 사용:
1. Cloudflare에 도메인 추가
2. DNS를 Cloudflare로 변경
3. Fly.io IP를 Cloudflare DNS에 추가
4. SSL/TLS: Full (strict)
5. Caching: Standard

### 2. 데이터베이스 인덱스

```python
# database.py에 인덱스 추가
class Progress(Base):
    __tablename__ = "progress"
    # ...
    __table_args__ = (
        Index('idx_user_created', 'user_id', 'created_at'),
    )
```

### 3. 시나리오 캐싱 확인

`llm_service.py`의 캐싱 로직이 활성화되어 있는지 확인

---

## 지원 및 문의

- Fly.io 문서: https://fly.io/docs/
- Fly.io 커뮤니티: https://community.fly.io/
- 프로젝트 이슈: GitHub Issues

---

**배포 성공을 기원합니다! 🚀**
