# 축 A 학습 계획 — D-GOP 음향 백본

> 확정일 2026-09-08. 대상: `backend/dgop.py`·`dgop_acoustic.py`가 쓰는 CTC 음향 모델.
> 실행 환경: RunPod H100. 부트스트랩 데이터: Zeroth-Korean.
> 관련 문서: `DEVELOPMENT_SUMMARY.md`(축 A~K 현황), `docs/lipreading-data-research.md`(축 D 데이터)

---

## 0. 왜 계획서 원안을 바꾸는가

계획서 3.1과 `deaf_speech_synthesis.py` docstring은 축 A를 **"정상 발화에 조음 교란을
적용한 합성 코퍼스로 한국어 체크포인트를 미세조정"** 으로 적어 두었다. 그대로 하면
D-GOP의 변별력이 사라진다.

`dgop.py`의 점수는 `naive × confidence`이고, 뭉갠 발화에서 분포가 평평해져 confidence가
떨어지는 것 자체가 **"발음이 부정확하다"는 신호**다. 실측:

| 발화 상태 | naive(표준 GOP) | confidence | D-GOP |
|---|---|---|---|
| 또렷한 발화 | 0.85 | 0.461 | 0.392 |
| 약간 뭉갬 | 0.55 | 0.055 | 0.030 |
| 심하게 뭉갬 | 0.30 | 0.0002 | 0.0001 |

여기서 모델을 "농인 발화에 강인하게" 만들면 뭉갠 발화에도 분포가 뾰족해지고, confidence가
올라가고, **점수가 높아진다.** 발음 교정 앱인데 뭉개도 만점이 나온다.

GOP 계열은 원래 canonical(정상 발화) 모델로 재야 의미가 있는 지표다. 그래서 모델을 둘로 나눈다.

## 1. 목표

> **자모 단위 D-GOP를 낼 수 있는 채점기(Scorer)와, 뭉갠 발화에서도 구간을 놓치지 않는
> 정렬기(Aligner) 두 개를 만든다.**

| | Scorer (채점기) | Aligner (정렬기) |
|---|---|---|
| 학습 데이터 | Zeroth 정상 발화만 | Scorer에서 이어받아 합성 저하 증강 |
| 역할 | 구간별 사후확률 → D-GOP | `forced_align`으로 음소 구간 탐색 |
| 뭉갠 발화에 | **일부러 약해야 함**(그게 점수 신호) | 강인해야 함 |
| vocab | 공유 | 공유 |

`dgop_acoustic.assess_text(model_id=...)`가 `aligner_id`/`scorer_id`로 갈라진다.

## 2. vocab — 위치 구분 69토큰

`kresnik/wav2vec2-large-xlsr-korean`의 기존 vocab은 **한글 음절 단위 1,205토큰**이라
`dgop.py`가 설계한 음소별 D-GOP가 나오지 않는다(B.6에서 발견한 한계). 어차피 학습할 거면
encoder는 두고 `lm_head`만 자모 vocab으로 교체하면 이 한계가 함께 풀린다.

**확정: 49토큰** (`backend/jamo_vocab.py`). 처음에 69로 잡았으나 실측 후 줄었다 —
라벨이 `phonetic=True`를 거치면서 평파열음화로 **종성이 표준발음법 7종성(ㄱㄴㄷㄹㅁㅂㅇ)으로
수렴**하기 때문이다. 겹받침·ㅅ·ㅊ 종성은 아예 나타나지 않는다.

| 구성 | 개수 | 비고 |
|---|---|---|
| 특수 | 3 | `<pad>`(CTC blank, id 0) · `<unk>` · `\|`(어절 경계) |
| 초성 | 18 | 무음 ㅇ 제외 — 토큰을 만들지 않고 중성만 남긴다 |
| 중성 | 21 | 단모음·이중모음 전체 |
| 종성 | 7 | 평파열음화가 수렴시킨 대표음 |
| **합계** | **49** | |

