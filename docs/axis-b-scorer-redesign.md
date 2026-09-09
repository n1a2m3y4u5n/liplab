# 축 B 채점식 재설계 — 실험 계획·인수인계

> 작성 2026-09-09. 상태: **배관 완료, GPU 실행 대기.**
> 배경·근거는 `docs/deaf-speech-data-research.md` §0, 실측 이력은 `docs/axis-a-training-plan.md`.

---

## 0. 왜 하는가 — 한 문단

축 A는 A-3에서 "합격"(단조성 0.998)을 받았지만, **그 판정을 만든 채점식이 구조적으로 결함**이다.
`D-GOP = naive × confidence`인데 두 항의 순위상관이 **0.980**이라 곱셈이 정보를 더하지 못하고,
보정 방향이 설계 의도와 **반대**다(과신은 통과시키고 과소확신을 벌한다). 그래서 지금 앵커·판정·
표시점수가 전부 결함 있는 자 위에 얹혀 있다. **실제 농인 발화를 구해도 이 형태로는 안 고쳐진다** —
데이터보다 이쪽이 먼저다.

재현: `python scripts/analyze_dgop_redundancy.py` (GPU·데이터 불필요)

---

## 1. 이미 만들어 둔 것 (커밋 `900bb1f`)

| 파일 | 역할 | 테스트 |
|---|---|---|
| `backend/gop_variants.py` | 문헌 표준 GOP 변형 9종 — 전부 순수 함수 | `test_gop_variants.py` (8) |
| `backend/jamo_perturb.py` | 목표 자모열 오염 규칙 4종 — 전부 순수 함수 | `test_jamo_perturb.py` (9) |
| `scripts/dump_gop_features.py` | 구간 통계 덤프 — **유일한 GPU 단계** | `test_dump_gop_features.py` (5) |
| `scripts/sweep_gop_scorers.py` | 채점식 일괄 비교 + 발화 단위 부트스트랩 CI | — |
| `backend/dgop_acoustic.ctc_outputs` | raw logit까지 반환(MaxLogit 계열에 필수) | 기존 테스트 |

**설계의 핵심은 GPU를 한 번만 쓰는 것이다.** 순전파 결과(평균 확률·로그확률·raw 로짓)를 npz로
뜬 뒤, 채점식 비교는 순수 함수 replay로 돌린다. 채점식을 추가할 때마다 Pod을 다시 빌리지 않는다.

### 채점식 후보

| 이름 | 식 | 출처 |
|---|---|---|
| `naive` | P̄(p) | 현행 대조군 |
| `dgop` | P̄(p) · margin · (1−H) | 현행 (결함 확인됨) |
| `gmm_gop` | mean_f log P_f(p) | Witt & Young 2000 |
| `nn_gop` | log P̄(p) − max_{q≠p} log P̄(q) | Hu et al. 2015 (LPR) |
| `dnn_gop` | log P̄(p) − log prior(p) | Hu et al. 2015 |
| `maxlogit` | L̄(p) | Yeo et al. 2023 |
| **`prior_maxlogit`** | L̄(p) − log prior(p) | **Yeo et al. 2023의 최고 성능** |
| `logit_margin` | L̄(p) − max_{q≠p} L̄(q) | Yeo et al. 2023 |
| `confidence` | margin · (1−H) | 진단용(채점식 후보 아님) |

---

## 2. ⚠️ 선결 조건 — GPU를 확보할 수 있는가

**이게 지금 최대 리스크다.** 2026-09-09 기준 Pod을 정지한 뒤 **재시작이 24회 연속 실패**했다
(AP-IN-2에 H100이 없음, 런북 §7.1). 네트워크 볼륨이 DC에 묶여 있어 우회로가 없다.

따라서 **Pod을 켜는 데 성공하면 그 세션에서 다음을 전부 끝낸다** — 끄면 다시 못 켤 수 있다:

1. 체크포인트 HF 백업 (`scripts/upload_ckpt_hf.py`, ~10분) ← **이걸 먼저 한다**
2. E1 덤프 (severity, ~12분)
3. E2 덤프 (perturb, ~12분)
4. npz 2개를 로컬로 회수

백업이 끝나면 이후로는 볼륨 없이도 HF에서 체크포인트를 받아 어디서든 재현할 수 있다.

---

## 3. 실행 — GPU 세션 (~35분, ~$2)

### 3-1. 접속·동기화

```bash
source /workspace/venv/bin/activate
cd /workspace/liplab && git pull origin feat/content-scale
export HF_HOME=/workspace/hf
```

> Pod을 Start하면 IP·포트가 바뀐다. `PUBLIC_KEY` env가 비어 SSH가 막히는 함정은 런북 §2.1 참고.

### 3-2. GPU를 태우기 전 검증 (무료)

```bash
cd backend && PYTHONPATH=. python test_gop_variants.py && PYTHONPATH=. python test_jamo_perturb.py && cd ..
python scripts/test_dump_gop_features.py
python scripts/dump_gop_features.py --smoke
```

### 3-3. 체크포인트 백업 (먼저!)

```bash
python scripts/upload_ckpt_hf.py     # HF 토큰 필요
```

### 3-4. E1 — 채점식 스윕용 덤프

```bash
python scripts/dump_gop_features.py --mode severity \
  --aligner /workspace/ckpt/aligner --scorer /workspace/ckpt/scorer \
  --limit 50 --out /workspace/feat/severity.npz
```

### 3-5. E2 — 과신 측정용 덤프

