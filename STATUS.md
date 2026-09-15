# 지금 상태 — 다시 들어왔을 때 여기부터

> 최종 갱신 2026-09-15 — **앱 트랙(`feat/sublexical-feedback`) 병합 완료 — 촉각 제거를 유지한 채.**
> 그 전 세션: A-6(E1·E2) 실행 완료, 체크포인트 HF 백업 완료.
> 브랜치 `feat/content-scale` — origin보다 **7커밋 앞서 있고 아직 푸시하지 않았다.**
> 이 파일은 **한 화면짜리 현황판**이다. 근거·수치는 각 항목의 링크를 따라간다.
> 전체 이력은 `DEVELOPMENT_SUMMARY.md`.

---

## 한 줄 요약

축 A(D-GOP 음향 백본)는 학습·평가·보정까지 끝났지만, **그 판정을 만든 채점식에 구조적 결함이
있다**는 것이 드러났다. 2026-09-14에 재설계 실험(E1·E2)을 실제로 돌렸고 결론이 나왔다 —
**곱셈 항을 버리고 `naive`(표준 GOP)로 간다.** 불확실성 보정은 값을 하지 않았다.
지금 1순위는 **교체와 그에 따른 A-3 재측정·A-4 재적합**이다. 체크포인트는 HF에 백업됐다.

그와 **별개로 앱 트랙이 따로 굴러가고 있었다.** 2026-09-15에 `feat/sublexical-feedback`(자모 단위
피드백·비심 혼동행렬·학습 효과 리포트)을 합쳤다. 분기점이 촉각 제거 이전이라 충돌이 많았지만
**두 기둥(독화·말하기) 체제를 기준으로 삼아** 해소했다.

---

## 바로 할 일 (우선순위)

> **2026-09-15 — 앱 트랙을 병합했다**(`c82fb9f`). `feat/sublexical-feedback` 6커밋을 촉각 제거를
> 유지한 채 합쳤고 테스트·빌드까지 확인했다. **아직 푸시하지 않았다.** 되돌리려면
> `git reset --hard backup/pre-merge-content-scale`(병합 직전 상태로 걸어 둔 태그).
>
> **2026-09-14 세션에서 ① HF 백업 · ② E1 · ③ E2 · ④ 회수 · 스윕까지 전부 끝냈다.**
> 결과·판정·한계는 `docs/axis-a-training-plan.md` **A-6**. Pod은 정지했다(26분, 약 $1.5).
> 체크포인트는 이제 HF에도 있다 — **더 이상 AP-IN-2 볼륨에 묶이지 않는다.**

### 1. 채점식을 `naive`로 교체 ⭐

E1에서 **naive를 유의하게 이긴 변형이 하나도 없었다**(naive·maxlogit·prior_maxlogit 모두 단조성
1.000으로 천장). 사전 등록 규칙(축 B §4)대로 **`naive`를 채택한다.** 곱셈 항 `confidence`는 E2에서
**네 규칙 전부 우연 수준**(AUC 0.46~0.62)이라 정보가 없다는 것이 실측으로 굳었다.

| 순서 | 작업 | GPU | 비고 |
|---|---|---|---|
| ~~1~~ | ~~`dgop.dgop_phone`을 naive로 교체~~ | — | ✅ **2026-09-15 완료.** 단언도 '해결 확인'으로 뒤집었다 |
| 2 | A-3 재측정 | **필요**(~12분) | 원점수 눈금이 바뀐다 |
| 3 | A-4 앵커 재적합 → `backend/data/dgop_calibration.json` | **필요**(~11분) | 표시 점수 상한 94.9도 재확인 |
| 4 | 앱 연결 — `DGOP_ALIGNER_ID`/`DGOP_SCORER_ID` | 불필요 | HF에 가중치가 있어 볼륨 없이 된다 |

2·3은 GPU가 필요하니 **한 세션에 묶어서** 돈다. 이제 아무 DC·아무 GPU에서 HF 체크포인트를 받아
돌리면 된다(비공개 저장소라 HF 읽기 토큰 필요).

