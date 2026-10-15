"""맞게 낸 토큰의 0점 꼬리 특성(탐색 자료 A0만, 맥, 모델 추론 없음). docs/phone-tail-2026-10.md 2절.

    python characterize.py LP_DIR JOBS OUT.json

A0 원래 목표의 끝 음절 밖·내지 않는 ㅎ 제외 토큰을 꼬리(표시 ≤ 1, naive < 0.015)와 나머지로 나눠, 구간 폭·빈칸 비율·위치·앞뒤 토큰·
지역 창(앞 토큰 끝 ~ 뒤 토큰 시작)의 채점기·정렬기 증거·클립 단위 채점기 확신·화자를 집계한다. 원자료 값은 쓰지 않고 집계만 낸다.
"""
import collections
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import offline as OF  # noqa: E402
import chipval as CV  # noqa: E402
import torch  # noqa: E402

DA, VOCAB = OF.DA, OF.VOCAB
B, WB = VOCAB["<pad>"], VOCAB["|"]
INV = {v: k for k, v in VOCAB.items()}


def rows_for(lp_dir, jobs):
    out = []
    for j in jobs:
        lp, slp = OF.load_lp(f"{lp_dir}/538_{j['clip']}.npz")
        ap, sp = CV.softmax(lp), CV.softmax(slp)
        toks = j["tokens"]
        spans = DA.align_targets(torch.from_numpy(lp), VOCAB, toks)
        T = lp.shape[0]
        s0, s1 = spans[0]["start"], spans[-1]["end"]
        seg = sp[s0:s1 + 1]
        nb = seg.argmax(1) != B
        clip_conf = float(seg[nb].max(1).mean()) if nb.any() else 0.0
        silent = set(j["silent_h"])
        for i, (tk, s) in enumerate(zip(toks, spans)):
            if not DA._is_scorable(tk) or i in silent or i >= j["fs"]:
                continue
            a, e = s["start"], s["end"]
            v = VOCAB[tk]
            mean = sp[a:e + 1].mean(0)
            lo, hi = CV.local_window(spans, i, T)
            W, WA = sp[lo:hi + 1], ap[lo:hi + 1]
            m = W.max(0).copy()
            excl = {B, WB, v, VOCAB.get(toks[i - 1], -1) if i else -1, VOCAB.get(toks[i + 1], -1) if i + 1 < len(toks) else -1}
            m[[x for x in excl if x >= 0]] = -1
            alt = int(m.argmax())
            out.append({"clip": j["clip"], "spk": j["spk"], "tok": tk, "prev": toks[i - 1] if i else "^",
                        "next": toks[i + 1] if i + 1 < len(toks) else "$", "naive": float(mean[v]), "width": e - a + 1,
                        "s_blank": float(mean[B]), "s_tmax": float(W[:, v].max()), "a_tmax": float(WA[:, v].max()),
                        "a_t": float(ap[a:e + 1, v].mean()), "alt": INV[alt], "alt_p": float(m[alt]), "clip_conf": clip_conf,
                        "rel": i / len(toks), "e1": float(sp[max(0, a - 1):min(T, e + 2), v].max()),
                        "bn": float(mean[v] / max(1e-9, 1 - mean[B]))})
    return out


