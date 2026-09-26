# LIPLAB 배포 가이드

> ⚠️ **전시앱 보호 — 반드시 읽을 것.** `fly deploy`(무옵션)와 `fly deploy --app liplab`는 **라이브 전시앱(`liplab.fly.dev`)을 덮어씁니다.**
> 이 문서의 예시 중 `--app liplab`은 전시앱 대상입니다. **기능 검증·개발 배포는 절대 전시앱에 하지 말고**, 반드시 dev 앱으로:
> ```bash
> fly deploy -c fly.dev.toml -a liplab-dev --remote-only   # develop/staging (liplab-dev.fly.dev)
> ```
> dev 앱 설정·확인 절차는 아래 "배포 전 준비사항"의 liplab-dev 항목(9항)에 있다. 전시앱 배포는 명시적 승인 후에만.
> `## Fly.io 프로덕션 배포` 아래의 `--app liplab` 예시(비밀키 교체, 스케일, 메모리 등)는 7월 전시앱 기준 옛 절차라 그대로
> 복사하지 않는다(예: `scale count 2`는 SQLite 볼륨을 나눠 쓰지 못하는 기계를 하나 더 만든다). 또 `.dockerignore`가
> `backend/models/`를 빼지 않아, 이 작업 폴더로 전시앱을 빌드하면 dev용 모델(약 0.7GB)이 이미지에 들어간다. 전시앱을 다시
> 배포해야 하면 먼저 그 폴더를 빌드 폴더 밖으로 옮긴다.

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

5. **의존성 보안 점검** (계획서 §4.9 ⑦)
   ```bash
   bash scripts/security-audit.sh   # pip-audit + npm audit(운영 의존성, high 이상)
   ```
   `SECURITY_AUDIT_OK`가 아니면 목록을 보고 올릴 수 있는 패키지를 올린다(`backend/requirements.txt`의 상한도 함께).
   9/24 점검: 운영 의존성 7건(high 2: axios·form-data)을 호환 범위 안에서 올렸다(`package-lock.json`만, axios 1.20.0,
   react-router-dom 6.30.6). 이 작업 폴더의 `node_modules`는 메인 체크아웃과 공유라 잠금 파일만 고쳤고(`npm audit fix
   --package-lock-only`), 배포 이미지는 `npm ci`로 새 잠금 파일을 따른다. 남은 2건(react-router 6의 moderate)은 7로 올려야
   풀린다. 하나는 사용자가 넣은 경로를 `<Link>`·`navigate`에 넘길 때의 열린 리디렉션인데 앱은 자체 목록의 경로만 넘기고,
   다른 하나는 서버 렌더링(SSR) 경로라 이 앱(브라우저 전용)에는 해당하지 않아 메이저 업그레이드는 미뤘다.
   파이썬(설치된 백엔드 환경을 pip-audit로 점검): `ecdsa`(python-jose가 끌어오는 것, 상류 수정판 없음)와 `pip` 자체뿐이다.
   토큰 서명은 HS256(HMAC)이라 `ecdsa`의 타원곡선 서명 경로를 쓰지 않고, `pip`은 이미지 빌드 도구라 실행 중인 앱과 무관하다.

6. **공개 전 확인**: 전시앱 `liplab.fly.dev`는 새 fly 앱으로만 시험하고 덮어쓰지 않는다. 처리방침의 개인정보
   보호책임자 연락처, `LIPLAB_UNLOCK_ALL`(전 단계 열기) 설정, 파일럿을 켤지(`LIPLAB_PILOT`)를 정한다.

7. **저장 데이터 암호화(계획서 §4.9 ①)**: fly 볼륨은 만들 때 `--no-encryption`을 주지 않으면 암호화된다. SQLite를
   볼륨에 둘 때는 `fly volumes list -a <새 앱>`의 ENCRYPTED 열이 true인지 확인하고, 확인한 뒤에만 처리방침에
   "암호화된 저장소에 보관"을 적는다(아직 적지 않았다).

