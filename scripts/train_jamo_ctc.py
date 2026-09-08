#!/usr/bin/env python
"""
A-1 Scorer 학습 — 자모 CTC 헤드 미세조정 (축 A).

무엇을 만드는가. kresnik/wav2vec2-large-xlsr-korean의 encoder는 그대로 두고 lm_head만
jamo_vocab의 49토큰으로 갈아끼워 Zeroth-Korean(정상 발화)으로 학습한다. 결과물이
D-GOP의 **채점기(Scorer)** 다.

왜 정상 발화만 쓰는가. dgop.py의 점수는 naive × confidence이고, 뭉갠 발화에서 분포가
평평해져 confidence가 떨어지는 것 자체가 '발음이 부정확하다'는 신호다. 저하 발화로 이
모델까지 강인하게 만들면 뭉개도 점수가 높아져 변별력이 사라진다. 저하 발화 강인성은
정렬기(Aligner, A-2)가 따로 맡는다. 자세한 근거는 docs/axis-a-training-plan.md §0.

2스테이지로 나누는 이유. 랜덤 초기화된 새 lm_head가 처음부터 full backprop을 타면
사전학습된 encoder를 망가뜨린다. 먼저 head만 데운 뒤 낮은 LR로 전체를 푼다.
CNN feature extractor는 전 구간 freeze(wav2vec2 미세조정 표준).

  # 로컬 CPU 형상 검증 — 합성 파형으로 1 step만, 데이터셋 미다운로드 (GPU 켜기 전 필수)
  python scripts/train_jamo_ctc.py --smoke

  # RunPod H100
  python scripts/train_jamo_ctc.py --out /workspace/ckpt/scorer --bf16
"""
import argparse
import os
import sys
from dataclasses import dataclass
from typing import Dict, List, Union

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import hf_audio  # noqa: E402
import jamo_vocab as V  # noqa: E402

BASE_MODEL = "kresnik/wav2vec2-large-xlsr-korean"
DATASET = "kresnik/zeroth_korean"


@dataclass
class JamoCTCCollator:
    """가변 길이 파형·라벨을 배치로 묶는다. 라벨 패딩은 -100(손실에서 무시)."""
    processor: object

    def __call__(self, features: List[Dict]) -> Dict:
        import torch
        batch = self.processor.pad(
            [{"input_values": f["input_values"]} for f in features],
            padding=True, return_tensors="pt",
        )
        labels = self.processor.pad(
            labels=[{"input_ids": f["labels"]} for f in features],
            padding=True, return_tensors="pt",
        )
        batch["labels"] = labels["input_ids"].masked_fill(
            labels.attention_mask.ne(1), -100
        )
        return batch


def build_processor(vocab_dir: str):
    """jamo_vocab을 HF Wav2Vec2Processor로 감싼다. vocab.json은 학습 산출물과 함께 보관한다."""
    from transformers import (Wav2Vec2CTCTokenizer, Wav2Vec2FeatureExtractor,
                              Wav2Vec2Processor)
    os.makedirs(vocab_dir, exist_ok=True)
    vocab_path = V.save_vocab_json(os.path.join(vocab_dir, "vocab.json"))
    tokenizer = Wav2Vec2CTCTokenizer(
        vocab_path, unk_token=V.UNK, pad_token=V.PAD, word_delimiter_token=V.WORD_DELIM,
    )
    fe = Wav2Vec2FeatureExtractor(
        feature_size=1, sampling_rate=16000, padding_value=0.0,
        do_normalize=True, return_attention_mask=True,
    )
    return Wav2Vec2Processor(feature_extractor=fe, tokenizer=tokenizer)


def build_model(processor):
    from transformers import Wav2Vec2ForCTC
    model = Wav2Vec2ForCTC.from_pretrained(
        BASE_MODEL,
        vocab_size=V.VOCAB_SIZE,
        ctc_loss_reduction="mean",
        pad_token_id=processor.tokenizer.pad_token_id,
        # 기존 체크포인트의 lm_head는 음절 1,205토큰이라 형상이 다르다 — 의도된 교체다.
        ignore_mismatched_sizes=True,
        attention_dropout=0.05, hidden_dropout=0.05, feat_proj_dropout=0.05,
        mask_time_prob=0.05, layerdrop=0.05,
    )
    model.freeze_feature_encoder()  # CNN 특징추출기는 전 구간 동결(표준)
    return model


def synthetic_dataset(processor, n: int = 4):
    """
    스모크용 합성 데이터셋. 실제 Zeroth를 받지 않고(수 GB) 형상·배관만 검증한다 —
    dgop 테스트가 합성 log_probs를 쓰는 것과 같은 원칙이다.
    파형 길이는 라벨보다 프레임이 넉넉하도록 잡는다(CTC 길이 제약).
    """
    import numpy as np
    from datasets import Dataset

    texts = ["국물 먹었다", "학교 갔다", "안녕하세요", "밥 먹자"][:n]
    rows = []
    for i, text in enumerate(texts):
        labels = V.text_to_ids(text)
        n_samples = (len(labels) + 50) * 320          # 프레임 > 라벨 보장
        rng = np.random.default_rng(i)
        wave = 0.05 * rng.standard_normal(n_samples).astype("float32")
        rows.append({
            "input_values": processor(wave, sampling_rate=16000).input_values[0],
            "labels": labels,
        })
    return Dataset.from_list(rows)


