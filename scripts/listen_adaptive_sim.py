"""소음 속 듣기(소리 듣기 4단계) 적응 절차 비교: 가상 청취자 시뮬레이션(docs/listen-adaptive-sim-2026-10.md).

가상 청취자는 낱말마다 로지스틱 정신측정 함수(50% 지점 기울기 s)를 따르고, 문장의 낱말은 서로 독립인 베르누이 시행이다.
문장 난이도 오프셋(SD 0·1·2 dB)과 제시마다 문장 낱말에 함께 걸리는 흔들림(낱말 사이 상관) 조건을 둔다. 어절 수는 앱의
TEST_FORMS·TRAIN_SENTENCES 그대로다.

검사 절차: (a) 지금 1-up-1-down(listen_curriculum.test_next_snr·test_srt), (b) 낱말 비율 걸음(Brand·Kollmeier 2002류),
(c) 베이지안 psi(역치·기울기 격자, 낱말 수 이항 가능도, 기대 엔트로피 최소). 훈련 절차: (a) 지금 stair_state·noise_mastered,
(d) 목표 정답률(70~80%) 비율 걸음과 50% 역치 추정량.

순수 numpy. 맥에서 시드 하나·조건 넷 전체가 몇 분 걸린다.

사용:
  python scripts/listen_adaptive_sim.py --seed 0 --out docs/listen-adaptive-sim-explore-seed0.json
  python scripts/listen_adaptive_sim.py --seed 1 --test a,c_marg --train a,d75_f05_bayes --out docs/listen-adaptive-sim-confirm-seed1.json
"""
import argparse
import json
import os
import sys
import time

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(_HERE), "backend"))
import listen_curriculum as L  # noqa: E402

LO, HI, START = L.TEST_STAIR["lo"], L.TEST_STAIR["hi"], L.TEST_STAIR["start"]
assert (LO, HI, START) == (L.STAIR["lo"], L.STAIR["hi"], L.STAIR["start"])


def _n_words(s: str) -> int:
    from sentence_feedback import consonant_feedback
    return int(consonant_feedback(s, "")["total_words"])


TEST_WORDS = np.array([_n_words(s) for s in L.TEST_FORMS["A"]])
assert list(TEST_WORDS) == [_n_words(s) for s in L.TEST_FORMS["B"]]
TEST_WORDS30 = np.concatenate([TEST_WORDS, TEST_WORDS[:10]])       # 시행 수 대비 정밀도용 30문장
TRAIN_WORDS = np.array([_n_words(s) for s in L.TRAIN_SENTENCES])

CONDITIONS = {
    "C0": {"sd_item": 0.0, "sd_trial": 0.0},
    "C1": {"sd_item": 1.0, "sd_trial": 0.0},
    "C2": {"sd_item": 2.0, "sd_trial": 0.0},
    "C3": {"sd_item": 1.0, "sd_trial": 2.0},
    # 보조 조건(사전 기준 판정에는 넣지 않음, 10/7 근거 조사 반영): 모든 청취자 기울기 9%/dB(K-HINT 문장 이해도 기울기, Moon 2005)
    "C4": {"sd_item": 1.0, "sd_trial": 0.0, "slope_fixed": 0.09},
    # 보조 조건: 낱말 사이 상관을 크게(제시마다 흔들림 4 dB). 의미 있는 짧은 문장의 독립 요소 수 j ≈ 2(Brand·Kollmeier 2002)에 가깝게
    "C5": {"sd_item": 1.0, "sd_trial": 4.0},
}
GROUPS = ["NH", "HA", "CI"]

# ── 가상 청취자 ──────────────────────────────────────────────────────


def make_listeners(rng, n):
    g = rng.choice(3, size=n, p=[0.2, 0.4, 0.4])
    srt = np.where(g == 0, rng.normal(-4.0, 1.0, n), np.where(g == 1, rng.uniform(-1.0, 8.0, n), rng.uniform(2.0, 22.0, n)))
    slope = np.clip(0.16 - 0.004 * (srt + 4.0) + rng.normal(0.0, 0.015, n), 0.05, 0.20)
    return {"group": g, "srt": srt, "slope": slope}