```bash
python scripts/dump_gop_features.py --mode perturb \
  --aligner /workspace/ckpt/aligner --scorer /workspace/ckpt/scorer \
  --limit 50 --out /workspace/feat/perturb.npz
```

> `--mode perturb`는 **자모 vocab 체크포인트 전용**이다. 음절 vocab(공개 체크포인트)으로 돌리면
> 첫 발화에서 즉시 실패한다 — 12분 뒤에 clean만 쌓인 npz를 받지 않도록 막아 뒀다.

### 3-6. 회수

```bash
# npz 2개를 로컬로 가져온다. 이후 분석에는 GPU가 필요 없다.
scp -P <포트> root@<IP>:/workspace/feat/*.npz ./data_out/
```

---

## 4. 분석 — GPU 없이, 몇 초

```bash
python scripts/sweep_gop_scorers.py --features data_out/severity.npz
python scripts/sweep_gop_scorers.py --features data_out/perturb.npz
```

### E1 판정 기준 — 세 결과가 배타적이라 어느 쪽이든 답이 된다

| 결과 | 해석 | 다음 행동 |
|---|---|---|
| **`prior_maxlogit`이 naive를 유의하게 이김** | 불확실성 보정의 **방향은 옳았고 곱셈 형태가 틀렸다** | 채점식을 교체 → A-3 재측정 → A-4 앵커 재적합 |
| **어떤 변형도 naive를 못 이김** | 합성 저하에서는 UQ 자체가 무의미 | `naive`로 단순화. 실제 병리 발화 확보 전까지 UQ 보류 |
| **`dgop`이 naive보다 유의하게 나쁨** | 현행 채점식이 실제로 해를 끼치고 있다 | 즉시 교체(앱 연결 전 필수) |

유의성은 **발화 단위 대응표본 부트스트랩**(10,000회)으로 판정한다. A-5까지의 "naive 0.914 >
D-GOP 0.813"에는 검정이 붙어 있지 않아 우연인지 알 수 없었다 — 이번엔 CI가 함께 나온다.

### E2 판정 기준 — 과신이 실재하는가

오디오는 동일하고 **목표 자모열만** 오염돼 있다. 따라서:

| 결과 | 해석 |
|---|---|
| **오염 목표에서 `naive`가 높게 남는다** | **과신이 실재한다.** UQ 보정이 값을 할 조건이 성립 — 다만 현행 곱셈 형태로는 못 잡는다(§0) |
| **오염 목표에서 `naive`가 붕괴한다** | 이 모델은 애초에 과신하지 않는다 → 축 A의 §0 전제가 이 체크포인트에 대해 거짓 |
| 규칙별 AUC가 크게 다름 | 어떤 조음 오류에 민감/둔감한지가 드러난다(종성 탈락 vs 모음 중앙화 등) |

---

## 5. 실행 후 해야 할 것

1. 결과를 `docs/axis-a-training-plan.md`에 A-6으로 기록(성과와 한계를 같은 비중으로)
2. 채점식을 교체하면 **연쇄가 따라온다**: A-3 재측정 → A-4 앵커 재적합 →
   `backend/data/dgop_calibration.json` 갱신 → 표시 점수 상한 재확인
3. `test_gop_variants.test_dgop_inverts_ranking_...`의 단언을 뒤집는다
   (지금은 "결함 기록", 고치면 "해결 확인")
4. `deaf_speech_synthesis.py` 정교화는 **이 다음**이다 — 잘못된 자를 정밀하게 만들 이유가 없다

---

## 6. 이 작업에서 이미 확인된 것 (재조사 불필요)

- **D-GOP가 순위를 뒤집는다.** '또렷하게 다른 음소'(0.0128)가 '머뭇거리지만 목표가 1등'(0.0015)보다
  8배 높은 점수를 받는다. naive는 이 순서를 맞게 매긴다.
  `test_gop_variants.test_dgop_inverts_ranking_confidently_wrong_beats_hesitantly_correct`가 고정.
- **blank 집계는 문제가 아니다.** `ctc_align.token_spans`가 비blank run만 잡아 구간에 blank가
  원리적으로 0개다. Cao et al. 2024의 지적은 A-5 **이전** 구현에만 해당했고 구간 뭉갬 수정으로
  함께 사라졌다. 불변 검사(`nb_frames != frames`)로 고정.
- **`nn_gop`은 목표를 경쟁 집합에서 빼야 한다.** 포함하면 목표가 argmax인 순간 0으로 포화해
  '아슬아슬한 1등'과 '압도적 1등'을 구별하지 못한다.
- **선행 연구가 같은 실험을 한국어로 이미 했다.** Yeo et al. (Interspeech 2023, 코드 MIT).
  한국어 τ: 베이스라인 −0.524 / 엔트로피 −0.264 / 마진 −0.443 / Prior+MaxLogit −0.544.
  **우리가 곱한 두 신호가 그 표에서 가장 나쁜 둘**이고, 개선폭도 상대 3.91%로 크지 않다.

---

## 7. 알려진 한계

- 표본이 **건청 발화 + 합성 저하**다. E1의 결론은 "합성 저하에서 어떤 채점식이 나은가"까지이고,
  실제 농인 발화로의 일반화는 보장되지 않는다.
- E2의 오염은 **치환 오류만** 모사한다(Cao et al. 2024가 같은 한계를 명시). 실제 농인 발화의
  운율·타이밍 이상은 재현하지 않는다.
- `--limit 50`은 A-3과 같은 표본 크기다. 채점식 간 차이가 작으면 검정력이 부족할 수 있다
  (필요 표본 논의는 `docs/deaf-speech-data-research.md` §4).