> **🚨 2·3이 끝나기 전에 앱의 D-GOP 경로를 켜지 않는다.** 채점식이 바뀌어 원점수 눈금이 달라졌는데
> `backend/data/dgop_calibration.json`과 `dgop.AXIS_A_SEVERITY_SCORES`는 아직 **구 식으로 잰 앵커**다.
> 지금 켜면 표시 점수가 틀린다. `DGOP_ALIGNER_ID` 미설정이 기본값이라 **현재는 꺼져 있다**(전사 경로).

### 2. 그다음

- **AI Hub 608 샘플 확인** — IRB 불필요, 본인인증만. 확인할 것 3가지는 `docs/deaf-speech-data-research.md` §2
- **정민화 연구실 접촉**(서울대 언어학과) — 이제 E1·E2 실측을 들고 갈 수 있다. 우리 가설을 한국어로 이미 검증했고 코드가 MIT로 공개돼 있다. QoLT·CI 아동 데이터 경로이기도 하다
- **`blank 제외` 변형 재덤프**(GPU ~12분) — A-6 "남은 일" 2번. 지금 npz로는 평가할 수 없다
- **병합분 푸시 여부 결정** — 로컬에만 있다. 푸시하면 `feat/sublexical-feedback`은 역할이 끝난다
- **CLAUDE.md 로드맵 정리** — 트랙 2 백로그의 **혼동 매트릭스 분석**은 이번 병합으로 구현됐다.
  목록에서 내리고, 새로 들어온 학습 효과 리포트를 구조 설명에 반영한다

---

## 어디까지 했나

### ✅ 끝난 것

| 단계 | 내용 | 결과 |
|---|---|---|
| **A-1/A-2 학습** | Scorer(정상 발화) + Aligner(저하 증강) 2모델 분리, 자모 49토큰 vocab | eval_loss 0.2087 / 1.147. H100 2.5시간, $7~8 |
| **A-3 변별력** | 재측정 완료 | **단조성 0.998 / AUC 1.000 / 정렬 1.000 — 합격** |
| **A-4 점수 보정** | severity 앵커 + log 보간 | `backend/data/dgop_calibration.json` 커밋. 5개 severity 전부 채택 |
| **A-5 버그 수정** | 구간 뭉갬 버그 — 중복 토큰이 한 구간으로 합쳐지던 문제 | 깨끗한 발화 **9.51 → 76.56**. 한계 ②의 실제 원인이었다 |
| **CTC 정렬 자체 구현** | `backend/ctc_align.py` (Viterbi) | torchaudio와 프레임 단위 일치 검증. 의존 제거 |
| **100점 도달 불가** | 표시 상한 94.9 | **그대로 두기로 결정** — 발음 교정 앱에서 만점을 주지 않는 편이 낫다 |
| **농인 발화 데이터 조사** | 7개 축 병렬 조사 | `docs/deaf-speech-data-research.md` |
| **채점식 재설계 배관** | E1/E2 실험 도구 일체 | `docs/axis-b-scorer-redesign.md` |
| **체크포인트 HF 백업** | scorer·aligner 최종 모델 | `duadnwls/liplab-dgop-{scorer,aligner}`에 각 **1.26GB**. 업로드 크기 대조 + HF API 재확인 (2026-09-14) |
| **A-6 E1·E2 실행** | 채점식 9종 스윕 + 과신 측정 | **naive 채택 확정.** 구간 22,905 / 22,106개. 결과·한계는 `docs/axis-a-training-plan.md` A-6 |
| **채점식 교체 (1단계)** | `dgop_phone`을 naive로 (2026-09-15) | 곱셈 항 제거. 구 식은 `gop_variants.dgop`·`analyze_dgop_redundancy`에 **비교 기준으로 보존** — A-6 표와 ρ=0.980을 계속 재현한다 |
| **촉각(타도마) 제거** | 세 기둥 → **두 기둥(독화·말하기)** | 파일 22개·백엔드 엔드포인트 6개 삭제. 대시보드·메뉴·분석·안내 전부 두 기둥 기준으로 재정렬 (`b730c0d`) |
| **앱 트랙 병합** | `feat/sublexical-feedback` 6커밋 통합 (2026-09-15) | **촉각 제거 유지.** 충돌 6파일 해소, 기능 충돌 3건은 합집합 (`c82fb9f`) |
| **근거 기반 독화 피드백** | 오답을 자모·비심 단위로 분석 + 개인별 혼동행렬 | `scoring.viseme_confusions`, `TrialAttempt` 모델, `GET /api/curriculum/confusion-matrix` |
| **학습 효과 리포트** | 학습곡선·향상도·단계 도달 시행수 | `GET /api/eval/summary` + `/analysis/eval`(`EvalReport.jsx`) |

