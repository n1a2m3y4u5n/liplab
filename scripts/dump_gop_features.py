#!/usr/bin/env python
"""
GOP 특징 덤프 — 축 B 재설계 실험의 **유일한 GPU 단계**.

지금까지 채점식을 하나 바꿀 때마다 모델을 다시 돌렸다. 그래서 비교가 비싸고 느리고
비결정론적이었다. 여기서는 구간별 집계 통계를 **한 번만** 뜬 뒤 npz로 저장하고, 이후
채점식 비교는 전부 순수 함수 replay로 처리한다(`scripts/sweep_gop_scorers.py`).
GPU 12분 한 번에 채점식 수십 개를 무한히 비교할 수 있게 된다.

두 실험을 한 번의 순전파로 함께 덤프한다:

  E1 채점식 스윕 (--mode severity)
     발화 × severity 0~4에 대해 구간 통계를 뜬다. 기존 A-3과 같은 표본·시드.

  E2 과신 측정 (--mode perturb)
     **깨끗한 발화만** 쓰고, 목표 자모열을 규칙으로 오염시킨다(jamo_perturb).
     오디오는 손대지 않는다 — 과신은 '음향은 q인데 P(p)를 높게 준다'는 현상이라
     목표만 틀리게 하면 저하 발화 합성 없이 그 조건이 만들어진다.

── 무엇을 저장하는가 ─────────────────────────────────────────────────────
구간마다 세 가지 집계를 저장한다:

  mean_prob      평균 확률분포        naive·dgop·dnn_gop용
  mean_logprob   평균 로그확률        gmm_gop·nn_gop용
  mean_logit     평균 raw 로짓        maxlogit·prior_maxlogit·logit_margin용

로짓을 보관하는 이유는 dgop_acoustic.ctc_outputs 참고(Yeo et al. 2023).
blank 프레임은 구간에 애초에 포함되지 않는다(span_aggregates의 불변 검사 참고).

  python scripts/dump_gop_features.py --smoke
  python scripts/dump_gop_features.py --mode severity \\
      --aligner /workspace/ckpt/aligner --scorer /workspace/ckpt/scorer \\
      --limit 50 --out /workspace/feat/severity.npz
"""
import argparse
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "backend"))
sys.path.insert(0, _HERE)

import dgop_acoustic as DA           # noqa: E402
import deaf_speech_synthesis as DSS  # noqa: E402
import hf_audio                      # noqa: E402
import jamo_perturb as JP            # noqa: E402
import jamo_vocab as JV              # noqa: E402
import eval_dgop_discrimination as E  # noqa: E402

SEVERITIES = E.SEVERITIES
SAMPLE_RATE = E.SAMPLE_RATE


def span_aggregates(log_probs, logits, start, end, blank_id):
    """
    구간 [start, end]의 집계 통계를 전체/비blank 두 방식으로 계산한다.
    비blank 프레임이 하나도 없으면 그쪽은 None(스윕에서 그 변형만 빠진다).
    """
    import torch

    lp = log_probs[start:end + 1]
    lg = logits[start:end + 1]
    probs = torch.softmax(lp, dim=-1)

    out = {
        "mean_prob": probs.mean(dim=0),
        "mean_logprob": lp.mean(dim=0),
        "mean_logit": lg.mean(dim=0),
    }
    # 불변 검사: 구간 안에 blank 프레임이 있으면 안 된다.
    # ctc_align.token_spans는 '같은 비blank 라벨이 이어지는 run'만 구간으로 잡으므로
    # blank는 구간 **사이**에만 존재한다(실측 확인). 따라서 Cao et al. 2024가 지적한
    # 'blank 프레임이 집계를 오염시키는' 문제는 이 구현에 해당하지 않는다.
    # 정렬 방식이 바뀌어 blank가 섞이기 시작하면 nb_frames != frames로 드러난다.
    out["nb_frames"] = int((lp.argmax(dim=-1) != blank_id).sum())
    out["frames"] = int(lp.shape[0])
    return out


