# 축 A 실행 절차서 — RunPod

> 작성 2026-09-08. 계획·근거는 `docs/axis-a-training-plan.md`, 여기는 **실행 순서·시간·비용**만.
> 로컬 선행 작업(§8-1~7)은 완료 상태이므로 이 문서는 Pod을 켜는 시점부터 시작한다.

---

## 0. 먼저 — 이전 추정치를 정정한다

계획서에 적었던 **"A-1 13시간 / 총 $50"은 과대 추정**이었다. 재생 대비 처리량(RTF)을 60배로
가정했는데, 그건 CPU급 수치이고 H100에는 맞지 않는다. FLOPs 기반으로 다시 계산하면:

| 하드웨어 | micro-batch당 | epoch당 | 패딩 낭비 +40% 반영 |
|---|---|---|---|
| H100 SXM @25% MFU | 35.8 ms | 1.7분 | **2.3분** |
| H100 SXM @15% MFU | 59.7 ms | 2.8분 | **3.9분** |
| A100 80GB @25% MFU | 113.7 ms | 5.3분 | 7.4분 |

(wav2vec2-large 302M 트랜스포머, batch 8, 발화 평균 8.34초 = 417프레임, gradient checkpointing
포함 micro-batch당 ≈ 8.9 TFLOP 기준. `transformers` 5.x에 `group_by_length`가 없어 패딩 낭비를
넉넉히 잡았다.)

**결론: A-1은 13시간이 아니라 1~1.5시간이다. 총 비용도 $50이 아니라 $15 안팎.**

---

## 1. Pod 사양

| 항목 | 권장 | 비고 |
|---|---|---|
| GPU | **H100 SXM 80GB** ×1 | A100으로도 되지만 2~3배 느리다. 총비용은 비슷하고 시간만 늘어난다 |
| vCPU | 16 이상 | A-2 증강이 CPU를 쓴다(아래 §4) |
| 컨테이너 디스크 | 40 GB | |
| **Network Volume** | **100 GB** | Pod이 죽어도 남는다. 체크포인트가 여기 있어야 재개된다 |
| 템플릿 | PyTorch 2.x + CUDA 12.x | |

**Network Volume을 반드시 쓴다.** Trainer 체크포인트 하나가 모델 1.27GB + Adam 상태 2.54GB ≈
**3.8GB**다. `save_total_limit=2` × 2스테이지면 A-1만 ~15GB를 점유한다.

---

## 2. 최초 세팅 (~15분)

```bash
# Network Volume에 작업 공간을 잡는다(/workspace가 볼륨 마운트 지점)
cd /workspace && git clone https://github.com/n1a2m3y4u5n/liplab.git && cd liplab
git checkout feat/content-scale     # 축 A 작업 브랜치
# (저장소가 공개라 Pod에서 인증 없이 그대로 받아진다)

# ⚠️ 순수 venv를 만들지 않는다. RunPod PyTorch 템플릿에는 이 GPU에 맞게 빌드된 CUDA torch가
#    이미 깔려 있는데, 깨끗한 venv는 그걸 가려서 pip가 PyPI에서 torch를 다시 받는다
#    (2.5GB, 느리고 CUDA 빌드가 어긋날 수 있다).
#    그렇다고 시스템 파이썬에 바로 설치할 수도 없다 — PEP 668로 pip가 차단된다
#    (2026-09-08 실기 확인). 답은 **시스템 패키지를 상속하는 venv**다.
python -m venv --system-site-packages /workspace/venv
source /workspace/venv/bin/activate
echo 'source /workspace/venv/bin/activate' >> ~/.bashrc

# 1) 먼저 템플릿의 torch가 그대로 보이는지 확인한다
python -c "import torch; print(torch.__version__, torch.version.cuda, torch.cuda.is_available())"

# 2) torch를 건드리지 않고 나머지만 설치
pip install -r backend/requirements.txt
pip install "transformers>=5.16.0" "datasets>=3.0.0" accelerate jiwer soundfile librosa

# HF 캐시도 볼륨에 둔다 — Pod 재생성 때 2.88GB를 다시 받지 않는다
export HF_HOME=/workspace/hf
echo 'export HF_HOME=/workspace/hf' >> ~/.bashrc

python scripts/check_ml_env.py    # ← "CUDA 사용 가능: True" 확인
```

