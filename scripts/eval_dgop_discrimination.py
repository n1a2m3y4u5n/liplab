#!/usr/bin/env python
"""
A-3 변별력 평가 — 축 A의 진짜 합격선.

축 A의 성패는 인식률(WER/CER)이 아니다. 발음 교정 앱이 필요로 하는 것은 **점수의 변별력**,
즉 '발음이 뭉갤수록 점수가 내려가는가'다. CER이 좋아져도 뭉갠 발화에 점수를 후하게 주면
그 모델은 이 앱에 쓸모가 없다.

정상 발화(Zeroth test)에 deaf_speech_synthesis로 severity 0~4를 걸고 세 가지를 잰다:

  1. 단조성   -ρ(severity, D-GOP)  ≥ 0.90   severity가 오를수록 점수가 내려가는가
  2. 분리도   AUC(severity 0 vs 3+) ≥ 0.85  정상과 심한 저하의 점수 분포가 갈리는가
  3. 정렬견고 severity 4의 aligned  ≥ 0.95  정렬기가 뭉갠 발화에서도 구간을 찾는가

표준 GOP(naive)와 나란히 출력한다 — D-GOP의 불확실성 보정이 실제로 과신을 막는지
같은 표본에서 직접 비교하기 위함이다.

  # 미세조정 전 베이스라인
  python scripts/eval_dgop_discrimination.py --limit 50

  # 축 A 산출물 (정렬기/채점기 분리)
  python scripts/eval_dgop_discrimination.py --aligner ./ckpt/aligner --scorer ./ckpt/scorer --limit 50
"""
import argparse
import os
import statistics
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import dgop as D                     # noqa: E402
import dgop_acoustic as DA           # noqa: E402
import deaf_speech_synthesis as DSS  # noqa: E402

DATASET = "kresnik/zeroth_korean"
SAMPLE_RATE = 16000
SEVERITIES = [0, 1, 2, 3, 4]

TARGET_MONOTONICITY = 0.90
TARGET_AUC = 0.85
TARGET_ALIGNED = 0.95


def spearman(xs, ys) -> float:
    """순위상관. 두 값이 모두 상수면 정의되지 않아 0.0을 돌려준다(scipy 의존 회피)."""
    def rank(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(order):           # 동점은 평균 순위
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r

    rx, ry = rank(xs), rank(ys)
    n = len(xs)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = (sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry)) ** 0.5
    return num / den if den else 0.0


def auc(pos, neg) -> float:
    """Mann-Whitney U 기반 AUC. pos(정상)가 neg(저하)보다 높은 점수를 받을 확률."""
    if not pos or not neg:
        return float("nan")
    wins = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return wins / (len(pos) * len(neg))