테스트: **backend 22 + scripts 3 + frontend 35, 전부 통과.** 2026-09-15 병합 후 재실행으로 확인했다
(`npx vite build` 성공, `main.py` 임포트 시 라우트 50개 등록·촉각 라우트 0개도 함께 확인) —
반드시 `backend/venv`의 파이썬으로 돌린다(시스템 파이썬엔 numpy·Levenshtein·torch가 없어 실패한다).
축 B §3-2의 스모크·스윕 배관도 로컬에서 끝까지 돌려 확인했다(31초, 구간 240개, blank 0개) —
**Pod에서 그 절은 건너뛰어도 된다.**

### ⚠️ 발견됐지만 아직 안 고친 것

**채점식 `D-GOP = naive × confidence`가 구조적으로 결함이다.** 데이터 없이 증명된다
(`python scripts/analyze_dgop_redundancy.py`):

- `ρ(naive, confidence) = 0.980` — 두 항이 같은 신호라 곱셈이 순위 정보를 더하지 못한다
- **보정 방향이 반대다** — 과신(뾰족한데 틀림)은 통과시키고 과소확신을 벌한다
- **순위를 뒤집는다** — '또렷하게 다른 음소'(0.0128)가 '머뭇거리지만 목표가 1등'(0.0015)보다
  8배 높은 점수. 확신에 차서 틀릴수록 점수가 오른다

선행 연구(Yeo et al., Interspeech 2023, 서울대, 코드 MIT)가 한국어 구음장애 발화에서 같은 실험을
이미 했고, **우리가 곱한 두 신호(margin·엔트로피)가 그 논문 표에서 가장 나쁜 둘**이었다.

**통계 인프라 3건 — 조사 문서 §5의 지적이 코드에 그대로 있다** (2026-09-14 확인):

- **유의성 검정이 없다** — `scripts/eval_dgop_discrimination.py`는 조사 문서보다 먼저 마지막으로
  수정된 상태다. 새 스윕(`sweep_gop_scorers.py`)에는 대응표본 부트스트랩이 붙었지만 **단조성
  비교에만** 있고 AUC에는 없다.
- **화자 단위 집계가 없다** — 스윕은 구간을 발화 단위로 접어 한 단계 개선했으나, 부트스트랩이
  뽑는 단위도 발화다. 한 화자의 발화 여러 개를 독립 표본으로 센다(조사 문서 §5-4).
- **합격선 0.90이 그대로다** — 감쇠 때문에 도달 불가일 수 있다는 지적(§5-5)에도
  `eval_dgop_discrimination.TARGET_MONOTONICITY = 0.90`이 유지돼 있다.

**A-6에서 새로 드러난 것 3건** (2026-09-14):

- **blank 불변 검사의 의미가 틀렸다.** `nb_frames != frames`는 정렬이 깨진 것을 잡지 못하고
  **모델 argmax가 blank인 프레임**을 센다. 강제정렬에서는 정상적으로 생기는 일이라 실제 데이터에서
  E1 구간의 **47%**(10,785개)가 걸린다. 따라서 **Cao et al. 2024의 blank 집계 지적은 여전히
  유효하다** — 축 B §6의 "재조사 불필요" 목록에서 그 줄을 내리고, 경고 문구도 고쳐야 한다.
- **`blank 제외` 변형은 평가되지 않았다.** `span_aggregates` docstring은 "전체/비blank 두 방식"을
  계산한다고 적었지만 저장되는 건 전체 구간 평균뿐이다. **재덤프 없이는 잴 수 없다.**
- **E1이 천장에 닿았다.** naive·maxlogit·prior_maxlogit이 모두 단조성 1.000이라 상위 후보를 구별할
  검정력이 없다. "UQ가 도움이 안 된다"가 아니라 **"합성 저하로는 물을 수 없다"**가 정확한 서술이다.

### 🚫 막힌 것