def respond(rng, x, srt, slope, offset, sd_trial, n):
    """x·srt·slope·offset·n: (B,). 맞힌 낱말 수 k (B,)."""
    eps = rng.normal(0.0, sd_trial, x.shape) if sd_trial > 0 else 0.0
    p = 1.0 / (1.0 + np.exp(-4.0 * slope * (x - srt - offset - eps)))
    return rng.binomial(n, p)


# ── 격자(베이지안·최대가능도) ────────────────────────────────────────

TH = np.arange(-15.0, 32.0 + 1e-9, 0.5)
SL = np.array([0.04, 0.05, 0.065, 0.08, 0.10, 0.125, 0.15, 0.18, 0.22])
NT, NS = len(TH), len(SL)
THg = np.repeat(TH, NS)          # (G,) 역치 먼저, 기울기 다음 순서
SLg = np.tile(SL, NT)
G = NT * NS
XC = np.arange(-10.0, 25.0 + 1e-9, 1.0)   # psi 후보 SNR
_EPS = 1e-9


def _p_grid(x):
    """x: (..., ) → (..., G) 낱말 정답 확률."""
    p = 1.0 / (1.0 + np.exp(-4.0 * SLg * (np.asarray(x)[..., None] - THg)))
    return np.clip(p, _EPS, 1 - _EPS)


def log_prior(kind):
    if kind == "flat":
        lp = np.zeros(G)
    else:   # psi 사전분포: 역치 N(5, 10²), 기울기 로그정규(중앙 0.10, 로그 SD 0.4)
        lp = -0.5 * ((THg - 5.0) / 10.0) ** 2 - 0.5 * ((np.log(SLg) - np.log(0.10)) / 0.4) ** 2
    return lp - lp.max()


def loglik(x, k, n):
    """한 시행의 격자 로그가능도(이항 계수 제외). x·k·n: (B,) → (B, G)."""
    p = _p_grid(x)
    return k[:, None] * np.log(p) + (n - k)[:, None] * np.log1p(-p)


def post_mean_th(logpost):
    lp = logpost - logpost.max(axis=-1, keepdims=True)
    w = np.exp(lp)
    return (w * THg).sum(-1) / w.sum(-1)


_PMF_CACHE = {}


def _pmf(n):
    """(n+1, len(XC), G) 이항 확률과 그 로그."""
    if n not in _PMF_CACHE:
        from math import comb
        p = _p_grid(XC)                                   # (X, G)
        ks = np.arange(n + 1)[:, None, None]
        c = np.array([comb(n, k) for k in range(n + 1)], float)[:, None, None]
        pm = c * p[None] ** ks * (1 - p[None]) ** (n - ks)
        _PMF_CACHE[n] = (pm, np.log(np.maximum(pm, 1e-300)))
    return _PMF_CACHE[n]


def psi_choose(logpost, n, marginal):
    """기대 사후 엔트로피가 가장 작은 후보 SNR의 색인. logpost: (B, G)."""
    lp = logpost - logpost.max(-1, keepdims=True)
    post = np.exp(lp)
    post /= post.sum(-1, keepdims=True)
    lpost = np.log(np.maximum(post, 1e-300))
    pm, lpm = _pmf(n)
    eh = np.zeros((post.shape[0], len(XC)))
    for k in range(n + 1):
        m = post @ pm[k].T                                                  # (B, X)
        if marginal:
            q = np.einsum("bts,xts->bxt", post.reshape(-1, NT, NS), pm[k].reshape(len(XC), NT, NS))
            sjlj = (q * np.log(np.maximum(q, 1e-300))).sum(-1)
        else:
            sjlj = (post * lpost) @ pm[k].T + post @ (pm[k] * lpm[k]).T
        eh += m * np.log(np.maximum(m, 1e-300)) - sjlj
    return np.argmin(eh, axis=1)


# ── 검사 절차 ────────────────────────────────────────────────────────


def a_next(x, ok, t, big_trials=None):
    bt = L.TEST_STAIR["big_trials"] if big_trials is None else big_trials
    step = L.TEST_STAIR["big"] if t < bt else L.TEST_STAIR["small"]
    return np.clip(x + np.where(ok, -step, step), LO, HI)


def mean_est(xs, nxt, n):
    """(a)의 역치를 n문장으로 늘린 것: 5~n번째 SNR과 다음 SNR의 평균."""
    return (xs[:, 4:n].sum(1) + nxt[:, n - 1]) / (n - 4 + 1)


