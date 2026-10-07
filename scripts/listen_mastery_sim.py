"""소음 속 듣기 2차: 4단계 숙달 판정·훈련 목표 조합·검사 앞 연습 문장 비교(docs/listen-mastery-sim-2026-10.md).

1차 스크립트(listen_adaptive_sim.py)의 가상 청취자·응답·격자를 그대로 쓴다. 순수 numpy.

사용:
  python scripts/listen_mastery_sim.py --calibrate --seed 0          # (b)의 σ_D 표 보정(탐색 시드, C1, 향상 없음)
  python scripts/listen_mastery_sim.py --seed 0 --out docs/listen-mastery-sim-explore-seed0.json
  python scripts/listen_mastery_sim.py --seed 1 --rules a,c20_p2_z23_g3 --combos d80:c20_p2_z23_g3 --practice p0,p3 --out ...
"""
import argparse
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import listen_adaptive_sim as S  # noqa: E402

L = S.L
T = 100                                   # 소리만 시행 수
W = L.NOISE_MASTER["window"]
GAIN = L.NOISE_MASTER["gain_db"]
GROUPS = S.GROUPS
COND_ALL = ["C0", "C1", "C2", "C3", "C4", "C5"]

# (b)의 σ_D 표: 지금 추정량(srt_estimate)으로 낸 두 20시행 창(1~20, 41~60) 차이의 SD, 최근 창 역치 구간(< 3, 3~10, ≥ 10 dB)별.
# 탐색 시드 0, C1, 향상 없음, 2,000명에서 --calibrate로 구해 고정했다(문서 7.1).
SIG_D_EDGES = (3.0, 10.0)
SIG_D = (1.253, 1.507, 1.914)


def sig_d(rec):
    i = np.digitize(rec, SIG_D_EDGES)
    return np.asarray(SIG_D, float)[i]


# ── 계단(훈련) ───────────────────────────────────────────────────────