| 항목 | 막힌 이유 | 상태 |
|---|---|---|
| ~~체크포인트 HF 백업~~ | ~~AP-IN-2에 H100 없음~~ | ✅ **2026-09-14 해결** — 재고가 돌아와 기존 Pod이 그냥 켜졌다 |
| ~~E1·E2 실행~~ | ~~같은 GPU 병목~~ | ✅ **2026-09-14 완료** (A-6) |
| **실제 농인 발화** | AI Hub 71434는 IRB+소속증빙 필요(안심존). 608은 본인인증만 | 경로는 조사 완료 |

> **GPU 확보 교훈 (2026-09-14).** 9/9의 24회 실패는 **그때 DC에 H100이 없었기 때문**이고, 닷새 뒤
> `gpuTypes.lowestPrice(dataCenterId:"AP-IN-2").stockStatus`가 `Low`로 돌아오자 기존 Pod의 `start`가
> 한 번에 성공했다. **다음에 막히면 우회로를 찾기 전에 재고를 먼저 조회한다.**
> 우회로 조사(S3 API는 AP-IN-2 미지원, 0 GPU 시작, 새 Pod 배포)는 런북 **§7.2**에, 실기에서 밟은
> 함정(**포트 재매핑**, **Pod 저장소가 9/8에 멈춰 있어 `git pull`이 거부됨**)은 **§2.1**에 적어 뒀다.

### 🔸 결정된 것

**2026-09-15 (병합에서).**

- **`closure-answer`는 두 구현의 합집합이다.** 양쪽 브랜치가 각자 같은 엔드포인트를 만들었다.
  상대의 **서버 채점**(`item_id`/`chosen`을 받아 `CLOSURE_ITEMS`에서 정답을 찾는다) 위에
  우리의 3단계 숙달·취약 입모양·SRS·XP를 얹었다. 한쪽만 고르면 기능이 사라진다.
- **정오답은 서버가 재계산한다 — XP까지.** 클라이언트가 보낸 `data.correct`를 믿으면 숙달·해금·
  평가를 조작할 수 있다. 상대의 감사 수정이 2단계 채점을 고쳤고, 병합하며 **같은 결함이 남아
  있던 XP 보상 1곳**도 서버 재계산값으로 맞췄다.
- **`HardwareBuild` 페이지는 되살리지 않는다.** 촉각 장치용이라 `b730c0d`가 지웠다. 상대 브랜치의
  lazy import를 그대로 받으면 `vite build`가 깨진다 — `EvalReport`만 받았다.

**2026-09-14.**

- **촉각 DB 테이블은 그대로 둔다.** `database.py`의 `TactileStageProgress`·`TactileAttempt`와
  `Bookmark.domain`의 `'tactile'` 값은 조회하는 코드가 없어 무해하다. 기존 행을 잃지 않기 위해
  남기고, **"미사용 · 지우려면 별도 마이그레이션 필요"** 주석만 붙였다.
- **`torch`·`torchaudio` `<2.9.0` 상한은 풀었다.** 근거: 로컬 `backend/venv`가 이미
  **torch 2.14 / torchaudio 2.11**이고 그 조합으로 backend 22파일·scripts 3파일이 전부 통과하며,
  상한의 근거였던 `forced_align`도 2.11에 그대로 살아 있다.
  ⚠️ **실질적 상한은 이제 `torchcodec<0.7.0`**(torch 2.8 계열에 묶여 있다)이다. 학습을 돌릴 때는
  (torch, torchaudio, torchcodec)을 **한 세트로** 맞춘다 — 위 로컬 검증에 torchcodec은 빠져 있어
  **데이터셋 오디오 디코딩 경로는 확인되지 않았다.** 상세는 `requirements-ml.txt` 머리 메모.
- **E1·E2 판정 규칙의 빈칸을 메꿨다.** "세 결과가 배타적"이 아니라는 점, `prior_maxlogit`이 아닌
  변형이 이길 때의 채택 순서, E2의 잔존율·AUC 임계값을 `docs/axis-b-scorer-redesign.md` §4에
  **사전 등록**으로 적었다(결과를 보기 전에 정한 값이다).

---

## 알아둘 함정 (반복해서 밟은 것들)