class BK:
    """낱말 비율 걸음: ΔL = −f(i)(비율 − tar)/s0, f(i) = max(f_min, 1.5·1.41^−i), i = 방향 전환 수."""

    def __init__(self, B, tar, s0, f_min, double):
        self.tar, self.s0, self.f_min, self.double = tar, s0, f_min, double
        self.last = np.zeros(B)
        self.nrev = np.zeros(B)

    def step(self, x, prop):
        d = np.sign(self.tar - prop)                    # +1이면 SNR을 올린다
        rev = (d != 0) & (self.last != 0) & (d != self.last)
        self.nrev += rev
        self.last = np.where(d != 0, d, self.last)
        f = np.maximum(self.f_min, 1.5 * 1.41 ** (-self.nrev))
        dl = -f * (prop - self.tar) / self.s0
        if self.double:
            dl = np.where((f >= 0.5) & (dl < 0), 2 * dl, dl)
        return np.clip(np.round(x + dl, 1), LO, HI)


TEST_VARIANTS = {
    "a": {"kind": "a"},
    "b_s10": {"kind": "b", "s0": 0.10, "double": False},
    "b_s10_dbl": {"kind": "b", "s0": 0.10, "double": True},
    "b_s15": {"kind": "b", "s0": 0.15, "double": False},
    "b_s15_dbl": {"kind": "b", "s0": 0.15, "double": True},
    "c_joint": {"kind": "c", "marginal": False},
    "c_marg": {"kind": "c", "marginal": True},
    # 보조 변형(10/7 근거 조사 반영, 사전 등록 뒤 추가): ICRA 권고(Akeroyd 2015)·Brand·Kollmeier 2002의 식 그대로
    # (s0 0.15, f 하한 0.1, 내림 2배 없음)와, 문헌 대조용 2 dB 고정 1-up-1-down
    "b_icra": {"kind": "b", "s0": 0.15, "double": False, "f_min": 0.1},
    "a_2db": {"kind": "a", "big_trials": 0},
}
CHECK_N = (10, 15, 20, 30)


def run_test_once(rng, lis, cond, var, words, batch=250):
    """한 번의 검사(30문장까지). 추정량별 {n: (N,)}, 막힘 (N,)을 돌려준다."""
    N = len(lis["srt"])
    T = len(words)
    xs, props = np.zeros((N, T)), np.zeros((N, T))
    nxt = np.zeros((N, T))
    est = {}
    offs = rng.normal(0.0, cond["sd_item"], (N, T)) if cond["sd_item"] > 0 else np.zeros((N, T))
    kind = var["kind"]
    ests_ml = {n: np.zeros(N) for n in CHECK_N}
    for b0 in range(0, N, batch):
        sl = slice(b0, min(N, b0 + batch))
        B = sl.stop - sl.start
        srt, slope = lis["srt"][sl], lis["slope"][sl]
        x = np.full(B, START)
        bk = BK(B, 0.5, var.get("s0", 0.1), var.get("f_min", 0.25), var.get("double", False)) if kind == "b" else None
        logpost = np.tile(log_prior("psi" if kind == "c" else "flat"), (B, 1))
        for t in range(T):
            n = int(words[t])
            if kind == "c" and t > 0:
                x = XC[psi_choose(logpost, n, var["marginal"])]
            k = respond(rng, x, srt, slope, offs[sl, t], cond["sd_trial"], np.full(B, n))
            prop = k / n
            xs[sl, t], props[sl, t] = x, prop
            logpost = logpost + loglik(x, k, np.full(B, n))
            if kind == "a":
                x = a_next(x, prop >= L.TEST_STAIR["criterion"], t, var.get("big_trials"))
            elif kind == "b":
                x = bk.step(x, prop)
            nxt[sl, t] = x
            if (t + 1) in CHECK_N and kind in ("b", "c"):
                ests_ml[t + 1][sl] = post_mean_th(logpost)
    if kind in ("a", "b"):
        est["mean"] = {n: mean_est(xs, nxt, n) for n in CHECK_N}
    if kind in ("b", "c"):
        est["post"] = ests_ml
    blocked = ((xs[:, :20] >= HI - 1e-9) & (props[:, :20] < 0.5)).any(1)
    return est, blocked, xs, props