def summarize(R):
    tail = [r for r in R if r["naive"] < 0.015]
    ok = [r for r in R if r["naive"] >= 0.5]
    rate = lambda rs: round(float(np.mean([r["naive"] < 0.015 for r in rs])), 4) if rs else None
    S = {"tokens": len(R), "tail": len(tail), "tail_rate": rate(R), "red_rate": round(float(np.mean([r["naive"] < 0.445 for r in R])), 4)}
    S["by_width"] = {w: {"n": len(rs), "tail": rate(rs)} for w in (1, 2, 3)
                     for rs in [[r for r in R if (r["width"] == w if w < 3 else r["width"] >= 3)]]}
    S["by_scorer_blank"] = {f"{lo}-{hi}": {"n": len(rs), "tail": rate(rs)} for lo, hi in ((0, .5), (.5, .9), (.9, .99), (.99, 1.01))
                            for rs in [[r for r in R if lo <= r["s_blank"] < hi]]}
    S["by_place"] = {p: rate([r for r in R if r["tok"].startswith(p)]) for p in ("o:", "n:", "c:")}
    S["by_relpos"] = [rate([r for r in R if q / 5 <= r["rel"] < (q + 1) / 5]) for q in range(5)]
    S["after_boundary"] = rate([r for r in R if r["prev"] == "|"])
    S["before_boundary"] = rate([r for r in R if r["next"] == "|"])
    ev = lambda f: (round(float(np.mean([f(r) for r in tail])), 4), round(float(np.mean([f(r) for r in ok])), 4))
    S["evidence_tail_vs_ok"] = {
        "scorer_target_gt0.5_in_window": ev(lambda r: r["s_tmax"] > .5),
        "scorer_target_gt0.5_pm1": ev(lambda r: r["e1"] > .5),
        "aligner_target_gt0.5_in_window": ev(lambda r: r["a_tmax"] > .5),
        "other_sound_gt0.5_in_window": ev(lambda r: r["alt_p"] > .5),
        "other_sound_and_no_target": ev(lambda r: r["alt_p"] > .5 and r["s_tmax"] <= .1),
        "nothing_heard": ev(lambda r: r["alt_p"] <= .5 and r["s_tmax"] <= .1),
        "blank_renorm_gt0.5": ev(lambda r: r["bn"] > .5),
    }
    S["aligner_target_prob_median_tail"] = round(float(np.median([r["a_t"] for r in tail])), 4)
    c = collections.Counter((r["tok"], r["alt"]) for r in tail if r["alt_p"] > .5 and r["s_tmax"] <= .1)
    S["heard_instead_top"] = [[a, b, n] for (a, b), n in c.most_common(20)]
    by_tok = collections.defaultdict(list)
    for r in R:
        by_tok[r["tok"]].append(r["naive"] < 0.015)
    S["tail_by_token_top"] = sorted([[t, len(v), round(float(np.mean(v)), 4)] for t, v in by_tok.items() if len(v) >= 100],
                                    key=lambda x: -x[2])[:15]
    clip = collections.defaultdict(list)
    for r in R:
        clip[r["clip"]].append((r["naive"] < 0.015, r["clip_conf"]))
    arr = np.array([(np.mean([a for a, _ in v]), v[0][1]) for v in clip.values()])
    from scipy.stats import spearmanr
    q1, q3 = np.quantile(arr[:, 1], [.25, .75])
    S["clip"] = {"n": len(arr), "tail_rate_pct": np.round(np.percentile(arr[:, 0], [10, 25, 50, 75, 90]), 4).tolist(),
                 "rho_tail_vs_scorer_conf": round(float(spearmanr(arr[:, 0], arr[:, 1])[0]), 3),
                 "tail_low_conf_q1": round(float(arr[arr[:, 1] < q1, 0].mean()), 4),
                 "tail_high_conf_q4": round(float(arr[arr[:, 1] >= q3, 0].mean()), 4)}
    spk = collections.defaultdict(list)
    for r in R:
        spk[r["spk"]].append(r["naive"] < 0.015)
    v = [np.mean(x) for x in spk.values()]
    S["speaker_tail_rate_pct"] = {"n": len(v), "q": np.round(np.percentile(v, [0, 10, 50, 90, 100]), 4).tolist()}
    return S


if __name__ == "__main__":
    lp_dir, jobs_path, out = sys.argv[1:4]
    jobs = [j for j in (json.loads(l) for l in open(jobs_path, encoding="utf-8")) if j["set"] == "A0"]
    S = summarize(rows_for(lp_dir, jobs))
    json.dump(S, open(out, "w"), ensure_ascii=False, indent=1)
    print(json.dumps(S, ensure_ascii=False)[:3000])