**위치 구분**을 쓴다 — 초성 ㄱ(파열)과 종성 ㄱ(미파열 [k̚])은 다른 소리라 `o:ㄱ`/`c:ㄱ`로
나눈다. 덕분에 '종성 발음'만 따로 채점할 수 있어 발성 교육에 직결된다.

1,205 → 49가 되면 D-GOP 엔트로피 신호 자체가 안정된다(지금은 롱테일 1,200여 클래스가
`normalized_entropy`를 지배해 '분포가 평평하다'는 신호가 흐려진다).

`<pad>`를 id 0에 두는 것은 `dgop_acoustic.align_targets`의 기본 `blank_token`과 맞추기 위함이다.

## 3. 선결 과제 — 발음 규칙 (⚠️ 최우선)

CTC 라벨은 **실제로 소리 난 것**과 일치해야 한다. 어긋나면 학습 전체가 오염된다.
`engine.to_pronounced_syllables()`가 연음·구개음화·격음화·겹받침·ㅎ탈락은 처리하지만,
2026-09-08 실측 결과 **네 개 규칙 계열이 통째로 빠져 있다**:

| 입력 | 현재 출력 | 기대 | 빠진 규칙 |
|---|---|---|---|
| 옷 | ㅗㅅ | 옫 | 평파열음화(음절 끝소리 규칙) |
| 꽃 | ㄲㅗㅊ | 꼳 | 평파열음화 |
| 앞 | ㅏㅍ | 압 | 평파열음화 |
| 국물 | ㄱㅜㄱ ㅁㅜㄹ | 궁물 | 비음화 |
| 닫는 | ㄷㅏㄷ ㄴㅡㄴ | 단는 | 비음화 |
| 밥물 | ㅂㅏㅂ ㅁㅜㄹ | 밤물 | 비음화 |
| 신라 | ㅅㅣㄴ ㄹㅏ | 실라 | 유음화 |
| 설날 | ㅅㅓㄹ ㄴㅏㄹ | 설랄 | 유음화 |
| 학교 | ㅎㅏㄱ ㄱㅛ | 학꾜 | 경음화 |
| 있다 | ㅣㅆ ㄷㅏ | 읻따 | 평파열음화 + 경음화 |

적용 순서가 있다: **평파열음화 → 비음화 → 유음화 → 경음화**. 비음화는 대표음(ㄱ/ㄷ/ㅂ)을
전제하므로 평파열음화가 먼저 돌아야 한다(밭만 → 받만 → 반만).

이 함수는 아바타 입모양 엔진과 채점이 공유하므로, 고치면 **앱 전체 발음 정확도도 함께 오른다**.
viseme이 실제로 바뀌는 경우는 종성 ㅊ/ㅈ → ㄷ(10→6)과 비음화 종성 ㄱ → ㅇ 정도다.

## 4. 학습 로드맵

| 단계 | 내용 | H100 | 비용 |
|---|---|---|---|
| **A-0 스모크** | 30분 subset으로 데이터로더→학습→저장 왕복. **여기서 실제 처리량 실측** | ~1h | ~$3 |
| **A-1 Scorer** | Zeroth 51.6h. ① encoder freeze·head만 2~3ep ② 전체 unfreeze·low LR 10~12ep | ~13h | ~$35 |
| **A-2 Aligner** | A-1에서 시작, `deaf_speech_synthesis`로 on-the-fly severity 0~4 증강 | ~4h | ~$10 |
| **A-3 평가·연결** | 변별력 지표 측정 + `assess_text` 배선 | ~1h | ~$3 |

**총 ~$50.** 시간은 RTF 60x 가정한 추정이라 A-0에서 실측 후 확정한다.

- A-1을 2스테이지로 나누는 이유: 랜덤 초기화된 새 `lm_head`가 처음부터 full backprop을 타면
  사전학습 encoder를 망가뜨린다. CNN feature extractor는 전 구간 freeze(표준).