def check_a_matches_app(rng, lis, cond):
    """(a)의 벡터 구현이 앱 함수(test_next_snr·test_srt)와 같은지 50명으로 확인한다."""
    sub = {k: v[:50] for k, v in lis.items()}
    est, _, xs, props = run_test_once(rng, sub, cond, TEST_VARIANTS["a"], TEST_WORDS30)
    for i in range(50):
        trials = []
        for t in range(20):
            s = L.test_next_snr(trials) if trials else START
            assert abs(s - xs[i, t]) < 1e-9, (i, t, s, xs[i, t])
            trials.append((s, bool(props[i, t] >= 0.5)))
        assert abs(L.test_srt(trials) - est["mean"][20][i]) < 0.051


def summarize_test(lis, e1, e2, blocked):
    srt, g = lis["srt"], lis["group"]
    N = len(srt)
    d = e2 - e1
    err = np.concatenate([e1 - srt, e2 - srt])
    gg = np.concatenate([g, g])
    sdd = float(np.std(d, ddof=1))
    out = {"bias": float(err.mean()), "bias_se": float(err.std(ddof=1) / np.sqrt(2 * N)),
           "rmse": float(np.sqrt((err ** 2).mean())), "retest_sd": sdd, "retest_sd_se": sdd / np.sqrt(2 * (N - 1)),
           "sem": sdd / np.sqrt(2), "mdc95": 1.96 * sdd, "blocked": float(blocked.mean()),
           "blocked_se": float(np.sqrt(blocked.mean() * (1 - blocked.mean()) / blocked.size)), "groups": {}}
    for gi, gn in enumerate(GROUPS):
        m = g == gi
        sdg = float(np.std(d[m], ddof=1))
        out["groups"][gn] = {"n": int(m.sum()), "bias": float(err[gg == gi].mean()),
                             "bias_se": float(err[gg == gi].std(ddof=1) / np.sqrt(2 * m.sum())),
                             "rmse": float(np.sqrt((err[gg == gi] ** 2).mean())), "retest_sd": sdg, "sem": sdg / np.sqrt(2),
                             "mdc95": 1.96 * sdg,
                             "blocked": float(blocked[np.concatenate([m, m])].mean())}
    return out


def run_tests(seed, n_lis, variants, conds):
    res = {}
    for ci, (cn, cond) in enumerate(CONDITIONS.items()):
        if cn not in conds:
            continue
        rng = np.random.default_rng([seed, ci, 1])
        lis = make_listeners(rng, n_lis)
        if "slope_fixed" in cond:
            lis["slope"] = np.full(n_lis, cond["slope_fixed"])
        if cn == "C0":
            check_a_matches_app(np.random.default_rng([seed, 99]), lis, cond)
        res[cn] = {}
        for vn in variants:
            var = TEST_VARIANTS[vn]
            t0 = time.time()
            vr = np.random.default_rng([seed, ci, 2, list(TEST_VARIANTS).index(vn)])
            est1, bl1, _, _ = run_test_once(vr, lis, cond, var, TEST_WORDS30)
            est2, bl2, _, _ = run_test_once(vr, lis, cond, var, TEST_WORDS30)
            for en in est1:
                name = vn if (var["kind"] != "b") else f"{vn}_{en}"
                res[cn][name] = {"by_n": {}}
                for n in CHECK_N:
                    sm = summarize_test(lis, est1[en][n], est2[en][n], np.concatenate([bl1, bl2]))
                    if n == 20:
                        res[cn][name].update(sm)
                    res[cn][name]["by_n"][n] = {"rmse": sm["rmse"], "retest_sd": sm["retest_sd"], "bias": sm["bias"]}
            print(f"  검사 {cn} {vn}: {time.time() - t0:.1f}s", flush=True)
    return res


# ── 훈련 절차 ────────────────────────────────────────────────────────

N_TRAIN = 60
W = L.NOISE_MASTER["window"]

TRAIN_VARIANTS = {"a": {"kind": "a"}}
for _tar in (0.70, 0.75, 0.80):
    for _fm in (0.5, 1.0):
        for _est in ("shift", "fixml", "bayes"):
            TRAIN_VARIANTS[f"d{int(_tar * 100)}_f{int(_fm * 10):02d}_{_est}"] = {"kind": "d", "tar": _tar, "f_min": _fm, "est": _est}

