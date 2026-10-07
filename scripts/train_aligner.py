#!/usr/bin/env python
"""
A-2 Aligner 학습 — 저하 발화 강인 정렬기 (축 A).

무엇을 만드는가. A-1이 만든 Scorer 체크포인트에서 이어받아, deaf_speech_synthesis의
조음 교란(severity 0~4)을 **매 스텝 무작위로** 걸어 학습한다. 결과물이 D-GOP의
**정렬기(Aligner)** 다 — forced_align이 뭉갠 발화에서도 음소 구간을 놓치지 않게 하는 것만이
목적이고, 채점은 여전히 A-1의 Scorer가 맡는다.

왜 Scorer를 그대로 쓰지 않는가. 뭉갠 발화에서 구간을 못 찾으면 채점 자체가 불가능하다.
반대로 채점기까지 저하 발화에 강인해지면 뭉개도 점수가 높아져 변별력이 사라진다.
두 요구가 정반대라 모델을 나눈다(docs/axis-a-training-plan.md §0·§1).

⚠️ severity 0(원본)을 반드시 섞는다. 저하 발화만 보면 정상 발화 정렬 능력을 잃는다.

  # 로컬 CPU 형상 검증 — 합성 파형 1 step, 데이터셋 미다운로드
  python scripts/train_aligner.py --smoke

  # RunPod H100 (A-1 산출물에서 이어받기)
  python scripts/train_aligner.py --from /workspace/ckpt/scorer --out /workspace/ckpt/aligner --bf16

  # 끝 무음 증강(docs/dgop-aligner-tailaug-2026-10.md): 발화 앞뒤에 무작위 길이 무음·약한 잡음을 덧붙인다.
  # 채점기 이어 학습은 --severities 0(저하 없음)으로 같은 스크립트를 쓴다.
  python scripts/train_aligner.py --from SCORER --out OUT --bf16 --pad-aug
  python scripts/train_aligner.py --from SCORER --out OUT --bf16 --pad-aug --severities 0 --epochs 2
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
sys.path.insert(0, os.path.dirname(__file__))

import hf_audio                     # noqa: E402
import jamo_vocab as V              # noqa: E402
import deaf_speech_synthesis as DSS  # noqa: E402
from train_jamo_ctc import DATASET, JamoCTCCollator, synthetic_dataset  # noqa: E402

SAMPLE_RATE = 16000
# severity 0(원본)을 다른 강도와 같은 비중으로 뽑아 정상 발화 정렬 능력을 유지한다.
SEVERITIES = [0, 1, 2, 3, 4]

# 끝 무음 증강(2026-10-07, docs/dgop-aligner-tailaug-2026-10.md). Zeroth train은 말소리 끝 뒤 무음이 중앙 14 ms라
# 정렬기·채점기가 문장 끝 토큰을 '입력의 끝'에 내도록 배웠다(docs/dgop-final-vowel-2026-10.md 7.2절). 앱 녹음은 정지 버튼으로
# 끝나 끝 무음이 길다. 학습 발화 앞뒤에 길이가 다른 무음·약한 잡음을 붙여 끝 출력이 입력 끝에 묶이지 않게 한다.
PAD_P_TAIL = 0.6            # 끝에 붙일 확률
PAD_TAIL_S = (0.1, 1.5)     # 끝 길이(초, 균등)
PAD_P_HEAD = 0.4            # 앞에 붙일 확률(앞뒤 독립)
PAD_HEAD_S = (0.05, 0.8)    # 앞 길이(초, 균등)
PAD_P_ZERO = 0.2            # 붙이는 소리가 디지털 무음일 확률(나머지는 가우스 잡음)
PAD_BELOW_DB = (35.0, 65.0)  # 잡음 RMS: 그 발화 10 ms 창 RMS 99백분위보다 이만큼 낮게(dB, 균등)


def pad_silence(wave, rng, sr: int = SAMPLE_RATE):
    """발화 앞뒤에 무작위 길이의 무음·약한 잡음을 붙인다(PAD_* 상수). 말소리 자체는 바꾸지 않는다."""
    import numpy as np
    y = np.asarray(wave, dtype=np.float32).reshape(-1)
    n = int(sr * 0.01)
    m = len(y) // n
    if m >= 1:
        r = np.sqrt(np.mean(y[:m * n].astype(np.float64).reshape(m, n) ** 2, axis=1) + 1e-12)
        ref_db = float(np.percentile(20.0 * np.log10(r), 99))
    else:
        ref_db = -20.0

    def seg(lo, hi):
        k = int(round(sr * rng.uniform(lo, hi)))
        if rng.random() < PAD_P_ZERO:
            return np.zeros(k, np.float32)
        rms = 10.0 ** ((ref_db - rng.uniform(*PAD_BELOW_DB)) / 20.0)
        return (rng.standard_normal(k) * rms).astype(np.float32)

    head = seg(*PAD_HEAD_S) if rng.random() < PAD_P_HEAD else np.zeros(0, np.float32)
    tail = seg(*PAD_TAIL_S) if rng.random() < PAD_P_TAIL else np.zeros(0, np.float32)
    return np.concatenate([head, y, tail])


def _proc_rng(seed: int, store: dict):
    """데이터로더 워커마다 다른 난수열(워커는 같은 상태를 복사해 받으므로 pid로 가른다)."""
    import numpy as np
    pid = os.getpid()
    if pid not in store:
        store[pid] = np.random.default_rng([seed, pid])
    return store[pid]


def degrading_transform(processor, seed: int = 0, severities=None, pad_aug: bool = False):
    """
    매 접근마다 무작위 severity를 골라 파형을 저하시킨 뒤 특징으로 바꾼다.

    HF의 lazy transform이라 **에폭마다 다른 교란**이 걸린다 — 고정 증강본을 미리 구워두는
    것보다 과적합이 덜하다. 저하는 반드시 특징 정규화 **이전의 원본 파형**에 걸어야 한다.
    """
    import numpy as np
    sevs = list(SEVERITIES if severities is None else severities)
    base_rng = np.random.default_rng(seed)
    store = {}

    def _tf(batch):
        # pad_aug를 켜면 워커마다 다른 난수열을 쓴다(끄면 예전과 같은 동작).
        rng = _proc_rng(seed, store) if pad_aug else base_rng
        values, labels = [], []
        for audio, text in zip(batch["audio"], batch["text"]):
            wave = hf_audio.to_waveform(audio)
            sev = int(rng.choice(sevs))
            if sev:
                try:
                    wave = DSS.simulate_deaf_speech(wave, SAMPLE_RATE, sev, rng=rng)
                except Exception:
                    pass  # 한 표본의 교란 실패가 배치를 멈추지 않게 한다
            if pad_aug:
                wave = pad_silence(wave, rng)   # 저하 뒤에 붙인다(붙인 잡음은 저하하지 않는다)
            values.append(processor(wave, sampling_rate=SAMPLE_RATE).input_values[0])
            labels.append(V.text_to_ids(text))
        return {"input_values": values, "labels": labels}

    return _tf


def _smoke_check_augment(processor) -> None:
    """
    스모크에서 증강 경로를 실제로 태운다. 학습 루프만 돌리면 degrading_transform이
    한 번도 실행되지 않아, 정작 A-2의 핵심인 저하 적용이 검증되지 않는다.
    """
    import numpy as np
    rng = np.random.default_rng(0)
    wave = 0.05 * rng.standard_normal(SAMPLE_RATE).astype("float32")  # 1초
    batch = {"audio": [{"array": wave, "sampling_rate": SAMPLE_RATE}] * 4,
             "text": ["국물 먹었다"] * 4}
    out = degrading_transform(processor, seed=0)(batch)
    assert len(out["input_values"]) == 4 and len(out["labels"]) == 4, "배치 형상 불일치"
    assert out["labels"][0] == V.text_to_ids("국물 먹었다"), "라벨이 자모 id열이어야 함"

    # 저하가 실제로 신호를 바꾸는지 — severity 0과 4의 대역폭 차이로 확인
    clean = DSS.simulate_deaf_speech(wave, SAMPLE_RATE, 0, rng=rng)
    heavy = DSS.simulate_deaf_speech(wave, SAMPLE_RATE, 4, rng=rng)
    hf_ratio = lambda y: float(np.abs(np.fft.rfft(y))[len(y) // 4:].sum() / (np.abs(np.fft.rfft(y)).sum() + 1e-9))
    assert hf_ratio(heavy) < hf_ratio(clean), "severity 4는 고역이 더 깎여야 함"
    print(f"[augment] 검증 OK — 고역 비중 severity0 {hf_ratio(clean):.3f} → severity4 {hf_ratio(heavy):.3f}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="src", default="./ckpt/scorer",
                    help="A-1 Scorer 체크포인트 경로")
    ap.add_argument("--out", default="./ckpt/aligner")
    ap.add_argument("--smoke", action="store_true", help="CPU에서 1 step만 — 형상 검증")
    ap.add_argument("--epochs", type=float, default=4)
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--grad-accum", type=int, default=2)
    ap.add_argument("--lr", type=float, default=2e-5)
    ap.add_argument("--bf16", action="store_true")
    ap.add_argument("--workers", type=int, default=min(8, os.cpu_count() or 4),
                    help="데이터로더 워커 수. 증강(librosa)이 CPU를 쓰므로 A-2에서 특히 중요하다")
    ap.add_argument("--resume", default=None, help="중단된 체크포인트 경로")
    ap.add_argument("--pad-aug", action="store_true", help="발화 앞뒤 무음·약한 잡음 덧붙이기(PAD_* 상수)")
    ap.add_argument("--severities", default=",".join(map(str, SEVERITIES)),
                    help="저하 강도 후보(쉼표). 채점기 이어 학습은 0")
    ap.add_argument("--warmup", type=int, default=300)
    ap.add_argument("--max-steps", type=int, default=-1, help="배관 점검용(양수면 그 스텝만)")
    args = ap.parse_args()
    sevs = [int(x) for x in args.severities.split(",") if x.strip()]

    import datasets as ds_lib
    from datasets import load_dataset
    from transformers import Trainer, TrainingArguments, Wav2Vec2ForCTC, Wav2Vec2Processor

    if not DSS.HAS_SYNTHESIS:
        print("librosa/scipy 미설치 — backend/requirements-ml.txt 설치 필요", file=sys.stderr)
        return 2

    if args.smoke:
        # A-1 산출물 없이도 배관을 검증할 수 있게 베이스 체크포인트로 대체한다.
        from train_jamo_ctc import build_model, build_processor
        processor = build_processor(args.out)
        model = build_model(processor)
        _smoke_check_augment(processor)
        train = eval_ds = synthetic_dataset(processor)
    else:
        processor = Wav2Vec2Processor.from_pretrained(args.src)
        model = Wav2Vec2ForCTC.from_pretrained(args.src)
        model.freeze_feature_encoder()
        train = load_dataset(DATASET, split="train").cast_column(
            "audio", ds_lib.Audio(sampling_rate=SAMPLE_RATE))
        eval_ds = load_dataset(DATASET, split="test").cast_column(
            "audio", ds_lib.Audio(sampling_rate=SAMPLE_RATE))
        train.set_transform(degrading_transform(processor, seed=0, severities=sevs, pad_aug=args.pad_aug))
        eval_ds.set_transform(degrading_transform(processor, seed=1, severities=sevs, pad_aug=args.pad_aug))

    print(f"[aligner] 시작점 {'(스모크: 베이스 체크포인트)' if args.smoke else args.src}")
    print(f"[aligner] severity {sevs} 무작위 적용 (0=원본 포함), 끝 무음 증강 {'켬' if args.pad_aug else '끔'}")

    targs = TrainingArguments(
        output_dir=args.out,
        per_device_train_batch_size=args.batch,
        gradient_accumulation_steps=args.grad_accum,
        num_train_epochs=1 if args.smoke else args.epochs,
        learning_rate=args.lr,
        warmup_steps=0 if args.smoke else args.warmup,
        lr_scheduler_type="linear",
        bf16=args.bf16,
        gradient_checkpointing=not args.smoke,
        eval_strategy="no" if args.smoke or args.max_steps > 0 else "epoch",
        save_strategy="no" if args.smoke or args.max_steps > 0 else "epoch",
        save_total_limit=2,
        # set_transform으로 input_values·labels를 지연 생성하므로, Trainer가 선언된 원본
        # 컬럼(audio·text 등)을 미리 지우면 변환할 것이 남지 않는다. 제거를 끈다.
        remove_unused_columns=False,
        # eval_loss가 중간 epoch에서 최적을 찍고 정체·반등하는 경우가 있다(A-1 실측:
        # stage2 epoch1 0.237 → 0.258 → 0.269 → 0.238). save_total_limit만으로는 마지막
        # 2개만 남아 최적점을 잃으므로, 최적 체크포인트를 명시적으로 보존·복원한다.
        load_best_model_at_end=not args.smoke and args.max_steps <= 0,
        metric_for_best_model="eval_loss",
        greater_is_better=False,
        logging_steps=25,
        max_steps=1 if args.smoke else args.max_steps,
        # severity 증강이 발화당 ~20ms(단일 코어 기준 7.6분/epoch)라 워커 없이는 GPU가 논다.
        dataloader_num_workers=0 if args.smoke else args.workers,
        report_to=[],
    )
    Trainer(model=model, args=targs, train_dataset=train, eval_dataset=eval_ds,
            data_collator=JamoCTCCollator(processor=processor)).train(
                resume_from_checkpoint=args.resume)

    model.save_pretrained(args.out)
    processor.save_pretrained(args.out)
    print(f"\n저장 완료: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