- A-2에서 **severity 0을 반드시 섞는다** — 저하 발화만 보면 정상 발화 정렬 능력을 잃는다.

## 5. 평가 지표 — WER이 아니다

축 A의 성패는 인식률이 아니라 **점수의 변별력**이다.

| 지표 | 목표 | 의미 |
|---|---|---|
| **단조성** (Spearman ρ) | ≥ 0.9 | severity 0→4에서 D-GOP가 단조 감소하는가 |
| **분리도** (AUC) | ≥ 0.85 | 정상 vs severity 3+ 점수 분포가 갈리는가 |
| **정렬 견고성** | severity 4에서 aligned ≥ 95% | Aligner가 제 역할을 하는가 |
| CER (Zeroth test 1.2h) | 참고용 | Scorer sanity check |

1·2번이 진짜 합격선이다. `dgop.py`가 순수 함수라 결정론적으로 측정된다.

## 6. 데이터 — Zeroth-Korean

| 항목 | 값 |
|---|---|
| 출처 | **`kresnik/zeroth_korean`** (Hugging Face, parquet) — 원본은 OpenSLR 40 |
| 규모 | 학습 51.6시간 22,263발화 105명 / 테스트 1.2시간 457발화 10명 |
| 스키마 | `audio`(16kHz) · `text` · `id` · `speaker_id` · `chapter_id` · `path` |
| 라이선스 | **CC BY 4.0** (인증·가입 불필요, 2026-09-08 확인) |

원본 `zeroth_korean.tar.gz`(9.6GB) 대신 HF parquet 배포판을 쓴다. **우리가 미세조정할
베이스 체크포인트 `kresnik/wav2vec2-large-xlsr-korean`과 같은 저자**의 정리본이라
tar 레이아웃을 추측할 필요가 없고 `load_dataset` 한 줄로 끝난다.

**라벨 사전점검 결과(실제 전사 500문장, 2026-09-08)**

| 점검 | 결과 |
|---|---|
| OOV | **0건** — 49토큰이 전부 커버 |
| 비한글 문자 | **없음** — 구두점·숫자·로마자 전무, 텍스트 정규화 불필요 |
| 라벨 길이 | 최소 51 / 중앙 103 / 최대 200 토큰 |
| vocab 사용률 | 47/49 (미관측 없음, 나머지 2는 특수토큰) |

⚠️ **CTC 길이 제약** — 출력 프레임 수(≈50fps)가 라벨 길이보다 짧으면 손실이 inf가 되어
학습이 망가진다. 중앙 103토큰이면 최소 2.1초, 최대 200토큰이면 4초가 필요하다.
`scripts/prepare_zeroth_labels.py --check-duration`으로 전수 확인하고,
`train_jamo_ctc.py`가 학습 직전에 위반 표본을 자동 제외한다.

OLKAVS(AI Hub, 음성 1,150h)는 본인인증·TB급 다운로드가 필요해 부트스트랩에 쓰지 않는다.
도착하면 A-1을 더 큰 데이터로 재학습하는 선택지로 둔다(`scripts/preprocess_olkavs.py --mode audio`).

## 7. RunPod 운영

- **Network Volume**에 데이터·체크포인트 — Pod이 죽어도 유지
- 체크포인트는 **HF Hub private repo**에도 push — 볼륨 사고 대비
- **Interruptible(spot)** + `resume_from_checkpoint`로 40~60% 절감
- Pod 첫 부팅 시 `scripts/check_ml_env.py` 실행 → `CUDA 사용 가능: True` 확인

## 8. 로컬 선행 작업 (GPU 불필요)

RunPod을 켜기 전에 여기까지 끝내야 GPU 시간을 태우지 않는다.