# 보조 변형(10/7 근거 조사 반영): 가중 상하법(Kaernbach 1991). 문장 맞음(낱말 0.5 이상)이면 위 걸음 × (1−0.75)/0.75만큼 내리고
# 틀리면 위 걸음만큼 올린다. 위 걸음은 지금 계단처럼 방향 전환 2번까지 4 dB, 그 뒤 2 dB. 문장 맞음 75%에 모인다.
for _est in ("fixml", "bayes"):
    TRAIN_VARIANTS[f"k75_{_est}"] = {"kind": "k", "tar": 0.75, "f_min": 0.0, "est": _est}

_TH1 = np.arange(-15.0, 32.0 + 1e-9, 0.1)


def _window_est_fixml(x, k, n, a, b):
    """기울기 0.10 고정 최대가능도(0.1 dB 격자). x·k·n: (B, T)."""
    p = 1.0 / (1.0 + np.exp(-0.4 * (x[:, a:b, None] - _TH1)))
    p = np.clip(p, _EPS, 1 - _EPS)
    ll = (k[:, a:b, None] * np.log(p) + (n - k)[:, a:b, None] * np.log1p(-p)).sum(1)
    return _TH1[np.argmax(ll, axis=1)]


def train_scenario_srt(srt0, improve):
    """시행별 참 SRT (B, T). 향상: 21~40번째에 3 dB 곧게 낮아지고 그 뒤 유지."""
    t = np.arange(1, N_TRAIN + 1)
    drop = np.clip((t - 20) / 20.0, 0, 1) * 3.0 if improve else np.zeros(N_TRAIN)
    return srt0[:, None] - drop[None, :]


def run_train_a(rng, lis, cond, improve):
    N = len(lis["srt"])
    srt_t = train_scenario_srt(lis["srt"], improve)
    offs = rng.normal(0.0, cond["sd_item"], (N, len(TRAIN_WORDS))) if cond["sd_item"] > 0 else np.zeros((N, len(TRAIN_WORDS)))
    order = np.argsort(rng.random((N, len(TRAIN_WORDS))), axis=1)[:, :N_TRAIN]
    nw = TRAIN_WORDS[order]
    off = np.take_along_axis(offs, order, 1)
    mastered = np.zeros(N, bool)
    props = np.zeros((N, N_TRAIN))
    trials = [[] for _ in range(N)]
    x = np.full(N, START)
    for t in range(N_TRAIN):
        k = respond(rng, x, srt_t[:, t], lis["slope"], off[:, t], cond["sd_trial"], nw[:, t])
        props[:, t] = k / nw[:, t]
        for i in range(N):
            trials[i].append((float(x[i]), bool(props[i, t] >= L.STAIR["criterion"])))
            if not mastered[i] and t + 1 >= L.NOISE_MASTER["min_trials"] and L.noise_mastered(trials[i]):
                mastered[i] = True
        x = np.array([L.stair_state(tr)["next_db"] for tr in trials])
    return mastered, props