def collect(rows, aligner_id, scorer_id, mode, rules, rate, seed, verbose=True):
    """
    발화 목록 → 구간별 집계 레코드. GPU를 쓰는 유일한 부분.
    반환: (records, meta) — records는 dict의 리스트.
    """
    import numpy as np
    import random as _random
    import torch

    rng = np.random.default_rng(seed)
    prng = _random.Random(seed)
    records = []
    conditions = SEVERITIES if mode == "severity" else ([None] + list(rules))

    unusable = 0
    for i, row in enumerate(rows):
        clean = hf_audio.to_waveform(row["audio"])
        text = row["text"]
        base_tokens = DA.tokens_for_text(text, model_id=aligner_id)

        # perturb 모드는 자모 vocab 전용이다. 음절 vocab(공개 체크포인트)으로 돌리면
        # 오염 규칙이 하나도 걸리지 않아 clean 조건만 쌓이고, 그걸 12분 뒤에야 알게 된다.
        if mode == "perturb" and i == 0:
            if not any(t[:2] in ("o:", "n:", "c:") for t in base_tokens):
                raise ValueError(
                    "perturb 모드는 자모 vocab 체크포인트가 필요합니다 — 지금 정렬기의 "
                    f"토큰은 자모가 아닙니다(예: {base_tokens[:5]}). "
                    "--aligner/--scorer에 축 A 산출물(/workspace/ckpt/*)을 지정하세요.")

        for cond in conditions:
            if mode == "severity":
                wave = clean if cond == 0 else DSS.simulate_deaf_speech(
                    clean, SAMPLE_RATE, cond, rng=rng)
                tokens = base_tokens
                cond_name, sev = f"sev{cond}", cond
            else:
                wave = clean                       # ← 오디오는 건드리지 않는다
                if cond is None:
                    tokens, cond_name = base_tokens, "clean"
                else:
                    rep = JP.perturbation_report(base_tokens, cond, rate=rate, rng=prng)
                    if not rep["usable"]:
                        unusable += 1              # 아무것도 안 바뀌면 비교가 성립 안 함
                        continue
                    tokens, cond_name = rep["perturbed"], cond
                sev = None

            try:
                a_lp, _a_lg, vocab = DA.ctc_outputs(wave, SAMPLE_RATE, aligner_id)
                spans = DA.align_targets(a_lp, vocab, tokens)
                if scorer_id == aligner_id:
                    s_lp, s_lg, s_vocab = a_lp, _a_lg, vocab
                else:
                    s_lp, s_lg, s_vocab = DA.ctc_outputs(wave, SAMPLE_RATE, scorer_id)
                    if s_lp.shape[0] != a_lp.shape[0]:
                        raise ValueError("정렬기·채점기 프레임 수 불일치")
            except Exception as e:
                if verbose:
                    print(f"  [skip] utt {i} / {cond_name}: {e}")
                continue

            blank_id = s_vocab.get(JV.PAD, 0)
            for sp in spans:
                tok = sp["token"]
                if not JV.is_scorable(tok) or tok not in s_vocab:
                    continue
                agg = span_aggregates(s_lp, s_lg, sp["start"], sp["end"], blank_id)
                rec = {"utt": i, "cond": cond_name, "severity": sev,
                       "target_id": s_vocab[tok], "token": tok,
                       "frames": agg["frames"], "nb_frames": agg["nb_frames"]}
                for k, v in agg.items():
                    if torch.is_tensor(v):
                        rec[k] = v.numpy().astype("float32")
                records.append(rec)

        if verbose and (i + 1) % 10 == 0:
            print(f"  … {i + 1}/{len(rows)}  (구간 {len(records):,}개)")

    if mode == "perturb" and unusable and verbose:
        print(f"  ({unusable}개 조건이 '오염되지 않음'으로 제외됐다 — 해당 문장에 그 규칙이 "
              f"걸릴 자모가 없다는 뜻)")
    meta = {"mode": mode, "aligner": aligner_id, "scorer": scorer_id,
            "utterances": len(rows), "seed": seed,
            "conditions": [str(c) for c in conditions], "rate": rate}
    return records, meta