| # | 작업 | 산출물 | 상태 |
|---|---|---|---|
| 1 | §3의 네 규칙을 `phonetic=True` 모드로 추가 | `backend/engine.py`, `backend/scoring.py`, `test_phonetic_rules.py` | ✅ 14/14 통과 |
| 2 | 자모 CTC vocab | `backend/jamo_vocab.py`, `test_jamo_vocab.py` | ✅ 49토큰, OOV 0건 |
| 3 | Zeroth 라벨 사전점검·변환 | `scripts/prepare_zeroth_labels.py` | ✅ 실전사 500문장 검증 |
| 4 | A-1 학습 스크립트 + CPU 형상 검증 | `scripts/train_jamo_ctc.py --smoke` | ✅ 합성 파형 1 step 통과 |
| 5 | A-2 Aligner 학습 스크립트 | `scripts/train_aligner.py --smoke` | ✅ 증강 경로까지 검증 |
| 6 | 변별력 평가 스크립트 | `scripts/eval_dgop_discrimination.py`, `test_eval_dgop_discrimination.py` | ✅ 지표 4/4 통과 |
| 7 | `assess_text`를 aligner/scorer 2모델로 분리 | `backend/dgop_acoustic.py`, `backend/main.py` | ✅ 합성 분포 테스트 2종 추가 |

**7번 배선** — `/api/speak/assess`의 환경변수가 둘로 갈라졌다.

| 변수 | 용도 |
|---|---|
| `DGOP_ALIGNER_ID` | 강제정렬용(A-2 산출물) |
| `DGOP_SCORER_ID` | 채점용(A-1 산출물). 생략 시 정렬기와 동일 |
| `DGOP_MODEL_ID` | 구 변수명 — 하위호환으로 정렬기 겸 채점기 |

두 모델의 프레임 수가 다르면 구간을 옮길 수 없으므로 `phone_confidences`가 즉시 `ValueError`를
낸다(조용히 틀린 점수를 내지 않는다). 어절 경계 `|` 토큰은 정렬은 제약하되 점수 집계에서 제외된다.

**중요한 설계 판단(1번)**: `to_pronounced_syllables()`는 아바타 입모양 엔진과 공유하는
함수다. 확인해보니 원래의 "규칙 생략"은 viseme 경로에서는 **옳은 판단**이었다 —
비음화 ㄱ→ㅇ은 둘 다 viseme 7이고 경음화도 전부 같은 그룹이라 입모양이 안 바뀐다.
그래서 기본 경로는 손대지 않고 `phonetic=True` 플래그로만 새 규칙을 켠다.
`test_phonetic_rules.test_default_path_unchanged`가 이 불변을 지킨다.

**환경 메모**: transformers 5.x에서 `TrainingArguments`의 `warmup_ratio`·`group_by_length`가
제거됐다. RunPod에서도 로컬과 같은 버전을 쓰도록 `requirements-ml.txt`에 `>=5.16.0`으로
고정하고 `accelerate`를 추가했다(Trainer 필수 런타임).

⚠️ **torchaudio 상한(중요)**: `torchaudio.functional.forced_align`이 **2.9에서 제거**된다
(2026-09-08 실기 확인 — RunPod H100/torchaudio 2.8.0에서 deprecation 경고 확인).
`dgop_acoustic.align_targets`가 이 API에 전적으로 의존하므로 `<2.9.0` 상한을 걸었다.
2.9 이상으로 올리려면 **CTC 강제정렬(Viterbi)을 자체 구현**하거나 대체 라이브러리로
옮겨야 한다 — 축 B 후속 과제로 남긴다. 알고리즘 자체는 단순해서 자체 구현이 현실적이고,
그러면 무거운 torchaudio 의존도 함께 덜어낼 수 있다.

---

## 실행 결과 (2026-09-08, RunPod H100 SXM)

### 학습

| 단계 | 설정 | 시간 | 결과 |
|---|---|---|---|
| A-1 stage1 (head만) | 3 epoch, lr 1e-3, 학습 파라미터 0.1M | 5.8분 | eval_loss 0.348 → **0.322** |
| A-1 stage2 (전체) | 12 epoch, lr 3e-5, 학습 파라미터 311.3M | **59분** | eval_loss → **0.2087** |
| A-2 Aligner | 4 epoch, severity 0~4 증강 | **20.8분** | eval_loss 1.299 → **1.147** |

