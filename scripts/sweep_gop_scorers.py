#!/usr/bin/env python
"""
채점식 일괄 비교 — GPU 없이, 결정론적으로, 몇 초 만에.

`scripts/dump_gop_features.py`가 뜬 구간 통계(npz)를 읽어 `gop_variants.SCORERS`의 모든
채점식을 같은 표본 위에서 비교한다. 순전파가 없으므로 채점식을 추가할 때마다 GPU를 다시
빌릴 필요가 없다.

두 모드가 있고 npz의 meta_mode로 자동 판별한다.

  severity 모드 — A-3과 같은 판정: severity와 점수의 단조성(-ρ), 정상 vs 중증 AUC.
                  **발화 단위로 먼저 접은 뒤** 집계한다 — 구간 단위 pooling은 같은 발화의
                  구간 수십 개를 독립 표본으로 세어 신뢰구간을 심하게 과소추정한다
                  (기존 eval_dgop_discrimination의 AUC가 그렇다).

  perturb 모드  — 과신 측정: 정답 목표열 vs 오염 목표열의 점수 분리도(AUC)와, 오염 조건에서
                  naive가 얼마나 남는지. **오디오가 동일하고 목표열만 다르므로**, 오염 조건에서
                  점수가 높게 남으면 그것이 곧 과신이다.

부트스트랩 신뢰구간을 함께 낸다 — A-5까지의 판정에는 검정이 붙어 있지 않아 "naive 0.914 >
D-GOP 0.813"이 우연인지 알 수 없었다. 여기서는 **발화 단위 부트스트랩**으로 짝지어 비교한다.

  python scripts/sweep_gop_scorers.py --features data_out/gop_severity.npz
"""
import argparse
import os
import statistics
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "backend"))
sys.path.insert(0, _HERE)

import gop_variants as G              # noqa: E402
import eval_dgop_discrimination as E  # noqa: E402




def load_features(path):
    import numpy as np
    d = np.load(path, allow_pickle=True)
    return d


def span_view(d, i):
    """i번째 구간을 gop_variants가 먹는 형태로 꺼낸다. 해당 집계가 없으면 빠진다."""
    import numpy as np
    span = {"target_id": int(d["target_id"][i])}
    for key in ("mean_prob", "mean_logprob", "mean_logit"):
        arr = d.get(key)
        if arr is None:
            continue
        v = arr[i]
        if np.isnan(v).any():
            continue
        span[key] = v
    return span


def empirical_prior(d):
    """목표 토큰 빈도에서 prior를 추정한다(prior_maxlogit·dnn_gop용)."""
    import numpy as np
    C = d["mean_prob"].shape[1]
    counts = np.bincount(d["target_id"].astype(int), minlength=C).astype("float64")
    counts += 1.0                      # 라플라스 — 미관측 토큰이 0이 되지 않게
    return counts / counts.sum()


def utterance_scores(d, name, prior):
    """
    (utt, cond) → 그 발화·조건의 평균 점수. 구간을 발화 단위로 먼저 접는다.
    반환: {(utt, cond): mean_score}
    """
    import numpy as np
    bucket = {}
    n = len(d["target_id"])
    for i in range(n):
        span = span_view(d, i)
        v = G.score_span(name, span, prior=prior)
        if v is None or not np.isfinite(v):
            continue
        key = (int(d["utt"][i]), str(d["cond"][i]))
        bucket.setdefault(key, []).append(float(v))
    return {k: statistics.fmean(v) for k, v in bucket.items() if v}


def eval_severity(scores):
    """발화별 단조성 평균과 정상 vs 중증 AUC."""
    by_utt = {}
    for (utt, cond), v in scores.items():
        if not cond.startswith("sev"):
            continue
        by_utt.setdefault(utt, {})[int(cond[3:])] = v
    rhos = []
    clean, severe = [], []
    for utt, m in by_utt.items():
        sevs = sorted(m)
        if len(sevs) >= 3:
            rhos.append(-E.spearman(sevs, [m[s] for s in sevs]))
        if 0 in m:
            clean.append(m[0])
        severe += [m[s] for s in (3, 4) if s in m]
    return {
        "mono": statistics.fmean(rhos) if rhos else float("nan"),
        "auc": E.auc(clean, severe) if clean and severe else float("nan"),
        "n_utt": len(by_utt),
        "rhos": rhos,
    }