def run_train_d(rng, lis, cond, improve, var, batch=250):
    N = len(lis["srt"])
    srt_t = train_scenario_srt(lis["srt"], improve)
    offs = rng.normal(0.0, cond["sd_item"], (N, len(TRAIN_WORDS))) if cond["sd_item"] > 0 else np.zeros((N, len(TRAIN_WORDS)))
    order = np.argsort(rng.random((N, len(TRAIN_WORDS))), axis=1)[:, :N_TRAIN]
    nw = TRAIN_WORDS[order]
    off = np.take_along_axis(offs, order, 1)
    xs, ks, props = np.zeros((N, N_TRAIN)), np.zeros((N, N_TRAIN)), np.zeros((N, N_TRAIN))
    bk = BK(N, var["tar"], 0.10, var["f_min"], False)
    x = np.full(N, START)
    last, nrev = np.zeros(N), np.zeros(N)
    for t in range(N_TRAIN):
        k = respond(rng, x, srt_t[:, t], lis["slope"], off[:, t], cond["sd_trial"], nw[:, t])
        xs[:, t], ks[:, t], props[:, t] = x, k, k / nw[:, t]
        if var["kind"] == "k":
            ok = k / nw[:, t] >= L.STAIR["criterion"]
            d = np.where(ok, -1.0, 1.0)
            nrev += (last != 0) & (d != last)
            last = d
            up = np.where(nrev < L.STAIR["big_reversals"], L.STAIR["big"], L.STAIR["small"])
            x = np.clip(np.round(x + np.where(ok, -up * (1 - var["tar"]) / var["tar"], up), 2), LO, HI)
        else:
            x = bk.step(x, k / nw[:, t])
    # 20시행 창 역치 추정: est[:, j] = 시행 j..j+19(0부터)의 역치
    nwin = N_TRAIN - W + 1
    est = np.zeros((N, nwin))
    if var["est"] == "shift":
        cs = np.concatenate([np.zeros((N, 1)), np.cumsum(xs, 1)], 1)
        shift = np.log(var["tar"] / (1 - var["tar"])) / (4 * 0.10)
        for j in range(nwin):
            est[:, j] = (cs[:, j + W] - cs[:, j]) / W - shift
    elif var["est"] == "fixml":
        for j in range(nwin):
            est[:, j] = _window_est_fixml(xs, ks, nw, j, j + W)
    else:
        lp0 = log_prior("psi")
        for b0 in range(0, N, batch):
            sl = slice(b0, min(N, b0 + batch))
            ll = np.stack([loglik(xs[sl, t], ks[sl, t], nw[sl, t]) for t in range(N_TRAIN)], 1)   # (B, T, G)
            cs = np.concatenate([np.zeros((ll.shape[0], 1, G)), np.cumsum(ll, 1)], 1)
            for j in range(nwin):
                est[sl, j] = post_mean_th(cs[:, j + W] - cs[:, j] + lp0)
    first = est[:, 0]
    mastered = np.zeros(N, bool)
    for n in range(W, N_TRAIN + 1):
        recent = est[:, n - W]
        hit = recent <= L.NOISE_MASTER["srt_db"]
        if n >= 2 * W:
            hit |= (first - recent) >= L.NOISE_MASTER["gain_db"]
        mastered |= hit
    return mastered, props


def summarize_train(lis, m_null, m_imp, p_null):
    srt, g = lis["srt"], lis["group"]
    fm_mask = srt >= 2.0
    miss_mask = srt >= 5.0
    nh_mask = srt <= -2.0
    fm = m_null[fm_mask].mean()
    miss = 1 - m_imp[miss_mask].mean()
    wp = p_null[:, 10:].mean(1)
    out = {"false_mastery": float(fm), "false_mastery_se": float(np.sqrt(fm * (1 - fm) / fm_mask.sum())), "n_fm": int(fm_mask.sum()),
           "miss": float(miss), "miss_se": float(np.sqrt(miss * (1 - miss) / miss_mask.sum())), "n_miss": int(miss_mask.sum()),
           "nh_mastered": float(m_null[nh_mask].mean()), "word_prop": float(wp.mean()), "groups": {}}
    for gi, gn in enumerate(GROUPS):
        m = g == gi
        out["groups"][gn] = {"word_prop": float(wp[m].mean()),
                             "false_mastery": float(m_null[m & fm_mask].mean()) if (m & fm_mask).any() else None,
                             "miss": float(1 - m_imp[m & miss_mask].mean()) if (m & miss_mask).any() else None}
    return out


def run_trains(seed, n_lis, variants, conds):
    res = {}
    for ci, (cn, cond) in enumerate(CONDITIONS.items()):
        if cn not in conds:
            continue
        rng = np.random.default_rng([seed, ci, 3])
        lis = make_listeners(rng, n_lis)
        if "slope_fixed" in cond:
            lis["slope"] = np.full(n_lis, cond["slope_fixed"])
        res[cn] = {}
        cache = {}
        for vn in variants:
            var = TRAIN_VARIANTS[vn]
            t0 = time.time()
            # 같은 걸음 규칙(목표·f_min)은 같은 응답 난수를 쓴다(추정량만 다른 변형끼리 짝 비교)
            key = vn if var["kind"] == "a" else f"{var['tar']}_{var['f_min']}"
            sid = (list(TRAIN_VARIANTS).index(vn) if var["kind"] == "a" else
                   1000 + int(var["tar"] * 100) * 10 + int(var["f_min"] * 10) + (5000 if var["kind"] == "k" else 0))
            out = []
            for improve in (False, True):
                vr = np.random.default_rng([seed, ci, 4, sid, int(improve)])
                if var["kind"] == "a":
                    out.append(run_train_a(vr, lis, cond, improve))
                else:
                    out.append(run_train_d(vr, lis, cond, improve, var))
            (m0, p0), (m1, _) = out
            res[cn][vn] = summarize_train(lis, m0, m1, p0)
            cache[key] = True
            print(f"  훈련 {cn} {vn}: {time.time() - t0:.1f}s", flush=True)
    return res