> 1)에서 `cuda`가 `None`이거나 torch가 2.4 미만이면 템플릿을 잘못 고른 것이다.
> Pod을 지우고 PyTorch 2.x + CUDA 12.x 템플릿으로 다시 만드는 편이 빠르다.
> (torch **상한**은 `<2.9.0`이다 — `requirements-ml.txt` 참고. 2.9 이상이면 그쪽을 먼저 본다.)

`CUDA 사용 가능: False`면 여기서 멈춘다 — 그대로 학습하면 CPU로 돌아 수십 배 느려진다.

### 2.1 두 번째 세션부터 (Pod을 다시 Start한 경우)

Network Volume에 저장소·HF 캐시·체크포인트가 그대로 있으므로 §2 전체를 다시 하지 않는다.
**Pod을 Start하면 IP·포트가 바뀐다** — 콘솔 Connect 탭에서 새로 확인한다.

⚠️ **SSH가 `Permission denied`로 막힐 수 있다**(2026-09-09 실기). Start 시 컨테이너의
`PUBLIC_KEY` 환경변수가 비어 있으면 계정에 등록된 공개키가 `authorized_keys`에 주입되지
않는다. 계정 키 등록 여부와 무관하다(프록시 `ssh.runpod.io`도 함께 막힌다). 해결:

```bash
# Pod env에 공개키를 넣고 재시작한다(JUPYTER_PASSWORD 같은 기존 env를 함께 보내야 덮이지 않는다)
curl -X PATCH https://rest.runpod.io/v1/pods/<podId> \
  -H "Authorization: Bearer $RUNPOD_API_KEY" -H "Content-Type: application/json" \
  -d "{\"env\":{\"PUBLIC_KEY\":\"$(cat ~/.ssh/id_ed25519.pub)\",\"JUPYTER_PASSWORD\":\"<기존값>\"}}"
```

PATCH가 컨테이너를 재시작시키므로 **포트 매핑이 또 바뀐다** —
`GET /v1/pods/<podId>`의 `portMappings["22"]`로 다시 확인한다(`runtime`이 `null`이어도
`portMappings`는 채워진다).

```bash
source /workspace/venv/bin/activate
cd /workspace/liplab && git pull origin feat/content-scale   # ← 로컬 수정분을 먼저 push해 둘 것
export HF_HOME=/workspace/hf
ls /workspace/ckpt/scorer /workspace/ckpt/aligner            # 체크포인트 생존 확인
python scripts/check_ml_env.py
```

> ⚠️ **2026-09-14 실기에서 밟은 함정 둘 — 둘 다 시간을 태웠다.**
>
> 1. **포트는 재시작마다 바뀐다.** Start 직후 SSH가 붙었는데도 컨테이너가 한 번 더 재시작되면
>    포트가 또 옮겨간다(실측 13471 → 19145). SSH가 `Connection refused`면 Pod이 죽은 게 아니라
>    **포트가 바뀐 것**이다. 대기·재시도 루프는 **매 회차에 `portMappings["22"]`를 다시 읽는다.**
>    고정 포트로 10분을 두드려 $0.6을 버렸다. 컨테이너 생존 여부는
>    `https://<podId>-8888.proxy.runpod.net`이 302를 주는지로 따로 확인된다.
> 2. **볼륨의 저장소가 9/8 상태로 멈춰 있었다.** `git pull`이 9/9에 Pod에서 생성된 untracked
>    `backend/data/dgop_calibration.json`과 충돌해 거부되고, 그러면
>    `scripts/{upload_ckpt_hf,dump_gop_features}.py`가 **없는 상태로 남는다.** 실제로 업로드와 E1이
>    `No such file or directory`로 즉사했다. 순서를 이렇게 한다:
>
> ```bash
> mv -f backend/data/dgop_calibration.json /workspace/logs/dgop_calibration.pod-backup.json
> git pull origin feat/content-scale && git rev-parse --short HEAD   # HEAD를 눈으로 확인한다
> ls scripts/upload_ckpt_hf.py scripts/dump_gop_features.py          # 둘 다 있어야 한다
> ```
>
> 백그라운드로 던질 때는 **`python -u`**를 쓴다. 버퍼링 때문에 로그가 비어 보이면 진행 중인지
> 죽은 것인지 구별할 수 없다.