def prepare_dataset(processor, split: str, limit: int = 0):
    """오디오 → input_values, 전사 → 자모 id열. CTC 길이 위반 표본은 여기서 걸러낸다."""
    import datasets as ds_lib
    from datasets import load_dataset

    ds = load_dataset(DATASET, split=split)
    if limit:
        ds = ds.select(range(min(limit, len(ds))))
    ds = ds.cast_column("audio", ds_lib.Audio(sampling_rate=16000))

    def _map(batch):
        # datasets 5.x는 AudioDecoder를, 그 이전은 dict를 준다 — hf_audio가 둘 다 흡수한다.
        wave = hf_audio.to_waveform(batch["audio"])
        batch["input_values"] = processor(wave, sampling_rate=16000).input_values[0]
        batch["labels"] = V.text_to_ids(batch["text"])
        batch["n_frames"] = len(wave) // 320  # wav2vec2 총 stride
        return batch

    ds = ds.map(_map, remove_columns=ds.column_names, num_proc=os.cpu_count())
    # CTC는 출력 프레임 수 ≥ 라벨 길이여야 한다. 어기면 손실이 inf가 되어 학습이 망가진다.
    before = len(ds)
    ds = ds.filter(lambda x: x["n_frames"] >= len(x["labels"]))
    if len(ds) != before:
        print(f"[filter] CTC 길이 위반 {before - len(ds)}건 제외 ({before} → {len(ds)})")
    return ds.remove_columns(["n_frames"])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="./ckpt/scorer")
    ap.add_argument("--smoke", action="store_true",
                    help="CPU에서 1 step만 — 형상·배관 검증용(실제 학습 아님)")
    ap.add_argument("--stage1-epochs", type=float, default=3, help="head만 학습")
    ap.add_argument("--stage2-epochs", type=float, default=12, help="전체 unfreeze")
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--grad-accum", type=int, default=2)
    ap.add_argument("--bf16", action="store_true")
    ap.add_argument("--workers", type=int, default=min(8, os.cpu_count() or 4),
                    help="데이터로더 워커 수. 0이면 메인 프로세스에서 직렬 처리돼 GPU가 논다")
    ap.add_argument("--resume", default=None,
                    help="중단된 체크포인트 경로. Community Cloud처럼 Pod이 끊길 수 있는 환경에서 필요")
    args = ap.parse_args()

    from transformers import Trainer, TrainingArguments

    processor = build_processor(args.out)
    print(f"[vocab] {V.VOCAB_SIZE}토큰 → {args.out}/vocab.json")

    model = build_model(processor)
    collator = JamoCTCCollator(processor=processor)

    if args.smoke:
        train = eval_ds = synthetic_dataset(processor)
    else:
        train = prepare_dataset(processor, "train")
        eval_ds = prepare_dataset(processor, "test")

    def run(tag: str, epochs: float, lr: float, freeze_encoder: bool, resume=None):
        model.wav2vec2.requires_grad_(not freeze_encoder)
        model.freeze_feature_encoder()  # 어느 단계에서든 CNN은 계속 동결
        trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
        print(f"\n=== {tag} | epochs={epochs} lr={lr} 학습 파라미터 {trainable/1e6:.1f}M ===")
        targs = TrainingArguments(
            output_dir=os.path.join(args.out, tag),
            per_device_train_batch_size=args.batch,
            gradient_accumulation_steps=args.grad_accum,
            num_train_epochs=epochs,
            learning_rate=lr,
            # transformers 5.x는 warmup_ratio·group_by_length를 뺐다 — 절대 스텝으로 지정한다.
            warmup_steps=0 if args.smoke else 500,
            lr_scheduler_type="linear",
            bf16=args.bf16,
            gradient_checkpointing=not args.smoke,
            eval_strategy="epoch" if not args.smoke else "no",
            save_strategy="epoch" if not args.smoke else "no",
            save_total_limit=2,
            logging_steps=25,
            max_steps=1 if args.smoke else -1,
            # 기본값 0이면 전처리가 메인 프로세스에서 직렬로 돌아 GPU를 놀린다.
            dataloader_num_workers=0 if args.smoke else args.workers,
            report_to=[],
        )
        Trainer(model=model, args=targs, train_dataset=train,
                eval_dataset=eval_ds, data_collator=collator).train(
                    resume_from_checkpoint=resume)

    # 1단계: 랜덤 head를 먼저 데운다(encoder 보호). 2단계: 낮은 LR로 전체 미세조정.
    # --resume는 중단 지점이 어느 스테이지인지에 따라 하나에만 걸린다.
    resume_stage = None
    if args.resume:
        resume_stage = "stage1_head" if "stage1" in args.resume else "stage2_full"
    if args.stage1_epochs:
        run("stage1_head", args.stage1_epochs if not args.smoke else 1, 1e-3, True,
            resume=args.resume if resume_stage == "stage1_head" else None)
    if args.stage2_epochs:
        run("stage2_full", args.stage2_epochs if not args.smoke else 1, 3e-5, False,
            resume=args.resume if resume_stage == "stage2_full" else None)

    model.save_pretrained(args.out)
    processor.save_pretrained(args.out)
    print(f"\n저장 완료: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
