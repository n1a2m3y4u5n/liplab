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


def degrading_transform(processor, seed: int = 0):
    """
    매 접근마다 무작위 severity를 골라 파형을 저하시킨 뒤 특징으로 바꾼다.

    HF의 lazy transform이라 **에폭마다 다른 교란**이 걸린다 — 고정 증강본을 미리 구워두는
    것보다 과적합이 덜하다. 저하는 반드시 특징 정규화 **이전의 원본 파형**에 걸어야 한다.
    """
    import numpy as np
    rng = np.random.default_rng(seed)

    def _tf(batch):
        values, labels = [], []
        for audio, text in zip(batch["audio"], batch["text"]):
            wave = hf_audio.to_waveform(audio)
            sev = int(rng.choice(SEVERITIES))
            if sev:
                try:
                    wave = DSS.simulate_deaf_speech(wave, SAMPLE_RATE, sev, rng=rng)
                except Exception:
                    pass  # 한 표본의 교란 실패가 배치를 멈추지 않게 한다
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
    args = ap.parse_args()

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
        train.set_transform(degrading_transform(processor, seed=0))
        eval_ds.set_transform(degrading_transform(processor, seed=1))

    print(f"[aligner] 시작점 {'(스모크: 베이스 체크포인트)' if args.smoke else args.src}")
    print(f"[aligner] severity {SEVERITIES} 무작위 적용 (0=원본 포함)")

    targs = TrainingArguments(
        output_dir=args.out,
        per_device_train_batch_size=args.batch,
        gradient_accumulation_steps=args.grad_accum,
        num_train_epochs=1 if args.smoke else args.epochs,
        learning_rate=args.lr,
        warmup_steps=0 if args.smoke else 300,
        lr_scheduler_type="linear",
        bf16=args.bf16,
        gradient_checkpointing=not args.smoke,
        eval_strategy="no" if args.smoke else "epoch",
        save_strategy="no" if args.smoke else "epoch",
        save_total_limit=2,
        # eval_loss가 중간 epoch에서 최적을 찍고 정체·반등하는 경우가 있다(A-1 실측:
        # stage2 epoch1 0.237 → 0.258 → 0.269 → 0.238). save_total_limit만으로는 마지막
        # 2개만 남아 최적점을 잃으므로, 최적 체크포인트를 명시적으로 보존·복원한다.
        load_best_model_at_end=not args.smoke,
        metric_for_best_model="eval_loss",
        greater_is_better=False,
        logging_steps=25,
        max_steps=1 if args.smoke else -1,
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