8. **파일럿을 켤 때**: `docs/pilot-data-spec.md`의 보관 기간·파기 방식·동의 철회 절차를 정하고,
   기한이 되면 `scripts/pilot_retention.py`로 파기하고 대장을 남긴다. 켜기 전에 가명 비밀키 `LIPLAB_PILOT_SECRET`을
   `fly secrets set`으로 넣고 파기가 끝날 때까지 바꾸지 않는다. 기호 없는 집단을 두면 `LIPLAB_PILOT_NOCUE_COHORTS`도 정한다.
   파기 도구는 이미지에 `/app/scripts/pilot_retention.py`로 들어 있고, 대장은 기본으로 볼륨(`/data`)에 남는다.

9. **liplab-dev 서버 추론(9/24 코드 반영, 9/25 채점 모델을 자체 학습 모델로 바꾸고 int8로 4GB에 맞춤, 9/25 18:18 배포, 9/26 콜드 스타트 개선은 배포 전)**: `fly.dev.toml`은
   `WITH_ML=1`로 빌드해 D-GOP 발음채점과 음성구동 아바타(A4)를 서버에서 켠다. 전시앱 `fly.toml`은 바꾸지 않았다(기본값
   `WITH_ML=0`이라 이미지가 전과 같다).
   - 채점 모델(9/25): 자체 학습 정렬기·채점기(`DGOP_MODEL=ours`). 사전등록 독립 재검(538 새 20화자)을 통과해 공개 kresnik
     대신 쓴다(`docs/scorer-selftrain.md`). 체크포인트는 git에 없으므로 배포 전에 빌드 폴더에 있는지 확인한다:
     `ls -l backend/models/dgop_ours/*/model.int8.safetensors`(9/26부터 미리 변환한 int8 파일, 각 355MB). 없으면
     `rm -rf backend/models/dgop_ours && cp -cR ~/Downloads/liplab-lab/models/dgop_ours_2026-09-25_int8 backend/models/dgop_ours`
     (APFS 복제라 디스크를 더 쓰지 않는다. 먼저 지우지 않으면 폴더가 이미 있을 때 그 안에 하위 폴더로 들어가, 예전 fp32가 남은 채
     빌드되고 켜질 때마다 실행 중 변환을 한다. 빌드 기록의 `dgop_ours ok:`가 `file`인지 본다).
     fp32 원본(각 1.26GB)은 `liplab-lab/models/dgop_ours_2026-09-25`에 있고, int8 파일은
     `backend/.venv/bin/python scripts/export_int8.py <fp32 폴더> <출력 폴더> --wav <16kHz 음성>`으로 다시 만든다(실행 중 변환과
     비트 단위로 같은지 확인하고 다르면 실패한다). 체크포인트가 없으면 빌드가 멈추고(조용히 전사 경로로 떨어지지 않게), int8 파일은
     빌드 때 이미지의 torch·transformers로 한 번 올려 본다. 빌드 폴더 업로드가 약 0.7GB 늘어난다(fp32를 싣던 9/25는 2.5GB).
   - 이미지: torch CPU 휠 + transformers, 자체 정렬기·채점기, microsoft/wavlm-large(아바타 백본, 빌드 때 받음).
     kresnik은 `DGOP_MODEL=kresnik`일 때만 받는다. `HF_HUB_OFFLINE=1`. 9/25 이미지는 4.6GB였고, int8 파일로 바꾸면 약 1.8GB 준다.
   - int8(9/25 오후): `BACKBONE_QUANT=int8`이면 정렬기·채점기의 선형층 가중치를 int8로 두고 계산은 fp32로 한다
     (`backend/quant_int8.py`, 모델당 약 1.2GB → 0.4GB). 아바타 백본은 fp32 그대로다. 사전등록 점검(`liplab-lab/notes/int8_prereg_2026-09-25.md`)
     다섯 조건을 모두 통과했다: 재검 관문 재현(단조 비율 Δ +3.5%p [2.2, 5.0]), 538 2,400쌍 표시 점수 차 평균 0.20점(95백분위 0.7),
     608 실발화 669문장 평균 0.36점(95백분위 1.0), CPU·GPU 경로 차 최대 0.1점, 호스팅 점검 최대 3.15GB(채점 뒤 2.7GB).
   - 기계: shared-cpu 2개, 메모리 4GB(int8 덕분에 9/25 오전의 8GB·4CPU에서 되돌림). 자동 정지는 그대로라 쓰는 동안만 과금된다. 켜질 때
     `LIPLAB_WARMUP=1`이 모델 세 개를 뒤에서 미리 올린다. 모델이 오르기 전에 온 발음 요청은 그 자리에서 적재를 기다린다.
   - 채점: `DGOP_ALIGNER_ID`·`DGOP_SCORER_ID`가 이미지 안 체크포인트(`/app/models/dgop_ours/...`)를 가리키고, 앵커는
     `DGOP_CALIBRATION=/app/data/dgop_calibration_ours.json`(538 조건별 중앙값 86.0·54.5·30.4·8.2 → 90·72·58·40). D-GOP가
     주 경로이고 실패하면 전사 경로로 폴백한다. 입모양 점수는 채점에 섞지 않고 따로 보인다(`LIPLAB_AV_FUSION=1`이면 연구용 융합).
   - 되돌리기(공개 kresnik): `[build.args]`의 `DGOP_MODEL`을 `"kresnik"`으로, `[env]`는 `DGOP_ALIGNER_ID = "kresnik/wav2vec2-large-xlsr-korean"`만
     남기고(`DGOP_SCORER_ID`·`DGOP_CALIBRATION` 삭제, 앵커는 `dgop_calibration_kresnik.json` 자동) `BACKBONE_QUANT`도 지운다(모델이 하나라
     fp32로 4GB에 들어간다). int8만 끄려면 `BACKBONE_QUANT` 줄을 지우고 기계를 shared-cpu 4개·8GB로 올린다.
   - 음성구동 아바타 체크포인트 `backend/models/kr_a4_wavlm.pt`(9.5MB)도 git에 없다(.gitignore). 이 작업 폴더에 복사해 두었으니
     배포 전에 `ls backend/models/kr_a4_wavlm.pt`로 있는지만 확인한다. 없으면 아바타는 텍스트 비심으로 폴백한다.
   - 단계 잠금: `LIPLAB_UNLOCK_ALL=demo`라 둘러보기 데모 계정만 전 단계가 열리고 실사용·파일럿 계정은 숙달 순서대로다.
   - 시크릿(배포 전에): 콘텐츠 검수자 `fly secrets set LIPLAB_ADMIN_EMAILS=<이메일> -a liplab-dev`(없으면 검수 화면을 아무도
     못 쓴다). 가입 때 이메일 소유를 확인하지 않으므로, 운영자가 그 주소로 먼저 가입한 뒤에 넣는다(아직 가입하지 않은 주소를
     넣으면 누구든 그 주소로 가입해 운영자가 된다). 9/26부터 가입 이메일은 소문자로 저장하고 대소문자만 다른 주소는 막는다.
     검수 화면은 후보 파일(`data/curriculum/candidates_*.json`, git 제외)이 이미지에 없고 결정을 이미지 안에 써서 재시작하면
     사라지므로, 지금 서버에서는 쓸 수 없다. 검수는 로컬(`docs/content-routine.md`)에서 한다.
   - 배포 전 점검(9/25, RunPod 파드에서 이미지와 같은 의존성·torch CPU 2스레드, 실제 음성 3문장을 webm/opus로): 자체 모델은
     예열에서 세 모델이 모두 올라왔고(6.5초), 최대 메모리 5.0GB, 발음 채점 문장당 1.6~2.0초, 맞는 문장 88~93점, 다른 문장
     45~48점이었다. 같은 파드에서 kresnik 설정은 3.1GB, 0.9~1.2초, 맞는 문장 86~95점, 다른 문장 0~45점. 재검 600클립으로 넓혀도
     다른 문장이 65점을 넘은 경우는 두 모델 모두 없었다(`docs/scorer-selftrain.md` 5절). 새 가상환경에서 SQLAlchemy 2.1이
     greenlet을 빼 앱이 뜨지 않는 결함을 찾아 고쳤다(`sqlalchemy[asyncio]`, ba3f8a7). 9/24 점검(kresnik)에서는 아바타가
     torchaudio·librosa 없이 꺼지는 결함을 고쳤다(b7973dc). 도구 `liplab-lab/tools/pod/hostcheck.py`(`HC_ALIGNER`·`HC_SCORER`·
     `HC_CALIBRATION`), 결과 `liplab-lab/data/pod_runs/20260925_a39mpqnc24np42/hostcheck/`. 같은 날 오후 int8 점검(같은 방식,
     `BACKBONE_QUANT=int8`): 최대 3.15GB(모델을 int8로 바꾸는 순간), 채점 뒤 상주 2.7GB, 문장당 2.5~3.0초로 fp32(4.3GB, 2.4~2.9초)와
     점수가 같았다. 첫 시도는 변환 뒤에도 체크포인트 파일 매핑이 남아 6.2GB로 재졌고, 나머지 파라미터를 복사해 매핑을 끊도록
     고친 뒤 다시 쟀다. 결과 `liplab-lab/data/pod_runs/20260925_4aol7xkyf762yh/hc2/`.
   - 9/25 배포 결과(사용자 지시, 이미지 deployment-01M3BX59ZYQB7SBF5TR0QV30AH, 4.6GB, 빌드 컨텍스트 2.6GB): 기계 shared-cpu 2개·4GB,
     볼륨 liplab_data 1GB(암호화 켜짐 확인), 비밀키 JWT_SECRET·ANTHROPIC_API_KEY 있음. 켜진 뒤 정렬기·채점기 int8 적재 각 약 75초,
     아바타 백본 2.4초. 맞는 문장 84.1점·다른 문장 29.5점(맥 음성합성 문장, D-GOP 경로, 자체 앵커), 채점 2.4~2.8초.
     기계가 멈췄다 켜지면 첫 발음 채점은 적재가 끝날 때까지(약 1~2분) 기다린다.
   - 콜드 스타트(9/26 실측과 개선, 배포 전, 원자료 `liplab-lab/data/hosting_runs/20260926_liplab-dev_cold/`): 멈춘 기계를 깨우면
     앱 응답 10초, 정렬기·채점기 적재 각 76초(차례로), 아바타 백본은 적재 2.6초였지만 첫 아바타 요청이 76초 걸렸다(가중치를 파일
     매핑으로 올려 첫 추론 때 읽는다). 전부 준비되기까지 약 4분이다. 원인은 CPU가 아니라 루트 파일시스템 읽기로, 1.26GB를 76초에
     읽어 초당 약 17MB였다(fly 문서는 루트 파일시스템을 기계 종류와 상관없이 8MiB/s·2000 IOPS로 제한한다고 적는다). 같은 적재가
     파드에서는 모델당 1.6초였다. 세 가지를 고쳤다.
     (1) 일시정지: `auto_stop_machines = "suspend"`. 수동 시험(`fly machine suspend`)에서 4GB 기계가 8초 만에 일시정지됐고, 깨운 뒤
     앱 응답 0.9초, 첫 발음 채점 3.6초, 첫 아바타 3.1초였으며 올려 둔 모델이 그대로 있었다(적재 시각 유지). 요금은 멈춘 기계와 같이
     저장 공간만이다. fly 문서는 2GB 넘는 기계에는 권하지 않고(일시정지 시간이 길어서) 스냅샷 보존을 보장하지 않으며, 배포하면
     스냅샷을 버린다. 그때는 (2)·(3)이 콜드 스타트를 줄인다. 문제가 생기면 `"stop"`으로 되돌린다.
     (2) 미리 변환한 int8: 정렬기·채점기를 `model.int8.safetensors`(fp32의 28%)로 싣고 fp32를 읽지 않고 바로 올린다
     (`quant_int8.load_ctc`, 빌드 폴더에 int8 파일만 있으면 `BACKBONE_QUANT`와 상관없이 이 경로). 텐서 569개가 실행 중 변환과 모두
     같고 로짓 차이 0(무작위 3초·음성합성 문장), D-GOP 점수도 배포 서버와 같았다(맞는 문장 84.1, 다른 문장 29.5). 읽는 양으로 따지면
     적재가 모델당 약 21초로 줄 것으로 본다(배포 뒤 확인). 변환 순간의 메모리 최고치(9/25 점검 3.15GB)도 없어진다.
     (3) 예열이 아바타 백본까지 1초 무음으로 한 번 돌려 가중치를 미리 읽는다(`audio2face.warm`). 일시정지 스냅샷에도 들어간다.
     함께 고친 결함: `GET /api/backbone/status`가 적재 내내 잠금을 기다려, 적재 중에 부르면 서버 전체가 멈췄다(비동기 엔드포인트
     안의 동기 대기). 이제 바로 답하고 올리는 중인 모델을 `loading`에 보인다. 제품 화면은 이 주소를 부르지 않아 측정 때만 드러났다.
   - 배포(사용자 지시 뒤에만): `fly deploy -c fly.dev.toml -a liplab-dev --remote-only`. 확인은 `GET /api/backbone/status`에
     세 모델이 올라왔고 정렬기·채점기의 `quant`가 `int8`, `quant_from`이 `file`인지, 발음 연습 응답의 `assessment_method`가 `dgop`이고
     `dgop.calibration`이 자체 학습 앵커인지 본다. 메모리는 서버 프로세스(로그의 `Started server process [N]`)의 최고치를
     `fly ssh console -a liplab-dev -C "cat /proc/N/status"`의 VmHWM으로 보고 4GB 안(점검 최대 3.15GB)인지 본다.
     일시정지는 몇 분 쉰 뒤 `fly status -a liplab-dev`의 STATE가 `suspended`인지, 깨운 뒤 `load_seconds`·`loaded_at`이 그대로인지
     본다. 콜드 스타트 시간은 `liplab-lab/tools/cold_start_measure.sh`로 잰다.
     D-GOP를 끄려면 `WITH_ML`을 0으로 바꾸거나 `DGOP_ALIGNER_ID`를 지우고 다시 배포한다.
   - 9/26 배포 결과(사용자 지시, v9 19:47, 이미지 deployment-01M3EMZ4N7SQW835D0F5JDMT7W 2.9GB(9/25 4.6GB), 빌드 폴더 754MB,
     원자료 `liplab-lab/data/hosting_runs/20260926_liplab-dev_cold/`의 deploy1·resume2·resume3): 빌드 점검에서 int8 두 모델을 실제로
     올렸고, 켜진 뒤 정렬기·채점기가 int8 파일에서 바로 올라왔다(`quant_from: file`, 적재 각 21.8초·21.2초, 전에는 각 76초).
     예열이 끝나 모두 준비되기까지 켜진 뒤 2분 14초(전에는 약 4분). 첫 발음 채점 2.7초, 맞는 문장 84.1점으로 전과 같다.
     서버 프로세스 메모리 최고 2.40GiB(VmHWM), 채점 뒤 2.36GiB. 예열이 아바타 백본(1.26GB)을 읽는 동안(켜진 뒤 약 2분) 들어온 첫
     아바타 요청은 그 읽기를 함께 기다려 72초였고, 예열 뒤에는 1.8초였다.
     일시정지: 요청이 없으면 fly 프록시가 2.5~4분 뒤 스스로 일시정지했다(스냅샷 6~9초). 두 번 깨웠다. 한 번은 fly가 깨우면서 기계를
     다른 호스트로 옮겨(`fly machine status` 이벤트 `launch migrated=true`) 스냅샷 없이 새로 켜졌고, 앱 응답까지 73초(새 호스트가
     이미지를 받는 시간 포함), 그 뒤 예열 2분 15초가 걸렸다. 다른 한 번은 앱 응답 1.8초, 세 모델이 그대로 있었고(적재 시각 같음) 첫
     아바타 3.6초, 첫 채점 2.8초였다. 일시정지는 대개 몇 초 안에 깨우지만, 이주가 일어나면 새로 켜는 것과 같다.
   - 9/26 저녁 전체 검토 뒤 고친 것(배포 전): Whisper를 받은 뒤에 `HF_HOME`을 정해 실행 때 Whisper를 못 찾던 것(dev는 오프라인이라
     전사 대체 경로가 실패, 전시앱은 켜질 때마다 다시 받음)을 고쳤고, torch 2.14.0·transformers 5.17.0으로 고정했다. 이 두 줄이
     빌드 캐시 앞쪽을 바꿔 다음 빌드는 ML 층을 모두 다시 만든다(원격 빌더에서 몇 분 더 걸림). 서버 추론은 한 번에 하나씩 돌고
     (`LIPLAB_ML_CONCURRENCY`, 기본 1), 추론에 넣는 음성은 앞 30초까지다. 요청 본문은 멀티파트 12MB·그 밖 2MB가 넘으면 413이다.

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