# ── 출력 ─────────────────────────────────────────────────────────────


def print_tables(res):
    if "test" in res:
        print("\n[검사 20문장] 조건 절차: 편향 | 재검사SD | MDC95 | RMSE | 막힘% | 집단 편향(NH/HA/CI) | 집단 MDC95")
        for cn, rows in res["test"].items():
            for vn, r in rows.items():
                gb = "/".join(f"{r['groups'][g]['bias']:+.2f}" for g in GROUPS)
                gm = "/".join(f"{r['groups'][g]['mdc95']:.1f}" for g in GROUPS)
                print(f"  {cn} {vn:16s} {r['bias']:+.2f}±{r['bias_se']:.2f} | {r['retest_sd']:.2f}±{r['retest_sd_se']:.2f} | "
                      f"{r['mdc95']:.2f} | {r['rmse']:.2f} | {100 * r['blocked']:.1f} | {gb} | {gm}")
        print("\n[개인 내 SD = SEM] 조건 절차: 전체 | NH | HA | CI")
        for cn, rows in res["test"].items():
            for vn, r in rows.items():
                print(f"  {cn} {vn:16s} {r['sem']:.2f} | " + " | ".join(f"{r['groups'][g]['sem']:.2f}" for g in GROUPS))
        print("\n[시행 수 대비] 조건 절차: n=10/15/20/30 재검사 SD (RMSE)")
        for cn, rows in res["test"].items():
            for vn, r in rows.items():
                s = "  ".join(f"{r['by_n'][n]['retest_sd']:.2f}({r['by_n'][n]['rmse']:.2f})" for n in CHECK_N)
                print(f"  {cn} {vn:16s} {s}")
    if "train" in res:
        print("\n[훈련 60시행] 조건 절차: 거짓숙달% | 향상놓침% | NH숙달% | 낱말정답비율(전체 NH/HA/CI)")
        for cn, rows in res["train"].items():
            for vn, r in rows.items():
                gw = "/".join(f"{r['groups'][g]['word_prop']:.2f}" for g in GROUPS)
                print(f"  {cn} {vn:18s} {100 * r['false_mastery']:.1f}±{100 * r['false_mastery_se']:.1f} | "
                      f"{100 * r['miss']:.1f}±{100 * r['miss_se']:.1f} | {100 * r['nh_mastered']:.1f} | {r['word_prop']:.2f} ({gw})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--n", type=int, default=2000, help="조건마다 가상 청취자 수")
    ap.add_argument("--test", default=",".join(TEST_VARIANTS), help="검사 변형(쉼표), 빈 문자열이면 건너뜀")
    ap.add_argument("--train", default=",".join(TRAIN_VARIANTS), help="훈련 변형(쉼표), 빈 문자열이면 건너뜀")
    ap.add_argument("--conds", default="C0,C1,C2,C3", help="조건(쉼표). C4는 보조 조건")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    res = {"seed": a.seed, "n": a.n, "test_words": TEST_WORDS.tolist(),
           "train_word_counts": {int(k): int(v) for k, v in zip(*np.unique(TRAIN_WORDS, return_counts=True))}}
    t0 = time.time()
    if a.test:
        res["test"] = run_tests(a.seed, a.n, [v for v in a.test.split(",") if v], a.conds.split(","))
    if a.train:
        res["train"] = run_trains(a.seed, a.n, [v for v in a.train.split(",") if v], a.conds.split(","))
    res["elapsed_s"] = round(time.time() - t0, 1)
    print_tables(res)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=1)
        print("저장:", a.out)


if __name__ == "__main__":
    main()