def save_npz(records, meta, path):
    """레코드 리스트 → npz. 벡터 키는 (N, C) 배열로 쌓는다."""
    import numpy as np

    if not records:
        raise ValueError("저장할 구간이 없습니다")
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    out = {}
    vec_keys = [k for k in records[0] if isinstance(records[0][k], np.ndarray)]
    for k in vec_keys:
        # 일부 레코드에 비blank 집계가 없을 수 있다 — 없으면 NaN 행으로 채운다.
        C = records[0][k].shape[0]
        arr = np.full((len(records), C), np.nan, dtype="float32")
        for i, r in enumerate(records):
            if k in r:
                arr[i] = r[k]
        out[k] = arr
    for k in ("utt", "target_id", "frames", "nb_frames"):
        out[k] = np.array([r[k] for r in records], dtype="int32")
    out["severity"] = np.array([-1 if r["severity"] is None else r["severity"]
                                for r in records], dtype="int32")
    out["cond"] = np.array([r["cond"] for r in records])
    out["token"] = np.array([r["token"] for r in records])
    for k, v in meta.items():
        out[f"meta_{k}"] = np.array(v if not isinstance(v, list) else v)
    np.savez_compressed(path, **out)
    return path


def _smoke_rows(n=4, seconds=5.0):
    """
    데이터셋 없이 배관만 확인하기 위한 합성 발화.

    ⚠️ 길이가 중요하다. 짧게 만들면 프레임 수가 목표 토큰 수와 비슷해져 **구간이 전부
    1프레임**이 되고, 그러면 비blank 집계가 전체 집계와 자명하게 같아져 blank 제외 경로가
    검증되지 않는다. Zeroth 실제 비율(평균 8.34초 / 라벨 중앙값 103토큰 ≈ 토큰당 4프레임)에
    맞춰 넉넉히 잡는다.
    """
    import numpy as np
    rng = np.random.default_rng(0)
    length = int(SAMPLE_RATE * seconds)
    return [{"audio": rng.standard_normal(length).astype("float32") * 0.05,
             "text": "학교에서 국물을 먹었습니다"} for _ in range(n)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["severity", "perturb"], default="severity")
    ap.add_argument("--aligner", default=DA.DEFAULT_MODEL_ID)
    ap.add_argument("--scorer", default=None, help="생략 시 정렬기와 동일")
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--rules", default=",".join(JP.RULES),
                    help="perturb 모드에서 적용할 오염 규칙(쉼표 구분)")
    ap.add_argument("--rate", type=float, default=1.0, help="오염 적용 비율")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default=None)
    ap.add_argument("--smoke", action="store_true",
                    help="합성 발화로 배관만 검증(모델은 필요, 데이터셋은 불필요)")
    args = ap.parse_args()

    if not DA.HAS_ACOUSTIC or not DSS.HAS_SYNTHESIS:
        print("torch/transformers/librosa 미설치 — backend/requirements-ml.txt 설치 필요",
              file=sys.stderr)
        return 2

    scorer = args.scorer or args.aligner
    rules = [r for r in args.rules.split(",") if r]
    unknown = [r for r in rules if r not in JP.RULES]
    if unknown:
        print(f"알 수 없는 오염 규칙: {unknown} (가능: {sorted(JP.RULES)})", file=sys.stderr)
        return 2

    if args.smoke:
        rows = _smoke_rows()
    else:
        import datasets as ds_lib
        from datasets import load_dataset
        ds = load_dataset(E.DATASET, split="test").cast_column(
            "audio", ds_lib.Audio(sampling_rate=SAMPLE_RATE))
        rows = ds.select(range(min(args.limit, len(ds))))

    print(f"모드 {args.mode} | 정렬기 {args.aligner} | 채점기 {scorer}")
    print(f"발화 {len(rows)}건" + (f" | 오염 규칙 {rules} (rate {args.rate})"
                                   if args.mode == "perturb" else
                                   f" | severity {SEVERITIES}") + "\n")

    try:
        records, meta = collect(rows, args.aligner, scorer, args.mode,
                                rules, args.rate, args.seed)
    except ValueError as e:
        print(f"\n{e}", file=sys.stderr)
        return 2
    if not records:
        print("수집된 구간이 없습니다 — 정렬이 전부 실패했는지 확인하세요", file=sys.stderr)
        return 1

    out = args.out or os.path.join(_HERE, "..", "data_out", f"gop_{args.mode}.npz")
    save_npz(records, meta, out)
    conds = {}
    for r in records:
        conds[r["cond"]] = conds.get(r["cond"], 0) + 1
    print(f"\n구간 {len(records):,}개 저장 → {out}")
    print("  조건별:", ", ".join(f"{k} {v:,}" for k, v in sorted(conds.items())))
    print(f"\n다음: python scripts/sweep_gop_scorers.py --features {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
