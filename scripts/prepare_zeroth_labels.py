#!/usr/bin/env python
"""
Zeroth-Korean 라벨 사전점검 — 축 A(A-1 Scorer) 학습 전 필수 관문.

RunPod H100은 시간당 과금이라, 라벨이 깨진 채로 학습을 시작하면 그대로 비용이 날아간다.
이 스크립트가 GPU를 켜기 전에 세 가지를 확인한다:

  1. OOV      — 모든 전사가 jamo_vocab의 49토큰 안에 들어오는가 (0건이어야 함)
  2. 비한글   — 구두점·숫자·로마자가 섞여 있는가 (있으면 정규화 규칙이 필요)
  3. 길이 타당성 — CTC는 출력 프레임 수 ≥ 라벨 길이여야 한다. 어기는 표본은 손실이
                  inf/nan이 되어 학습을 통째로 망가뜨리므로 미리 걸러낸다.

  # 텍스트만 검사(오디오 미다운로드 — 로컬에서 즉시 가능)
  python scripts/prepare_zeroth_labels.py --split train --limit 2000

  # 오디오까지 받아 길이 타당성 포함 전수 검사(GPU 서버에서)
  python scripts/prepare_zeroth_labels.py --split train --check-duration
"""
import argparse
import collections
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import jamo_vocab as V  # noqa: E402

DATASET = "kresnik/zeroth_korean"
# wav2vec2 CNN 특징추출기의 총 stride — 16kHz에서 320샘플(20ms)당 프레임 1개(=50fps).
_FRAME_STRIDE = 320


def frames_for(n_samples: int) -> int:
    """파형 길이(샘플) → CTC 출력 프레임 수(근사). 정확한 값은 모델의 conv 설정을 따른다."""
    return n_samples // _FRAME_STRIDE


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="train", choices=["train", "test"])
    ap.add_argument("--limit", type=int, default=0, help="검사할 표본 수(0=전체)")
    ap.add_argument("--check-duration", action="store_true",
                    help="오디오를 실제로 받아 CTC 길이 타당성까지 검사(느림)")
    ap.add_argument("--out", default="", help="자모 토큰열을 jsonl로 저장할 경로")
    args = ap.parse_args()

    from datasets import load_dataset

    # 길이 검사가 필요 없으면 오디오 디코딩을 건너뛰어 텍스트만 스트리밍한다.
    ds = load_dataset(DATASET, split=args.split, streaming=not args.check_duration)
    if args.check_duration:
        import datasets as _ds
        ds = ds.cast_column("audio", _ds.Audio(sampling_rate=16000))

    oov = collections.Counter()
    nonhangul = collections.Counter()
    too_long = []          # 라벨이 프레임 수보다 긴 표본
    tok_lens, n = [], 0
    writer = open(args.out, "w", encoding="utf-8") if args.out else None

    for row in ds:
        if args.limit and n >= args.limit:
            break
        text = row["text"]
        toks = V.text_to_tokens(text)
        tok_lens.append(len(toks))
        oov.update(t for t in toks if t not in V.VOCAB)
        nonhangul.update(ch for ch in text if not ("가" <= ch <= "힣") and ch != " ")

        if args.check_duration:
            n_frames = frames_for(len(row["audio"]["array"]))
            if n_frames < len(toks):
                too_long.append((row["id"], n_frames, len(toks)))

        if writer:
            import json
            writer.write(json.dumps({"id": row["id"], "text": text,
                                     "tokens": toks, "ids": V.tokens_to_ids(toks)},
                                    ensure_ascii=False) + "\n")
        n += 1

    if writer:
        writer.close()

    print(f"[{DATASET}:{args.split}] 표본 {n}건")
    print(f"  vocab            : {V.VOCAB_SIZE}토큰")
    print(f"  OOV              : {dict(oov) if oov else '0건 ✓'}")
    print(f"  비한글 문자      : {dict(nonhangul) if nonhangul else '없음 ✓'}")
    if tok_lens:
        srt = sorted(tok_lens)
        print(f"  라벨 길이        : 최소 {srt[0]} / 중앙 {srt[len(srt)//2]} / 최대 {srt[-1]}")
    if args.check_duration:
        print(f"  CTC 길이 위반    : {len(too_long)}건 "
              f"{'✓' if not too_long else '← 학습에서 제외 필요'}")
        for uid, f, l in too_long[:5]:
            print(f"      {uid}: 프레임 {f} < 라벨 {l}")
    else:
        print("  CTC 길이 위반    : 미검사 (--check-duration 으로 확인)")
    if args.out:
        print(f"  저장             : {args.out}")

    return 1 if (oov or too_long) else 0


if __name__ == "__main__":
    raise SystemExit(main())