---

## 3. A-0 스모크 (~30분, 대부분 다운로드)

```bash
# 3-1. 로컬에서 검증한 테스트를 GPU 환경에서 재확인 (1분)
cd backend && PYTHONPATH=. python test_phonetic_rules.py && PYTHONPATH=. python test_jamo_vocab.py \
  && PYTHONPATH=. python test_dgop_acoustic.py && cd ..
python scripts/test_eval_dgop_discrimination.py

# 3-2. 학습 배관 형상 검증 — 데이터셋 없이 합성 파형 1 step (2분)
python scripts/train_jamo_ctc.py --smoke
python scripts/train_aligner.py --smoke

# 3-3. 데이터셋 내려받고 라벨 전수 점검 (2.88GB, ~20분)
python scripts/prepare_zeroth_labels.py --split train --check-duration
python scripts/prepare_zeroth_labels.py --split test  --check-duration
```

**3-3이 이 단계의 핵심이다.** OOV와 CTC 길이 위반을 여기서 잡는다. 길이 위반이 나오면
`train_jamo_ctc.py`가 자동 제외하지만, 제외 건수가 전체의 5%를 넘으면 batch 구성을
다시 봐야 한다.

**3-4. 처리량 실측** — A-1을 1 epoch만 돌려 실제 epoch 시간을 잰다. 이 수치로 이후 예산을 확정한다.

```bash
python scripts/train_jamo_ctc.py --out /workspace/ckpt/probe \
  --stage1-epochs 1 --stage2-epochs 0 --bf16 --workers 16
```

---

## 4. A-1 Scorer 학습 (1~1.5시간)

```bash
python scripts/train_jamo_ctc.py \
  --out /workspace/ckpt/scorer \
  --stage1-epochs 3 --stage2-epochs 12 \
  --batch 8 --grad-accum 2 --bf16 --workers 16 \
  2>&1 | tee /workspace/logs/a1.log
```

| 항목 | 값 |
|---|---|
| optimizer step | stage1 4,176 + stage2 16,704 = **20,880** |
| epoch당 | 2,783 micro-batch / 1,392 step |
| 예상 시간 | **35~90분** (2.3~3.9분/epoch × 15) |

`--workers`를 빼먹지 말 것. `dataloader_num_workers` 기본값이 0이라 전처리가 메인 프로세스에서
직렬로 돌아 GPU가 논다.

**보는 것**: loss가 stage1에서 급락한 뒤(랜덤 head가 자리를 잡는 구간) stage2에서 완만히 내려가야
한다. stage2 초반에 loss가 튀면 LR(3e-5)이 높은 것이다.

---

## 5. A-2 Aligner 학습 (~40분)

```bash
python scripts/train_aligner.py \
  --from /workspace/ckpt/scorer --out /workspace/ckpt/aligner \
  --epochs 4 --batch 8 --grad-accum 2 --bf16 --workers 16 \
  2>&1 | tee /workspace/logs/a2.log
```

증강 비용은 실측했다 — `simulate_deaf_speech`가 발화당 **20.5ms**(severity 평균, RTF 407x).

| 워커 수 | 증강 시간/epoch |
|---|---|
| 0 (기본값) | 7.6분 ← **GPU 연산보다 느려 병목이 된다** |
| 8 | 0.95분 |
| 16 | 0.48분 |

워커 8개 이상이면 증강이 GPU 연산에 가려 사라진다. 예상 시간 **10~25분**(4 epoch).

---

## 6. A-3 변별력 평가 (~20분)

