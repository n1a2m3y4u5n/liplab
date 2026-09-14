# 지금 상태 — 다시 들어왔을 때 여기부터

> 최종 갱신 2026-09-14 (`1c87bc7` 이후 · 이 정정분은 아직 커밋 전). 브랜치 `feat/content-scale`, origin과 동기화됨.
> 이 파일은 **한 화면짜리 현황판**이다. 근거·수치는 각 항목의 링크를 따라간다.
> 전체 이력은 `DEVELOPMENT_SUMMARY.md`.

---

## 한 줄 요약

축 A(D-GOP 음향 백본)는 **학습·평가·보정까지 끝났고 "합격" 판정도 받았다.**
그런데 **그 판정을 만든 채점식 자체에 구조적 결함이 있다**는 것이 나중에 드러났다.
지금 1순위는 데이터 확보가 아니라 **채점식 재설계**이고, 그 실험은 **배관까지 끝나 GPU 실행만 남았다.**

---

## 바로 할 일 (우선순위)

### 1. GPU 세션 — 한 번 켜면 세 가지를 한꺼번에 ⭐

**⚠️ Pod을 켜는 것 자체가 지금 최대 리스크다.** AP-IN-2에 H100이 없어 재시작이 **24회 연속
실패**한 상태다(볼륨이 DC에 묶여 우회로 없음, `docs/axis-a-runbook.md` §7.1).
**켜지면 끄기 전에 아래를 전부 끝낸다.**

| 순서 | 작업 | 시간 | 왜 이 순서인가 |
|---|---|---|---|
| ① | 체크포인트 HF 백업 (`scripts/upload_ckpt_hf.py`) | ~10분 | 이것만 끝나면 볼륨 없이 어디서든 재현된다. **최우선** |
| ② | E1 덤프 (채점식 스윕용) | ~12분 | |
| ③ | E2 덤프 (과신 측정용) | ~12분 | |
| ④ | npz 2개 로컬 회수 | ~1분 | 이후 분석은 GPU 불필요 |

명령어 전문·판정 기준 → **`docs/axis-b-scorer-redesign.md`** (§3 실행, §4 판정)

- 필요한 것: **RunPod API 키**, **HF write 토큰**
  - ⚠️ 2026-09-09 세션에서 쓴 키·토큰은 **대화 기록에 남아 있으니 폐기(rotate) 권장.**
    저장소·커밋에 흔적이 없음은 확인했다. 다시 필요하면 새로 발급하면 된다
- 비용: ~$2 (Pod $3.49/hr)
- 잔액: 2026-09-09 기준 약 **$14** + 볼륨 월 $4.20(하루 $0.14) 계속 과금 중

### 2. 스윕 분석 (GPU 불필요, 몇 초)

```bash
python scripts/sweep_gop_scorers.py --features data_out/severity.npz
python scripts/sweep_gop_scorers.py --features data_out/perturb.npz
```

**판정이 배타적이라 어느 결과가 나와도 답이 된다:**

| 결과 | 뜻 | 다음 |
|---|---|---|
| `prior_maxlogit`이 naive를 유의하게 이김 | 방향은 옳고 **곱셈 형태만** 틀렸다 | 채점식 교체 → A-3 재측정 → A-4 앵커 재적합 |
| 아무 변형도 naive를 못 이김 | 합성 저하에서 UQ 자체가 무의미 | `naive`로 단순화 |
| `dgop`이 naive보다 유의하게 나쁨 | 현행 채점식이 해를 끼치는 중 | 앱 연결 전 즉시 교체 |

### 3. 그다음

- **앱 연결** — `DGOP_ALIGNER_ID`/`DGOP_SCORER_ID` 설정. ①(HF 백업)이 선행돼야 함
- **AI Hub 608 샘플 확인** — IRB 불필요, 본인인증만. 확인할 것 3가지는 `docs/deaf-speech-data-research.md` §2
- **정민화 연구실 접촉**(서울대 언어학과) — 우리 가설을 한국어로 이미 검증했고 코드가 MIT로 공개돼 있다. QoLT·CI 아동 데이터 경로이기도 하다

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
| **채점식 재설계 배관** | E1/E2 실험 도구 일체 | `docs/axis-b-scorer-redesign.md`. **GPU만 남음** |
| **촉각(타도마) 제거** | 세 기둥 → **두 기둥(독화·말하기)** | 파일 22개·백엔드 엔드포인트 6개 삭제. 대시보드·메뉴·분석·안내 전부 두 기둥 기준으로 재정렬 (`b730c0d`) |

테스트: **backend 22 + scripts 3 + frontend 35, 전부 통과.** 2026-09-14 재실행으로 확인했다 —
반드시 `backend/venv`의 파이썬으로 돌린다(시스템 파이썬엔 numpy·Levenshtein·torch가 없어 실패한다).

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

### 🚫 막힌 것

| 항목 | 막힌 이유 | 상태 |
|---|---|---|
| **체크포인트 HF 백업** | AP-IN-2에 H100 없음 → Pod 재시작 24회 실패 | HF repo·모델카드·업로드 스크립트는 준비 완료. GPU만 뜨면 두 줄 |
| **E1·E2 실행** | 같은 GPU 병목 | 배관·테스트 완료 |
| **실제 농인 발화** | AI Hub 71434는 IRB+소속증빙 필요(안심존). 608은 본인인증만 | 경로는 조사 완료 |

> **2026-09-14 우회로 재조사** — RunPod 공식 문서로 다시 훑어 런북 **§7.2**에 표로 정리했다.
> S3 호환 API는 **AP-IN-2 미지원**이고, DC 간 볼륨 이전도 원본 쪽 Pod이 필요해 같은 병목이다.
> 남은 후보는 **(A) GPU 0개로 시작**(공식 기능·데이터 회수용. 업로드는 CPU로 충분하지만
> 네트워크 볼륨 Pod에 적용되는지는 문서에 없다)과 **(B) `start` 재시도 대신 같은 볼륨으로 새 Pod
> 배포**(정지된 Pod은 원래 물리 머신에 묶인다)다. **①만 끝나면 E1·E2는 AP-IN-2에 묶이지 않는다.**

### 🔸 결정된 것 (2026-09-14)

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
   CRLF이고, `README.md`·`.gitignore`·`backend/data/ksl_dictionary.csv`는 **이미 두 방식이 섞여 있다.**
   섞으면 diff가 파일 전체로 뒤집힌다. **편집 전에 확인한다:**
   ```bash
   grep -c $'\r' <파일>                   # 0이면 LF, 줄 수와 같으면 CRLF
   git ls-files --eol | grep -v 'w/lf'    # 저장소 전체를 한 번에 본다
   ```
6. 테스트는 pytest가 아니라 자체 러너 — `PYTHONPATH=. python test_x.py`

---

## 문서 지도

| 문서 | 언제 보나 |
|---|---|
| **`docs/axis-b-scorer-redesign.md`** | **다음 작업(E1·E2)을 할 때 — 명령어·판정 기준 전문** |
| `docs/axis-a-runbook.md` | RunPod 실행 절차, 시간·비용, 함정 |
| `docs/axis-a-training-plan.md` | 축 A 설계 근거와 실측 이력(A-1~A-5) |
| `docs/deaf-speech-data-research.md` | 데이터 확보 경로 7개 축 + 채점식 결함의 근거 |
| `DEVELOPMENT_SUMMARY.md` | 전체 개발 이력 요약 |
| `CLAUDE.md` | 프로젝트 오리엔테이션(커리큘럼·잠금 규칙·컨벤션) |