def score_one(wave, text, aligner_id, scorer_id):
    """한 파형의 D-GOP·naive 점수와 정렬 성공률."""
    tokens = DA.tokens_for_text(text, model_id=aligner_id)
    phones = DA.phone_confidences(wave, SAMPLE_RATE, tokens,
                                  aligner_id=aligner_id, scorer_id=scorer_id)
    scorable = [p for p in phones if p.get("scorable", True)]
    aligned = [p for p in scorable if p.get("aligned")]
    if not aligned:
        return None, None, 0.0
    dgop = D.sentence_dgop(aligned)["score"]
    naive = 100.0 * statistics.fmean(p["naive"] for p in aligned)
    return dgop, naive, len(aligned) / max(1, len(scorable))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--aligner", default=DA.DEFAULT_MODEL_ID)
    ap.add_argument("--scorer", default=None, help="생략 시 정렬기와 동일(단일 모델 동작)")
    ap.add_argument("--limit", type=int, default=50, help="평가할 발화 수")
    args = ap.parse_args()

    if not DA.HAS_ACOUSTIC or not DSS.HAS_SYNTHESIS:
        print("torch/torchaudio/librosa 미설치 — backend/requirements-ml.txt 설치 필요",
              file=sys.stderr)
        return 2

    import numpy as np
    import datasets as ds_lib
    from datasets import load_dataset

    ds = load_dataset(DATASET, split="test").cast_column(
        "audio", ds_lib.Audio(sampling_rate=SAMPLE_RATE))
    ds = ds.select(range(min(args.limit, len(ds))))

    rng = np.random.default_rng(0)
    # by_sev[severity] = 점수 목록, rhos = 발화별 단조성
    by_sev = {s: {"dgop": [], "naive": [], "aligned": []} for s in SEVERITIES}
    rhos_dgop, rhos_naive = [], []

    print(f"정렬기 {args.aligner}\n채점기 {args.scorer or args.aligner}\n발화 {len(ds)}건 × severity {SEVERITIES}\n")
    for i, row in enumerate(ds):
        clean = np.asarray(row["audio"]["array"], dtype=np.float32)
        text = row["text"]
        sevs, ds_scores, nv_scores = [], [], []
        for sev in SEVERITIES:
            wave = clean if sev == 0 else DSS.simulate_deaf_speech(clean, SAMPLE_RATE, sev, rng=rng)
            dg, nv, ar = score_one(wave, text, args.aligner, args.scorer)
            by_sev[sev]["aligned"].append(ar)
            if dg is None:
                continue
            by_sev[sev]["dgop"].append(dg)
            by_sev[sev]["naive"].append(nv)
            sevs.append(sev); ds_scores.append(dg); nv_scores.append(nv)
        if len(sevs) >= 3:   # 순위상관을 낼 만큼 점이 있어야 한다
            rhos_dgop.append(-spearman(sevs, ds_scores))
            rhos_naive.append(-spearman(sevs, nv_scores))
        if (i + 1) % 10 == 0:
            print(f"  … {i + 1}/{len(ds)}")

    print("\n severity | D-GOP 평균 | naive 평균 | 정렬 성공률")
    print(" ---------+------------+------------+-----------")
    for s in SEVERITIES:
        d, n, a = by_sev[s]["dgop"], by_sev[s]["naive"], by_sev[s]["aligned"]
        print(f"     {s}    |   {statistics.fmean(d) if d else float('nan'):6.2f}   |"
              f"   {statistics.fmean(n) if n else float('nan'):6.2f}   |   {statistics.fmean(a) if a else 0:.3f}")

    mono = statistics.fmean(rhos_dgop) if rhos_dgop else float("nan")
    mono_naive = statistics.fmean(rhos_naive) if rhos_naive else float("nan")
    sep = auc(by_sev[0]["dgop"], by_sev[3]["dgop"] + by_sev[4]["dgop"])
    sep_naive = auc(by_sev[0]["naive"], by_sev[3]["naive"] + by_sev[4]["naive"])
    align4 = statistics.fmean(by_sev[4]["aligned"]) if by_sev[4]["aligned"] else 0.0

    def verdict(v, target):
        return "PASS" if v == v and v >= target else "FAIL"

    print(f"\n{'지표':<26}{'D-GOP':>9}{'naive':>9}{'목표':>8}  판정")
    print(f"{'단조성 -ρ(sev, score)':<26}{mono:>9.3f}{mono_naive:>9.3f}{TARGET_MONOTONICITY:>8.2f}  {verdict(mono, TARGET_MONOTONICITY)}")
    print(f"{'분리도 AUC(0 vs 3+)':<26}{sep:>9.3f}{sep_naive:>9.3f}{TARGET_AUC:>8.2f}  {verdict(sep, TARGET_AUC)}")
    print(f"{'정렬 견고성(sev 4)':<26}{align4:>9.3f}{'-':>9}{TARGET_ALIGNED:>8.2f}  {verdict(align4, TARGET_ALIGNED)}")

    ok = all(v == v and v >= t for v, t in
             ((mono, TARGET_MONOTONICITY), (sep, TARGET_AUC), (align4, TARGET_ALIGNED)))
    print(f"\n종합: {'축 A 합격' if ok else '미달 — 위 판정 참고'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