> ✅ 2026-09-09 재측정 완료(A-5 참고). 구간 뭉갬 버그 수정 후 같은 체크포인트로 다시 돌려
> **단조성 0.998 / AUC 1.000 / 정렬 1.000 — 축 A 합격**을 받았다. 베이스라인도 다시 쟀고
> 3→4 역전(1.97 → 2.00)이 재현돼 버그 탓이 아님이 확인됐다.
>
> 🔴 **2026-09-15 — 다시 돌려야 한다.** 재측정 사유는 체크포인트가 아니라 **채점식 교체**다.
> `dgop.dgop_phone`이 naive로 바뀌어(A-6) **원점수 눈금 자체가 달라졌다.** "체크포인트를 바꿀
> 때만 다시 돈다"는 위 문장만 보고 건너뛰지 말 것 — 채점식이 바뀌어도 다시 돌아야 한다.
> 이어서 **§6.5 재적합까지 같은 세션에서** 끝낸다(원점수가 바뀌면 앵커도 무효다).

체크포인트는 이제 HF에 있다(§7). 볼륨 없이 아무 DC·아무 GPU에서 돌릴 수 있고,
**비공개 저장소라 `HF_TOKEN`(읽기 권한)이 필요**하다 — `huggingface_hub`가 환경변수를
자동으로 읽으므로 export만 해 두면 코드 수정은 없다(2026-09-15 확인).

```bash
export HF_TOKEN=hf_...          # 읽기 권한. 비공개 저장소 접근에 필수

# 미세조정 전 베이스라인 — 비교 기준(공개 체크포인트라 토큰 없이도 된다)
python scripts/eval_dgop_discrimination.py --limit 50 2>&1 | tee /workspace/logs/a3-base.log

# 축 A 산출물 — HF 저장소 id로 직접 받는다(볼륨 경로가 있으면 그 경로를 써도 된다)
python scripts/eval_dgop_discrimination.py \
  --aligner duadnwls/liplab-dgop-aligner --scorer duadnwls/liplab-dgop-scorer --limit 50 \
  2>&1 | tee /workspace/logs/a3-after.log
```

| 지표 | 합격선 |
|---|---|
| 단조성 −ρ(severity, D-GOP) | ≥ 0.90 |
| 분리도 AUC(severity 0 vs 3+) | ≥ 0.85 |
| 정렬 견고성(severity 4) | ≥ 0.95 |

세 줄 모두 PASS면 축 A 완료. naive(표준 GOP) 열이 나란히 찍히므로, D-GOP의 불확실성 보정이
실제로 과신을 막았는지 같은 표본에서 바로 확인된다.

---

## 6.5 A-4 점수 보정 (~20분)

A-3이 PASS해도 원점수는 그대로 못 쓴다 — 합격선(50·65)과 비교조차 되지 않는 눈금이다.
**모델을 앱에 연결하기 전에 반드시 여기를 돌린다.**

> ✅ **2026-09-09 재적합 완료.** severity 중앙값 78.15 / 31.65 / 15.20 / 2.90 / 0.85로
> 앵커 5개 전부 채택됐고 `backend/data/dgop_calibration.json`으로 커밋됐다.
>
> 🔴 **2026-09-15 — 그 앵커는 무효다.** 채점식이 naive로 바뀌어 원점수 눈금이 달라졌다
> (A-6). 재적합 사유는 체크포인트 교체만이 아니라 **채점식 교체도 포함**이다.
> 재적합 전까지 앱의 D-GOP 경로(`DGOP_ALIGNER_ID`)를 켜지 않는다.
>
> 실제 소요(H100, 50발화): A-3 축 A 약 12분 + 베이스라인 약 9분 + A-4 약 11분.
> Pod 단가는 런북 §8의 $2.99가 아니라 **$3.49/hr**이었다(2026-09-09 실측).

**먼저 GPU 없이 배관부터 확인한다** — 인자 오타나 배관 오류를 Pod에서 처음 만나면 20분·$1을
그대로 버린다. 합성 발화·합성 채점기로 측정 루프부터 JSON 저장까지 그대로 탄다:

```bash
python scripts/fit_dgop_calibration.py --smoke
```