def track(rng, lis, cond, drop_db, placement):
    """소리만 T시행. placement: ("stair",) 지금 1-up-1-down 또는 ("bk", tar). (xs, ks, nw) 각 (N, T)."""
    N = len(lis["srt"])
    t = np.arange(1, T + 1)
    srt_t = lis["srt"][:, None] - (np.clip((t - 20) / 20.0, 0, 1) * drop_db)[None, :]
    nsent = len(S.TRAIN_WORDS)
    offs = rng.normal(0.0, cond["sd_item"], (N, nsent)) if cond["sd_item"] > 0 else np.zeros((N, nsent))
    order = np.concatenate([np.argsort(rng.random((N, nsent)), axis=1) for _ in range(-(-T // nsent))], 1)[:, :T]
    nw = S.TRAIN_WORDS[order]
    off = np.take_along_axis(offs, order, 1)
    xs, ks = np.zeros((N, T)), np.zeros((N, T))
    x = np.full(N, S.START)
    last, nrev = np.zeros(N), np.zeros(N)
    bk = S.BK(N, placement[1], 0.10, 0.5, False) if placement[0] == "bk" else None
    for j in range(T):
        k = S.respond(rng, x, srt_t[:, j], lis["slope"], off[:, j], cond["sd_trial"], nw[:, j])
        xs[:, j], ks[:, j] = x, k
        if bk is None:
            ok = k / nw[:, j] >= L.STAIR["criterion"]
            d = np.where(ok, -1.0, 1.0)
            nrev += (last != 0) & (d != last)
            last = d
            step = np.where(nrev < L.STAIR["big_reversals"], L.STAIR["big"], L.STAIR["small"])
            x = np.clip(x + d * step, L.STAIR["lo"], L.STAIR["hi"])
        else:
            x = bk.step(x, k / nw[:, j])
    return xs, ks, nw


def check_stair_matches_app(xs, ks, nw, n=30):
    for i in range(n):
        trials = []
        for j in range(T):
            nxt = L.stair_state(trials)["next_db"]
            assert abs(nxt - xs[i, j]) < 1e-9, (i, j, nxt, xs[i, j])
            trials.append((float(xs[i, j]), bool(ks[i, j] / nw[i, j] >= 0.5)))


def cur_window_est(xs, ks, nw, w):
    """지금 추정량(srt_estimate)으로 낸 w시행 창 역치. est[:, j] = 시행 j..j+w-1."""
    N = xs.shape[0]
    ok = ks / nw >= L.STAIR["criterion"]
    est = np.zeros((N, T - w + 1))
    for i in range(N):
        tr = list(zip(xs[i].tolist(), ok[i].tolist()))
        for j in range(T - w + 1):
            est[i, j] = L.srt_estimate(tr[j:j + w])
    return est


_LP_SLOPE = -0.5 * ((np.log(S.SLg) - np.log(0.10)) / 0.4) ** 2      # 역치 편평, 기울기 로그정규


def ml_window_stats(xs, ks, nw, ws=(20, 30), batch=100, q=None):
    """낱말 비율 격자 적합: 창마다 역치 주변 사후 평균과 SD. {w: (mu, sd)} 각 (N, T-w+1).
    q: 격자점마다의 대상 값(G,). 기본은 50% 역치, 목표 정답률 지점(SRT_tar)을 주면 그 사후 평균·SD."""
    q = S.THg if q is None else q
    N = xs.shape[0]
    out = {w: (np.zeros((N, T - w + 1)), np.zeros((N, T - w + 1))) for w in ws}
    for b0 in range(0, N, batch):
        sl = slice(b0, min(N, b0 + batch))
        ll = np.stack([S.loglik(xs[sl, j], ks[sl, j], nw[sl, j]) for j in range(T)], 1)
        cs = np.concatenate([np.zeros((ll.shape[0], 1, S.G)), np.cumsum(ll, 1)], 1)
        for w in ws:
            mu, sd = out[w]
            for j in range(T - w + 1):
                lp = cs[:, j + w] - cs[:, j] + _LP_SLOPE
                lp -= lp.max(1, keepdims=True)
                p = np.exp(lp)
                p /= p.sum(1, keepdims=True)
                m = p @ q
                mu[sl, j] = m
                sd[sl, j] = np.sqrt(np.maximum(p @ (q ** 2) - m ** 2, 1e-12))
    return out


# ── 판정 규칙 ────────────────────────────────────────────────────────


def first_hit(hits):
    """hits: {n: (N,) bool} → 처음 숙달한 시행 수(없으면 inf)."""
    N = len(next(iter(hits.values())))
    at = np.full(N, np.inf)
    for n in sorted(hits):
        at = np.where(np.isinf(at) & hits[n], n, at)
    return at


def rule_a(est20, min_trials=W):
    hits = {}
    for n in range(min_trials, T + 1):
        rec = est20[:, n - W]
        h = rec <= L.NOISE_MASTER["srt_db"]
        if n >= 2 * W:
            h |= (est20[:, 0] - rec) >= GAIN
        hits[n] = h
    return first_hit(hits)


def rule_w(est_w, w):
    hits = {}
    for n in range(w, T + 1):
        rec = est_w[:, n - w]
        h = rec <= L.NOISE_MASTER["srt_db"]
        if n >= 2 * w:
            h |= (est_w[:, 0] - rec) >= GAIN
        hits[n] = h
    return first_hit(hits)


def rule_b(est20, z):
    hits = {}
    for n in range(W, T + 1):
        rec = est20[:, n - W]
        sg = sig_d(rec)
        h = rec + z * sg / np.sqrt(2) <= L.NOISE_MASTER["srt_db"]
        if n >= 2 * W:
            h |= (est20[:, 0] - rec) >= np.maximum(GAIN, z * sg)
        hits[n] = h
    return first_hit(hits)


def rule_c(ml, w, phi, z, g, crit=0.0):
    mu, sd = ml[w]
    sd = sd * np.sqrt(phi)
    hits = {}
    for n in range(w, T + 1):
        rec, srec = mu[:, n - w], sd[:, n - w]
        h = rec + z * srec <= crit
        if n >= 2 * w:
            dlt = mu[:, 0] - rec
            h |= (dlt - z * np.sqrt(sd[:, 0] ** 2 + srec ** 2) > 0) & (dlt >= g)
        hits[n] = h
    return first_hit(hits)


def rule_e(ml, w, phi, z, g, every, consec, crit=0.0):
    """사후 등록 뒤 탐색(문서 7.2): (c)와 같은 판정을 every시행마다만 보고(회차 끝 판정), consec번 잇달아 만족해야 숙달."""
    mu, sd = ml[w]
    sd = sd * np.sqrt(phi)
    raw = {}
    for n in range(w, T + 1):
        if n % every:
            continue
        rec, srec = mu[:, n - w], sd[:, n - w]
        h = rec + z * srec <= crit
        if n >= 2 * w:
            dlt = mu[:, 0] - rec
            h |= (dlt - z * np.sqrt(sd[:, 0] ** 2 + srec ** 2) > 0) & (dlt >= g)
        raw[n] = h
    hits = {}
    ns = sorted(raw)
    for i, n in enumerate(ns):
        h = raw[n].copy()
        for k in range(1, consec):
            h &= raw[ns[i - k]] if i - k >= 0 else False
        hits[n] = h
    return first_hit(hits)


E_RULES = {}
for _w in (20, 30):
    for _phi in (1, 2):
        for _z in (1.645, 2.326):
            for _g in (2, 3):
                for _c in (1, 2):
                    E_RULES[f"e{_w}_p{_phi}_z{int(_z * 10)}_g{_g}_k10_c{_c}"] = (_w, _phi, _z, _g, 10, _c)

C_RULES = {}
for _w in (20, 30):
    for _phi in (1, 2):
        for _z in (1.645, 2.326):
            for _g in (2, 3):
                C_RULES[f"c{_w}_p{_phi}_z{int(_z * 10)}_g{_g}"] = (_w, _phi, _z, _g)
C_RULES["ref_point"] = (20, 1, 0.0, 3)          # 점추정 3 dB(1차 확인 후보의 판정과 같은 꼴)
B_RULES = {"b_z16": 1.645, "b_z23": 2.326, "b_z31": 3.09}
STAIR_RULES = ["a", "d40", "dw30"] + list(B_RULES) + list(C_RULES)
ALL_RULES = STAIR_RULES + list(E_RULES)


def apply_rule(name, est20, est30, ml):
    if name == "a":
        return rule_a(est20)
    if name == "d40":
        return rule_a(est20, min_trials=40)
    if name == "dw30":
        return rule_w(est30, 30)
    if name in B_RULES:
        return rule_b(est20, B_RULES[name])
    if name in E_RULES:
        return rule_e(ml, *E_RULES[name])
    return rule_c(ml, *C_RULES[name])


def summarize(lis, at, props_null=None):
    srt, g = lis["srt"], lis["group"]
    out = {}
    for key, sc, mask in (("fm", "null", srt >= 2.0), ("r3", "imp3", srt >= 5.0), ("r5", "imp5", srt >= 7.0),
                          ("nh", "null", srt <= -1.0)):
        a = at[sc][mask]
        reached = np.isfinite(a)
        rate = float(reached.mean())
        out[key] = rate
        out[key + "_se"] = float(np.sqrt(rate * (1 - rate) / mask.sum()))
        out[key + "_n"] = int(mask.sum())
        out[key + "_median_trials"] = float(np.median(a[reached])) if reached.any() else None
        out[key + "_groups"] = {gn: (float(np.isfinite(at[sc][mask & (g == gi)]).mean()) if (mask & (g == gi)).any() else None)
                                for gi, gn in enumerate(GROUPS)}
    if props_null is not None:
        wp = props_null[:, 10:].mean(1)
        out["word_prop"] = float(wp.mean())
        out["word_prop_groups"] = {gn: float(wp[g == gi].mean()) for gi, gn in enumerate(GROUPS)}
    return out


SCEN = {"null": 0.0, "imp3": 3.0, "imp5": 5.0}


def run_training(seed, n_lis, conds, rules, combos):
    res = {}
    for cn in conds:
        ci = list(S.CONDITIONS).index(cn)
        cond = S.CONDITIONS[cn]
        rng = np.random.default_rng([seed, ci, 31])
        lis = S.make_listeners(rng, n_lis)
        if "slope_fixed" in cond:
            lis["slope"] = np.full(n_lis, cond["slope_fixed"])
        res[cn] = {"rules": {}, "combos": {}}
        t0 = time.time()
        if rules:
            at = {r: {} for r in rules}
            for si, (sc, drop) in enumerate(SCEN.items()):
                xs, ks, nw = track(np.random.default_rng([seed, ci, 32, si]), lis, cond, drop, ("stair",))
                if cn == COND_ALL[0] and si == 0:
                    check_stair_matches_app(xs, ks, nw)
                need_cur = any(r in ("a", "d40", "dw30") or r in B_RULES for r in rules)
                est20 = cur_window_est(xs, ks, nw, 20) if need_cur else None
                est30 = cur_window_est(xs, ks, nw, 30) if "dw30" in rules else None
                ml = ml_window_stats(xs, ks, nw) if any(r in C_RULES or r in E_RULES for r in rules) else None
                for r in rules:
                    at[r][sc] = apply_rule(r, est20, est30, ml)
                if sc == "null":
                    props0 = ks / nw
            for r in rules:
                res[cn]["rules"][r] = summarize(lis, at[r], props0)
        by_place = {}
        for cb in combos:
            pl, rn = cb.split(":")
            by_place.setdefault(pl, []).append(rn)
        for pl, rns in by_place.items():
            tar = int(pl[1:]) / 100.0
            at = {r: {} for r in rns}
            for si, (sc, drop) in enumerate(SCEN.items()):
                xs, ks, nw = track(np.random.default_rng([seed, ci, 33, int(tar * 100), si]), lis, cond, drop, ("bk", tar))
                ml = ml_window_stats(xs, ks, nw) if any(r in C_RULES or r in E_RULES for r in rns) else None
                # 사후 등록 뒤 추가(문서 7.3): 목표 지점 역치 SRT_tar를 직접 추정하고 0 dB 기준을 logit(tar)/(4·0.10) dB로 환산
                q_tar = S.THg + np.log(tar / (1 - tar)) / (4 * S.SLg)
                mlq = ml_window_stats(xs, ks, nw, q=q_tar) if any(r.startswith("q") for r in rns) else None
                crit_q = float(np.log(tar / (1 - tar)) / (4 * 0.10))
                for r in rns:
                    if r.startswith("qe"):
                        at[r][sc] = rule_e(mlq, *E_RULES[r[1:]], crit=crit_q)
                    elif r.startswith("q"):
                        at[r][sc] = rule_c(mlq, *C_RULES["c" + r[1:]], crit=crit_q)
                    elif r in E_RULES:
                        at[r][sc] = rule_e(ml, *E_RULES[r])
                    else:
                        at[r][sc] = rule_c(ml, *C_RULES[r])
                if sc == "null":
                    props0 = ks / nw
            for r in rns:
                res[cn]["combos"][f"{pl}:{r}"] = summarize(lis, at[r], props0)
        print(f"  훈련 {cn}: {time.time() - t0:.1f}s", flush=True)
    return res


def calibrate(seed, n_lis):
    cond = S.CONDITIONS["C1"]
    rng = np.random.default_rng([seed, 1, 31])
    lis = S.make_listeners(rng, n_lis)
    xs, ks, nw = track(np.random.default_rng([seed, 1, 39]), lis, cond, 0.0, ("stair",))
    est = cur_window_est(xs, ks, nw, 20)
    d = est[:, 0] - est[:, 40]
    rec = est[:, 40]
    bins = np.digitize(rec, SIG_D_EDGES)
    out = [float(np.std(d[bins == b], ddof=1)) for b in range(3)]
    print("σ_D(구간 < 3, 3~10, ≥ 10 dB):", [round(v, 3) for v in out], "n:", [int((bins == b).sum()) for b in range(3)],
          "평균 D:", round(float(d.mean()), 3))
    return out


# ── 검사 앞 연습 문장 ────────────────────────────────────────────────

PRACTICE = {"p0": (0, 4), "p3": (3, 4), "p5": (5, 4), "p3s": (3, 0), "p5s": (5, 0)}


def run_test_practice(rng, lis, cond, k_prac, big_trials):
    N = len(lis["srt"])
    nsent = len(S.TRAIN_WORDS)
    x = np.full(N, S.START)
    if k_prac:
        pick = np.argsort(rng.random((N, nsent)), axis=1)[:, :k_prac]
        nwp = S.TRAIN_WORDS[pick]
        offp = rng.normal(0.0, cond["sd_item"], (N, k_prac)) if cond["sd_item"] > 0 else np.zeros((N, k_prac))
        for j in range(k_prac):
            k = S.respond(rng, x, lis["srt"], lis["slope"], offp[:, j], cond["sd_trial"], nwp[:, j])
            x = np.clip(x + np.where(k / nwp[:, j] >= 0.5, -L.TEST_STAIR["big"], L.TEST_STAIR["big"]), S.LO, S.HI)
    words = S.TEST_WORDS
    offs = rng.normal(0.0, cond["sd_item"], (N, 20)) if cond["sd_item"] > 0 else np.zeros((N, 20))
    xs, props, nxt = np.zeros((N, 20)), np.zeros((N, 20)), np.zeros((N, 20))
    for t in range(20):
        k = S.respond(rng, x, lis["srt"], lis["slope"], offs[:, t], cond["sd_trial"], np.full(N, int(words[t])))
        xs[:, t], props[:, t] = x, k / words[t]
        x = S.a_next(x, props[:, t] >= 0.5, t, big_trials)
        nxt[:, t] = x
    est = S.mean_est(xs, nxt, 20)
    blocked = ((xs >= S.HI - 1e-9) & (props < 0.5)).any(1)
    return est, blocked


def check_practice_matches_app(seed=0, n=200):
    """p5s 시뮬레이션의 걸음 규칙이 앱 함수(test_next_snr·test_srt, n_practice)와 같은지 무작위 응답으로 확인한다."""
    rng = np.random.default_rng([seed, 77])
    kp = L.TEST_STAIR["practice"]
    for _ in range(n):
        oks = rng.random(kp + 20) < 0.5
        x, xs, trials = S.START, [], []
        for j in range(kp + 20):
            assert abs((L.test_next_snr(trials, n_practice=min(kp, len(trials))) if trials else S.START) - x) < 1e-9
            trials.append((x, bool(oks[j])))
            xs.append(x)
            step = L.TEST_STAIR["big"] if j < kp else L.TEST_STAIR["small"]
            x = float(np.clip(x + (-step if oks[j] else step), S.LO, S.HI))
        test = np.array(xs[kp:])
        est = (test[4:20].sum() + x) / 17
        assert abs(L.test_srt(trials, n_practice=kp) - est) < 0.051


def run_practice(seed, n_lis, conds, variants):
    check_practice_matches_app()
    res = {}
    for cn in conds:
        ci = list(S.CONDITIONS).index(cn)
        cond = S.CONDITIONS[cn]
        rng = np.random.default_rng([seed, ci, 41])
        lis = S.make_listeners(rng, n_lis)
        if "slope_fixed" in cond:
            lis["slope"] = np.full(n_lis, cond["slope_fixed"])
        res[cn] = {}
        for vn in variants:
            kp, bt = PRACTICE[vn]
            vr = np.random.default_rng([seed, ci, 42, list(PRACTICE).index(vn)])
            e1, b1 = run_test_practice(vr, lis, cond, kp, bt)
            e2, b2 = run_test_practice(vr, lis, cond, kp, bt)
            res[cn][vn] = S.summarize_test(lis, e1, e2, np.concatenate([b1, b2]))
    return res


# ── 출력 ─────────────────────────────────────────────────────────────


def print_tables(res):
    for part in ("rules", "combos"):
        if "training" not in res:
            break
        print(f"\n[{part}] 조건 규칙: FM% | R3%(중앙 시행) | R5% | NH%(중앙 시행) | 낱말비율")
        for cn, r in res["training"].items():
            for name, m in r[part].items():
                print(f"  {cn} {name:22s} {100 * m['fm']:5.1f} | {100 * m['r3']:5.1f}({m['r3_median_trials']}) | "
                      f"{100 * m['r5']:5.1f} | {100 * m['nh']:5.1f}({m['nh_median_trials']}) | {m.get('word_prop', 0):.2f}")
    if "practice" in res:
        print("\n[연습 문장] 조건 변형: 편향 | 재검사SD | MDC95 | 막힘% | 집단 편향")
        for cn, r in res["practice"].items():
            for vn, m in r.items():
                gb = "/".join(f"{m['groups'][g]['bias']:+.2f}" for g in GROUPS)
                print(f"  {cn} {vn:4s} {m['bias']:+.2f} | {m['retest_sd']:.3f} | {m['mdc95']:.2f} | {100 * m['blocked']:.2f} | {gb}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--n", type=int, default=2000)
    ap.add_argument("--calibrate", action="store_true")
    ap.add_argument("--conds", default=",".join(COND_ALL))
    ap.add_argument("--rules", default=",".join(STAIR_RULES))
    ap.add_argument("--combos", default=",".join(f"{p}:{r}" for p in ("d75", "d80") for r in C_RULES) + "," +
                    ",".join(f"{p}:q{r[1:]}" for p in ("d75", "d80") for r in C_RULES if r.startswith("c")))
    ap.add_argument("--practice", default=",".join(PRACTICE))
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    if a.calibrate:
        calibrate(a.seed, a.n)
        return
    assert None not in SIG_D or not any(r in B_RULES for r in a.rules.split(",")), "먼저 --calibrate로 SIG_D를 정한다"
    conds = a.conds.split(",")
    res = {"seed": a.seed, "n": a.n, "T": T, "sig_d": SIG_D}
    t0 = time.time()
    if a.practice:
        res["practice"] = run_practice(a.seed, a.n, conds, [v for v in a.practice.split(",") if v])
    if a.rules or a.combos:
        res["training"] = run_training(a.seed, a.n, conds, [v for v in a.rules.split(",") if v],
                                       [v for v in a.combos.split(",") if v])
    res["elapsed_s"] = round(time.time() - t0, 1)
    print_tables(res)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=1)
        print("저장:", a.out)


if __name__ == "__main__":
    main()