1. **Pod을 정지하면 GPU 예약이 풀린다.** 볼륨에서 꺼낼 게 있으면 **끄기 전에** 꺼낸다
2. **Pod Start 후 `PUBLIC_KEY` env가 비어 SSH가 막힌다** — env PATCH + 재시작. 그러면 포트가 또 바뀐다 (런북 §2.1)
3. **`--mode perturb`는 자모 vocab 전용** — 음절 vocab으로 돌리면 첫 발화에서 즉시 실패하도록 막아 뒀다
4. ~~`torchaudio<2.9.0` 상한~~ → **2026-09-14 해제됨.** 이제 실제로 막는 것은 `torchcodec<0.7.0`이다
   (torch 2.8 계열에 묶여 있다) — 학습 환경에서는 torch·torchaudio·torchcodec을 한 세트로 맞춘다
5. **줄바꿈이 파일마다 다르다 — `main.py`만이 아니다.** 실측 결과 소스 18개가 CRLF다:
   `backend/{main,database,engine,scoring,llm_service,auth,check_db}.py`,
   `frontend/src/api.js`, `frontend/src/pages/{Practice,Conversation,Bookmarks}.jsx`,
   `frontend/src/components/{LipSyncPlayer3D,QuizForm}.jsx`, `frontend/src/{main.jsx,store/useStore.js}`,
   `frontend/{vite,tailwind,postcss}.config.js`.
   **"나머지는 LF"는 틀렸다 (2026-09-14 정정).** 추적 파일 **36개**가 CRLF거나 섞여 있다 — 위 18개 외에
   `backend/requirements.txt`, `frontend/{index.html,package.json,package-lock.json}`,
   `frontend/src/index.css`, `Dockerfile`, `docker-compose.yml`, `fly.toml`, `.env.example`,
   `scripts/{setup.sh,setup.ps1,start-backend.ps1}`, `DEPLOY.md`, `QUICKSTART.md`, `PROJECT_SUMMARY.md`가
   CRLF이고, `.gitignore`·`backend/data/ksl_dictionary.csv` **2개만 두 방식이 섞여 있다.**
   (**2026-09-15 정정** — `README.md`는 혼합이었으나 상대 브랜치가 고치며 CRLF로 정규화했다.
   합계 36개는 그대로이고 CRLF 34 · 혼합 2로 내역만 바뀌었다. 병합으로 들어온 `fly.dev.toml`·
   `EvalReport.jsx`는 LF다.)
   섞으면 diff가 파일 전체로 뒤집힌다. **편집 전에 확인한다:**
   ```bash
   grep -c $'\r' <파일>                   # 0이면 LF, 줄 수와 같으면 CRLF
   git ls-files --eol | grep -v 'w/lf'    # 저장소 전체를 한 번에 본다
   ```
6. 테스트는 pytest가 아니라 자체 러너 — `PYTHONPATH=. python test_x.py`
7. **오래된 분기점에서 갈라진 브랜치를 합칠 때, 자동 병합이 조용히 옛 코드를 남긴다.**
   `feat/sublexical-feedback` 병합에서 `Closure.jsx`가 그랬다 — 양쪽 호출이 나란히 살아남아
   같은 엔드포인트를 두 번 부르고, 두 번째는 바뀐 시그니처와 안 맞아 매번 400이 났다.
   **충돌이 안 난 파일이 오히려 위험하다.** 시그니처를 바꿨다면 호출부를 전부 훑는다.

---

## 문서 지도

| 문서 | 언제 보나 |
|---|---|
| **`docs/axis-b-scorer-redesign.md`** | 채점식 후보 9종과 **사전 등록한 판정 규칙**(§4). E1·E2는 끝났고 결과는 A-6에 |
| `docs/axis-a-runbook.md` | RunPod 실행 절차, 시간·비용, 함정 |
| `docs/axis-a-training-plan.md` | 축 A 설계 근거와 실측 이력(A-1~**A-6**) — **1순위 작업의 근거가 A-6에 있다** |
| `docs/deaf-speech-data-research.md` | 데이터 확보 경로 7개 축 + 채점식 결함의 근거 |
| `DEVELOPMENT_SUMMARY.md` | 전체 개발 이력 요약 |
| `CLAUDE.md` | 프로젝트 오리엔테이션(커리큘럼·잠금 규칙·컨벤션) |