```bash
python scripts/fit_dgop_calibration.py \
  --aligner duadnwls/liplab-dgop-aligner --scorer duadnwls/liplab-dgop-scorer --limit 50 \
  --out /workspace/liplab/backend/data/dgop_calibration.json 2>&1 | tee /workspace/logs/a4-cal.log
```

앵커 적합이 실패해도(원점수가 severity를 거스르면 실패한다) severity별 중앙값은
`<out>.medians.json`에 남는다 — 측정을 다시 할 필요는 없다.

severity별 원점수 중앙값을 재서 앵커를 만들고 JSON으로 남긴다(방법·근거는
`docs/axis-a-training-plan.md` §A-4). 확인할 것:

| 확인 | 기대 |
|---|---|
| 보정 점수 열 | severity 0→4가 90 / 72 / 58 / 40 / 20 근처 |
| `⚠️ 제외했습니다` 경고 | 없어야 한다. 뜨면 그 severity를 모델이 구별하지 못한다는 뜻 |
| 중앙값 vs A-3 평균 | 크게 벌어지면 소수 발화가 평균을 끌고 있다는 신호 |

보정 자체는 단조 변환이라 **보정을 새로 맞췄다는 이유로** A-3을 다시 돌릴 필요는 없다
(순위를 바꾸지 않으므로). 이번 세션에 §6을 다시 도는 것은 별개 이유 — 구간 뭉갬 버그 수정으로
**원점수 자체가 바뀌었기** 때문이다.

**이 JSON은 체크포인트 전용이다** — 모델을 바꾸면 이 단계부터 다시 한다.

---

## 7. 산출물 회수

**현황(2026-09-09)**: 저장소 2개와 모델 카드는 **이미 만들어 뒀다**(private).
가중치만 비어 있다 — 아래 §7.1 참고.

- `duadnwls/liplab-dgop-scorer`
- `duadnwls/liplab-dgop-aligner`

```bash
# Pod 안에서. 최종 모델만 올린다(Trainer 옵티마이저 상태 제외 → 19GB가 아니라 2.5GB)
HF_TOKEN=hf_... python scripts/upload_ckpt_hf.py /workspace/ckpt/scorer  duadnwls/liplab-dgop-scorer
HF_TOKEN=hf_... python scripts/upload_ckpt_hf.py /workspace/ckpt/aligner duadnwls/liplab-dgop-aligner
```

스크립트가 업로드 후 원격 파일 목록·크기를 로컬과 대조해 검증하고, 최상위에 가중치가
없으면 아예 중단한다. `stage*`·`checkpoint-*`는 학습 재개용이라 올리지 않는다.

> ⚠️ **`allow_patterns`에 와일드카드를 쓰지 말 것.** `huggingface_hub`의 fnmatch는 `/`도
> `*`로 먹어서 `"*.json"`이 `stage1_head/config.json`·`checkpoint-4176/config.json`까지
> 잡는다(실측 확인). 스크립트는 최상위 파일명을 실행 시점에 나열하는 방식을 쓴다.

### 7.1 백업이 막힌 이유 — AP-IN-2 용량 (2026-09-09)

Pod을 **정지하면 GPU 예약이 풀린다.** A-3·A-4를 마치고 과금을 줄이려 정지했더니 그 사이
호스트의 H100을 다른 사용자가 가져갔고, 이후 `start`가 계속 실패했다:

```
start pod: There are not enough free GPUs on the host machine to start this pod.
```

우회로가 없다 — 네트워크 볼륨은 데이터센터에 묶이는데 **AP-IN-2에는 H100 한 종류만**
존재하고(`gpuAvailability`로 확인) 당시 `available=False`였다. 값싼 GPU($0.19~)로 볼륨만
붙이려 해도 그 DC에 없고, CPU 전용 Pod도 `no instances currently available`이었다.
90초 간격 24회 재시도 전부 실패.

**교훈**: 볼륨에서 뭔가 꺼내야 한다면 **Pod을 끄기 전에 꺼낸다.** 정지는 과금을 줄이지만
재시작을 보장하지 않는다.