batch 16 / grad_accum 1 (유효 배치 16), bf16, workers 24. GPU 사용률 87~99%, 45GB/80GB.
A-1 총 65분으로 계획서 추정(35~90분) 안에 들어왔다.

### A-3 변별력 — **축 A 합격**

| 지표 | 베이스라인 | 축 A | 목표 | |
|---|---|---|---|---|
| 단조성 −ρ(sev, score) | 0.840 | **0.979** | 0.90 | ✅ |
| 분리도 AUC(0 vs 3+) | 0.998 | **0.999** | 0.85 | ✅ |
| 정렬 견고성(sev 4) | 1.000 | **1.000** | 0.95 | ✅ |

severity별 D-GOP 평균:

| severity | 0 | 1 | 2 | 3 | 4 |
|---|---|---|---|---|---|
| 베이스라인 | 6.65 | 3.58 | 2.07 | 1.15 | **1.25 ↑** |
| 축 A | 9.51 | 2.74 | 1.49 | 0.61 | **0.30** |

베이스라인은 severity 3→4에서 점수가 **되레 올라가** 심한 저하를 구별하지 못한다.
축 A 모델은 끝까지 단조 감소한다 — 이것이 §0에서 세운 가설의 실증이다.

### 정직한 한계 두 가지

**① naive(표준 GOP)도 이 실험에서는 단조롭다.** 단조성이 naive 0.995 > D-GOP 0.979로
오히려 근소하게 높다. §0의 "표준 GOP는 뭉갠 발화에서 과신한다"는 예상은 **합성 저하에
대해서는 성립하지 않았다** — deaf_speech_synthesis의 교란(저역통과·잡음·포먼트 이동)은
분포를 실제로 평평하게 만들어 naive 점수도 함께 떨어뜨린다. 과신 문제는 **실제 농인
발화**에서 검증해야 하며, 그 데이터가 아직 없다. D-GOP의 불확실성 보정이 값을 하는지는
미결로 남는다.

**② 점수 스케일이 사용 불가 수준으로 압축돼 있다.** 깨끗한 발화(severity 0)의 D-GOP가
9.51/100이다. 학습자에게 그대로 보여줄 수 없다. 원인은 구간 평균 분포에 CTC blank가
지배적인 프레임이 섞여 target_prob이 낮게 나오기 때문으로 보인다. **점수 보정(calibration)
단계가 앱 연결 전에 반드시 필요하다** — 예컨대 정상 발화 분포를 기준으로 백분위 매핑.

### 실행 중 잡은 문제 (전부 수정·커밋됨)

로컬 검증만으로는 드러나지 않았던 것들이다.

| # | 문제 | 조치 |
|---|---|---|
| 1 | `torchaudio>=2.9.0` 요구 — `forced_align`이 2.9에서 **제거 예정** | `<2.9.0` 상한 |
| 2 | `torchcodec` 누락 — datasets 5.x가 오디오 디코딩을 이쪽으로 옮김 | 추가, `0.6.x` 고정(최신판은 CUDA 13 요구) |
| 3 | datasets 5.x가 `AudioDecoder` 반환 — `row["audio"]["array"]` 불통 | `backend/hf_audio.py` 신설 |
| 4 | PEP 668로 시스템 pip 설치 차단 | `venv --system-site-packages`로 CUDA torch 상속 |
| 5 | `num_proc=os.cpu_count()` — Pod은 224코어 | 상한 32 |
| 6 | A-2가 `set_transform`인데 Trainer가 원본 컬럼 제거 | `remove_unused_columns=False` |
| 7 | eval_loss 최적점이 중간 epoch일 수 있음 | `load_best_model_at_end` |
| 8 | `ctc_log_probs`가 항상 CPU — 평가가 비현실적으로 느림 | `resolve_device()`로 GPU 자동 사용 |