def eval_perturb(scores):
    """정답 목표열 vs 오염 목표열의 분리도. 규칙별로 낸다."""
    by_cond = {}
    for (utt, cond), v in scores.items():
        by_cond.setdefault(cond, {})[utt] = v
    clean = by_cond.get("clean", {})
    out = {}
    for cond, m in by_cond.items():
        if cond == "clean":
            continue
        common = sorted(set(clean) & set(m))
        if not common:
            continue
        out[cond] = {
            "auc": E.auc([clean[u] for u in common], [m[u] for u in common]),
            "clean_mean": statistics.fmean([clean[u] for u in common]),
            "pert_mean": statistics.fmean([m[u] for u in common]),
            "n": len(common),
        }
    return out


def paired_bootstrap(rhos_a, rhos_b, n=10000, seed=0):
    """
    발화 단위 대응표본 부트스트랩 — 두 채점식의 단조성 차이에 신뢰구간을 붙인다.
    반환: (평균차, ci_low, ci_high, p_two_sided)
    """
    import random
    if not rhos_a or len(rhos_a) != len(rhos_b):
        return (float("nan"),) * 3 + (float("nan"),)
    rnd = random.Random(seed)
    m = len(rhos_a)
    diffs = []
    for _ in range(n):
        idx = [rnd.randrange(m) for _ in range(m)]
        diffs.append(statistics.fmean([rhos_a[i] - rhos_b[i] for i in idx]))
    diffs.sort()
    obs = statistics.fmean([a - b for a, b in zip(rhos_a, rhos_b)])
    lo, hi = diffs[int(0.025 * n)], diffs[int(0.975 * n) - 1]
    # 부호가 0을 건너는 비율로 양측 p 근사
    p = 2 * min(sum(1 for x in diffs if x <= 0), sum(1 for x in diffs if x >= 0)) / n
    return obs, lo, hi, min(1.0, p)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--features", required=True, help="dump_gop_features.py가 만든 npz")
    ap.add_argument("--baseline", default="naive", help="비교 기준 채점식")
    ap.add_argument("--bootstrap", type=int, default=10000)
    args = ap.parse_args()

    d = load_features(args.features)
    mode = str(d["meta_mode"])
    prior = empirical_prior(d)
    print(f"특징 {args.features}\n모드 {mode} | 구간 {len(d['target_id']):,}개 "
          f"| 발화 {len(set(d['utt'].tolist()))}건\n")

    # 불변 검사 — 구간에 blank가 섞이면 집계 해석이 달라진다(정상이면 항상 0건).
    bad = int((d["nb_frames"] != d["frames"]).sum())
    if bad:
        print(f"[WARN] 구간 {bad}개에 blank 프레임이 섞여 있습니다 — 정렬 방식이 바뀌었는지 "
              f"확인하세요(Cao et al. 2024의 blank 제외 논점이 그때부터 유효해집니다).\n")

    results = {}
    for name in G.SCORERS:
        scores = utterance_scores(d, name, prior)
        if scores:
            results[name] = (eval_severity(scores) if mode == "severity"
                             else eval_perturb(scores))

    if mode == "severity":
        base_key = args.baseline
        base = results.get(base_key)
        print(f" {'채점식':<26}{'단조성':>8}{'AUC':>8}   vs {args.baseline} (95% CI)")
        print(" " + "-" * 74)
        for key in sorted(results, key=lambda k: -results[k]["mono"]):
            r = results[key]
            cmp = ""
            if base and key != base_key and len(r["rhos"]) == len(base["rhos"]):
                obs, lo, hi, p = paired_bootstrap(r["rhos"], base["rhos"], args.bootstrap)
                sig = "유의" if (lo > 0 or hi < 0) else "  -"
                cmp = f"   {obs:+.3f} [{lo:+.3f}, {hi:+.3f}] p={p:.3f} {sig}"
            print(f" {key:<26}{r['mono']:>8.3f}{r['auc']:>8.3f}{cmp}")
        print("\n 단조성·AUC 모두 클수록 좋다. CI가 0을 포함하지 않으면 기준 대비 유의한 차이다.")
    else:
        print(f" {'채점식':<26}{'규칙':<24}{'AUC':>7}{'정답평균':>10}{'오염평균':>10}")
        print(" " + "-" * 78)
        for key in sorted(results):
            for rule, r in sorted(results[key].items()):
                print(f" {key:<26}{rule:<24}{r['auc']:>7.3f}"
                      f"{r['clean_mean']:>10.3f}{r['pert_mean']:>10.3f}")
        print("\n AUC가 1에 가까울수록 오염을 잘 잡아낸다. **오염평균이 정답평균에 가까이 남으면**")
        print(" 그것이 과신이다 — 음향은 그대로인데 틀린 목표에도 높은 점수를 준다는 뜻이다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