### 7.2 우회로를 공식 문서로 재조사한 결과 (2026-09-14)

§7.1의 "우회로가 없다"는 **2026-09-09 시점** 판단이다. RunPod 공식 문서로 다시 훑은 결과는 이렇다.

| 경로 | 결론 | 근거 |
|---|---|---|
| **S3 호환 API** — Pod 없이 볼륨 파일을 꺼낸다 | ❌ 지원 데이터센터 15곳(EU·US)에 **AP-IN-2가 없다** | [S3-compatible API](https://docs.runpod.io/storage/s3-api) |
| **볼륨을 다른 DC로 이전** | ❌ 공식 방법이 **양쪽에 Pod을 띄워** `runpodctl`/`rsync`로 복사하는 것이다 — 원본 쪽 Pod이 떠야 해서 같은 병목 | [Network volumes](https://docs.runpod.io/storage/network-volumes) |
| **(A) GPU 0개로 시작** | 🔸 공식 기능이다 — *"Runpod gives you the option to start the Pod with zero GPUs"*. 데이터 회수용이고 CPU가 적어 연산에는 못 쓴다. **§7 업로드는 CPU로 충분**하므로 이게 되면 백업만은 끝낼 수 있다. 단 문서 설명이 **로컬 볼륨 Pod 기준**이라 네트워크 볼륨 Pod에도 적용되는지는 미확인이고, 버튼·API 이름과 과금도 문서에 없다 | [Zero GPU Pods](https://docs.runpod.io/pods/troubleshooting/zero-gpus) |
| **(B) `start` 재시도 대신 새 Pod 배포** | 🔸 정지된 Pod은 **원래 물리 머신에 묶인다** — 그 머신의 H100이 비어야 `start`가 성공한다. 같은 볼륨을 붙인 **새 Pod은 AP-IN-2의 다른 머신**에도 배정될 수 있다. 다음 재시도는 `start` 반복이 아니라 DC 여유(`gpuAvailability`) 확인 + 새 Pod 배포로 간다 | 위 Zero GPU 문서, [Manage Pods](https://docs.runpod.io/pods/manage-pods) |
| **Pod 마이그레이션(베타)** | ❓ 재시작 때 GPU가 없으면 새 머신으로 옮겨 주는 기능. 같은 DC 한정인지, 네트워크 볼륨 Pod에도 되는지는 문서에 없다 | [Pod migration](https://docs.runpod.io/pods/troubleshooting/pod-migration) |

- 네트워크 볼륨의 `/workspace`는 **stop이든 terminate든 보존된다**고 문서에 명시돼 있다
  ([Manage Pods](https://docs.runpod.io/pods/manage-pods)). (B)에서 기존 Pod을 종료해도 체크포인트는 안전하다.
- **§7 백업만 끝나면 이후 실험은 AP-IN-2에 묶이지 않는다** — HF에서 체크포인트를 받아 아무 DC·아무
  GPU에서 재현할 수 있다(`docs/axis-b-scorer-redesign.md` §2). 그래서 (A)는 백업 하나만 풀어도
  E1·E2까지 같이 풀리는 경로다.
- `POST /v1/pods/{podId}/start`에는 **요청 본문 스키마가 문서에 없다**
  ([start 엔드포인트](https://docs.runpod.io/api-reference/pods/POST/pods/podId/start)) — GPU 개수를
  지정해 켜는 방법이 API 문서로 확인되지 않는다. 0 GPU 시작은 **콘솔에서 확인하는 편이 빠르다.**
- ⚠️ **REST API v1은 2026-11-15에 폐지된다**([API overview](https://docs.runpod.io/api-reference/overview)).
  §2.1의 `rest.runpod.io/v1` PATCH도 그때까지만 유효하니, 그 전에 v2로 옮긴다.

앱에 연결할 때는 환경변수 둘만 설정한다(미설정이면 기존 전사 경로 그대로 — 안전한 기본값):

```bash
DGOP_ALIGNER_ID=duadnwls/liplab-dgop-aligner
DGOP_SCORER_ID=duadnwls/liplab-dgop-scorer
HF_TOKEN=hf_...        # ⚠️ 두 저장소가 비공개다 — 없으면 로드 실패 후 전사 경로로 폴백한다
```

폴백은 조용하지 않다 — 실패하면 서버 로그에 `[WARN] D-GOP 경로 실패`가 찍힌다(2026-09-15 추가).
켰는데 점수가 예전 같다면 그 줄부터 찾는다. 응답의 `assessment_method`도 `"dgop"`인지 확인한다.

§6.5에서 만든 `backend/data/dgop_calibration.json`도 저장소에 함께 커밋한다(기본 경로라
환경변수 없이 읽힌다). 다른 경로에 둘 거면 `DGOP_CALIBRATION=<경로>`로 알려준다 — 없으면
축 A 실측 내장 앵커로 떨어진다.

---

## 8. 시간·비용 종합

### 시간

| 단계 | 예상 | 여유 포함 |
|---|---|---|
| 세팅 + A-0 | 45분 | 1시간 |
| A-1 Scorer | 35~90분 | 1.5시간 |
| A-2 Aligner | 10~25분 | 40분 |
| A-3 평가 | 20분 | 30분 |
| 회수·정리 | 10분 | 20분 |
| **합계** | **약 2~3시간** | **4시간** |

### 비용 (RunPod 공시가, 2026-09-08 확인)

| GPU | $/hr | 4시간 기준 |
|---|---|---|
| **H100 SXM (Secure)** | $2.99 | **$12.0** |
| H100 PCIe (Community) | $1.99 | $8.0 |
| H100 SXM (Community) | $2.69 | $10.8 |
| A100 80GB (Community) | $1.19 | $4.8 (단, 8~10시간 소요 → $10 내외) |

Network Volume 100GB × $0.07/GB/월 = **$7/월** (일할 아님 — 다 쓰면 지운다)

> **총 $15~20.** 실패해서 두 번 돌려도 $40을 넘기지 않는다.
> A100은 시간당 단가가 싸지만 2~3배 느려 **총액은 비슷하고 대기 시간만 늘어난다.** H100 권장.

### 데이터

| 항목 | 값 |
|---|---|
| `kresnik/zeroth_korean` parquet | **2.88 GB** (train 6샤드 2.81GB + test 0.06GB) |
| 학습 22,263발화 / 51.6시간, 평균 8.34초 | |
| 체크포인트 1개 | 3.8 GB (모델 1.27 + Adam 2.54) |

---

## 9. 중단·재개

Community Cloud는 호스트가 내려가면 Pod이 끊긴다. 체크포인트가 Network Volume에 있으면
그대로 이어붙인다:

```bash
# A-1 (스테이지는 경로에서 자동 판별 — stage1이 끝났으면 stage2만 이어 돈다)
python scripts/train_jamo_ctc.py --out /workspace/ckpt/scorer --bf16 --workers 16 \
  --stage1-epochs 0 \
  --resume /workspace/ckpt/scorer/stage2_full/checkpoint-<번호>

# A-2
python scripts/train_aligner.py --from /workspace/ckpt/scorer --out /workspace/ckpt/aligner \
  --bf16 --workers 16 --resume /workspace/ckpt/aligner/checkpoint-<번호>
```

`--stage1-epochs 0`으로 이미 끝난 스테이지를 건너뛸 수 있다.

## 10. 실패했을 때

| 증상 | 원인 | 대응 |
|---|---|---|
| loss가 `inf`/`nan` | CTC 길이 위반 | `prepare_zeroth_labels.py --check-duration`으로 확인, 필터 동작 점검 |
| stage2에서 loss 발산 | LR 과다 | `--stage2` LR을 3e-5 → 1e-5 |
| 단조성 미달 | 채점기가 저하 발화에 너무 강함 | A-1에 저하 데이터가 섞였는지 확인(섞이면 안 된다) |
| 정렬 견고성 미달 | A-2 부족 | `--epochs` 증가, severity 분포 조정 |
| epoch 시간이 추정의 3배↑ | 워커 0 또는 CUDA 미사용 | `--workers`, `check_ml_env.py` 재확인 |
