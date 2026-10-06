#!/usr/bin/env python
"""
P3 청인 또래 예비 파일럿 설계 모의실험(master-plan 2판 5절, idea-sweep 가1·나2·나15).

A-A-B 개인 내 설계: 학습 없이 사전 검사 두 번(A1, A2), 2주 학습 뒤 사후(B). 주지표는 사람별
D = (B − A2) − (A2 − A1) = B − 2·A2 + A1 (단위 %p)의 평균이다. 이 스크립트는 실제 얼굴 검사 두 층의 문항 수와 인원을
정하기 위해 다음을 계산한다.

  1) 고정 인원(n = 20·30·40)에서 층·문항 수별 검출력(95% 구간 하한 > 0), 구간 반폭, 3갈래 판정 확률
     (지지: 하한 > 0, 반증: 하한 ≤ 0이고 상한 < 최소 의미 효과 5%p, 판정 불가: 하한 ≤ 0이고 상한 ≥ 5%p)
     - 폐쇄형: 실제 얼굴 낱말 4지선다, 회당 12·24·48문항
     - 개방형: 실제 얼굴 문장 타이핑의 음소 정답률, 회당 20·40문장(문장 안 음소는 베타이항)
  2) 순차 베이즈 설계 분석: 5명마다 JZS 베이즈 인자, BF ≥ 6 또는 ≤ 1/6에서 멈춤, 최대 40명.
     효과 0과 가정 효과에서 기대 인원과 오도 증거율.
  3) 추천 설정에서 추측값 민감도.

모든 가정값은 PARAMS에 있고, 문서 docs/pilot/design-simulation.md 2절에 근거와 '추측' 여부를 적었다.
numpy만 쓴다(t 임계값은 scripts/pilot_analysis.py의 t_crit). 노트북에서 몇 분 안에 끝나게 반복 수를 잡았다.

    python3 scripts/pilot_design_sim.py                      # 전체(기본 시드 20261006), 결과 JSON을 docs/pilot/에 쓴다
    python3 scripts/pilot_design_sim.py --reps 400 --seq-reps 300 --out /tmp/x.json   # 빠른 점검
    python3 scripts/pilot_design_sim.py --selfcheck          # 베이즈 인자 수치 적분 교차 확인만
"""
import argparse
import json
import math
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from pilot_analysis import t_crit  # noqa: E402  (외부 의존 없는 t 임계값)

SEED = 20261006
MME = 5.0  # 최소 의미 효과(%p), master-plan 0절 원칙 3

# ───────────────────────── 가정값(문서 2절에 근거와 추측 여부) ─────────────────────────
PARAMS = {
    # 공통: 효과는 확률 척도(%p)에 더한다. 회차마다 사람의 상태 잡음(주의·피로)이 독립으로 붙는다.
    "retest_mean_pp": 3.0,      # A1→A2 재검사 효과 평균(추측)
    "retest_sd_pp": 2.0,        # 재검사 효과의 개인차(추측)
    "retest_ratio": 1.0,        # λ: A2→B 사이 재검사 효과 = λ × (A1→A2 효과). 1이면 주지표가 편향 없음(추측, 민감도에서 0~1)
    "state_sd_pp": 3.0,         # 회차별 상태 잡음 SD(추측)
    "transfer_sd_ratio": 0.5,   # 전이 효과 개인차 SD = 0.5 × 평균 효과(추측)
    # 개방형 문장(음소 정답률)
    "open_base_mean": 0.30,     # 청인 시각 단독 문장 음소 정답률 사전 평균(추측, 리허설·P20 자료로 교체)
    "open_person_sd_logit": 0.6,  # 사람 간 SD(로짓). 평균 근처에서 약 12%p(추측)
    "open_sent_sd_logit": 0.8,  # 문장 난이도 SD(로짓, 추측)
    "open_phon_min": 14,        # 문장당 채점 음소 수(무음 초성 ㅇ 제외) 하한·상한, 6~10음절 문장 가정
    "open_phon_max": 26,
    "open_icc": 0.25,           # 같은 문장 안 음소 정오의 상관(베타이항 과산포, 추측)
    # 폐쇄형 4지선다(실제 얼굴 낱말)
    "closed_guess": 0.25,
    "closed_disc": 1.2,         # 변별(assessment-design.md 6절과 같은 가정)
    "closed_item_sd": 1.0,      # 문항 난이도 SD(로짓, 추측)
    "closed_person_sd": 1.0,    # 사람 간 SD(로짓, 추측)
    "closed_base_mean": 0.50,   # 사전 평균 정답률(추측). 아래에서 사람 평균 로짓으로 바꾼다
    # 폼: 회차마다 서로 다른 동형 폼(A·B·C)을 순환 라틴 방진 3순서로 배정한다. 폼 난이도는 표본 문항에서 자연히 생긴다(맞춤 없음).
}

N_LIST = (20, 30, 40)
CLOSED_K = (12, 24, 48)
OPEN_S = (20, 40)
TAUS = (0.0, 5.0, 10.0)
ORDERS = np.array([[0, 1, 2], [1, 2, 0], [2, 0, 1]])  # 순서 o에서 회차 1·2·3에 쓰는 폼


def logistic(x):
    return 1.0 / (1.0 + np.exp(-x))


def logit(p):
    return math.log(p / (1 - p))


def _closed_mu(P):
    """폐쇄형 사전 평균 정답률이 closed_base_mean이 되도록 사람 평균 로짓을 찾는다(수치, 한 번만)."""
    rng = np.random.default_rng(0)
    th = rng.normal(0, P["closed_person_sd"], 20000)
    d = rng.normal(0, P["closed_item_sd"], 200)
    c, a = P["closed_guess"], P["closed_disc"]
    lo, hi = -5.0, 5.0
    for _ in range(50):
        mid = (lo + hi) / 2
        acc = (c + (1 - c) * logistic(a * (mid + th[:, None] - d[None, :]))).mean()
        lo, hi = (mid, hi) if acc < P["closed_base_mean"] else (lo, mid)
    return (lo + hi) / 2


def _gains(rng, R, n, tau, P):
    """회차별 확률 척도 가산값(R, n, 3), 단위 비율. 회차 1(A1)은 상태 잡음만.
    A2 = 기저 + ρ_i, B = 기저 + (1 + λ)ρ_i + τ_i 이므로 D의 기댓값은 τ + (λ − 1)ρ다."""
    rho = rng.normal(P["retest_mean_pp"], P["retest_sd_pp"], (R, n)) / 100
    tau_i = rng.normal(tau, P["transfer_sd_ratio"] * tau, (R, n)) / 100 if tau else np.zeros((R, n))
    g = rng.normal(0, P["state_sd_pp"] / 100, (R, n, 3))
    g[:, :, 1] += rho
    g[:, :, 2] += (1 + P["retest_ratio"]) * rho + tau_i   # 누적: A2까지 ρ, A2→B에 λρ가 더해진다
    return g


def sim_open(rng, R, n, S, tau, P):
    """개방형 문장 음소 정답률. 반환: 회차 점수(R, n, 3), 단위 %."""
    th = rng.normal(logit(P["open_base_mean"]), P["open_person_sd_logit"], (R, n))
    b = rng.normal(0, P["open_sent_sd_logit"], (R, 3, S))                      # 폼 3개 × 문장 S개
    m = rng.integers(P["open_phon_min"], P["open_phon_max"] + 1, (R, 3, S))
    order = ORDERS[np.arange(n) % 3]                                             # (n, 3) 회차 → 폼
    bf = b[:, order, :]                                                          # (R, n, 3, S)
    mf = m[:, order, :]
    pi = logistic(th[:, :, None, None] - bf) + _gains(rng, R, n, tau, P)[:, :, :, None]
    pi = np.clip(pi, 0.005, 0.995)
    k = 1.0 / P["open_icc"] - 1.0
    p = rng.beta(pi * k, (1 - pi) * k)
    y = rng.binomial(mf, p)
    return 100.0 * y.sum(-1) / mf.sum(-1)


def sim_closed(rng, R, n, K, tau, P, mu):
    th = rng.normal(mu, P["closed_person_sd"], (R, n))
    d = rng.normal(0, P["closed_item_sd"], (R, 3, K))
    order = ORDERS[np.arange(n) % 3]
    df_ = d[:, order, :]
    c, a = P["closed_guess"], P["closed_disc"]
    pr = c + (1 - c) * logistic(a * (th[:, :, None, None] - df_)) + _gains(rng, R, n, tau, P)[:, :, :, None]
    pr = np.clip(pr, 0.01, 0.99)
    y = rng.random(pr.shape) < pr
    return 100.0 * y.mean(-1)


def index_of(scores):
    """주지표 D = B − 2·A2 + A1(%p). scores: (..., 3)."""
    return scores[..., 2] - 2 * scores[..., 1] + scores[..., 0]


_TCRIT = {}


def tc(df):
    if df not in _TCRIT:
        _TCRIT[df] = t_crit(df, 0.95)
    return _TCRIT[df]


def order_adjusted(D):
    """순서(폼 배정)를 고정효과로 둔 D 평균. 사람 i의 순서는 i % 3(라틴 방진 3순서, 모집 순으로 돌려 배정).
    추정값 = 세 순서 평균의 평균, 오차 분산 = 순서 안 잔차의 합동 분산, 자유도 n − 3.
    폼 난이도 차이는 순서 평균에만 들어가므로 오차에서 빠진다(단순 평균의 t 구간은 이 차이를 사람 간 잡음으로 잘못 넣는다).
    반환: 추정값, 표준오차, 자유도, 유효 인원 n_eff = 9 / Σ(1/n_o)."""
    R, n = D.shape
    o = np.arange(n) % 3
    cnt = np.bincount(o, minlength=3).astype(float)
    M = np.stack([D[:, o == k].mean(1) for k in range(3)], 1)
    est = M.mean(1)
    resid = D - M[:, o]
    s2 = (resid ** 2).sum(1) / (n - 3)
    inv = (1.0 / cnt).sum()
    se = np.sqrt(s2 * inv / 9.0)
    return est, se, n - 3, 9.0 / inv, np.sqrt(s2)


def _verdict(m, h, true_mean, mme):
    lo, hi = m - h, m + h
    support = lo > 0
    refute = (~support) & (hi < mme)
    undecided = (~support) & (hi >= mme)
    return {
        "power": float(support.mean()),
        "halfwidth_mean": float(h.mean()),
        "halfwidth_p90": float(np.quantile(h, 0.9)),
        "verdict": {"support": float(support.mean()), "undecided": float(undecided.mean()),
                    "refute": float(refute.mean())},
        "support_but_below_mme": float((support & (hi < mme)).mean()),
        "mean_est": float(m.mean()),
        "bias": float(m.mean() - true_mean),
        "coverage": float(((lo <= true_mean) & (true_mean <= hi)).mean()),
    }


def summarize_fixed(D, true_mean, mme=MME):
    """D: (R, n). 주분석은 순서 고정효과 추정(order_adjusted), 단순 평균 t 구간은 'naive'로 함께 둔다."""
    R, n = D.shape
    est, se, df, neff, sw = order_adjusted(D)
    out = _verdict(est, tc(df) * se, true_mean, mme)
    out["sd_index_within_order"] = float(sw.mean())
    m = D.mean(1)
    sd = D.std(1, ddof=1)
    naive = _verdict(m, tc(n - 1) * sd / math.sqrt(n), true_mean, mme)
    naive["sd_index"] = float(sd.mean())
    out["naive"] = naive
    return out


def run_chunked(fn, reps, chunk, *args):
    out = []
    done = 0
    while done < reps:
        r = min(chunk, reps - done)
        out.append(fn(r, *args))
        done += r
    return np.concatenate(out, 0)


# ───────────────────────── JZS 베이즈 인자(일표본 t, Rouder 외 2009) ─────────────────────────
def _central_t_pdf(t, nu):
    c = math.exp(math.lgamma((nu + 1) / 2) - math.lgamma(nu / 2)) / math.sqrt(nu * math.pi)
    return c * (1 + t * t / nu) ** (-(nu + 1) / 2)


def bf_table(neff, nu, r, tgrid, Q=400, W=900):
    """관측 t의 격자에서 BF+0(한쪽, δ>0 반코시)과 BF10(양쪽 코시)을 수치 적분으로 계산한다.
    p(t | δ) = ∫ φ(t·w − δ√n) · w · f_w(w) dw, w = √(V/ν), V ~ χ²_ν(비중심 t의 혼합 표현).
    δ는 반코시 분위수 격자(δ = r·tan(πq/2), q 등간격 중점)라 사전 질량이 균등 가중이다.
    일표본이면 neff = n, nu = n − 1. 순서 고정효과 추정이면 neff = 9/Σ(1/n_o), nu = n − 3(δ는 순서 안 SD 단위)."""
    wmax = 1.0 + 10.0 * math.sqrt(2.0 / nu) + 0.5
    w = np.linspace(wmax / W / 2, wmax, W)
    dw = w[1] - w[0]
    v = nu * w * w
    logf = (nu / 2 - 1) * np.log(v) - v / 2 - (nu / 2) * math.log(2) - math.lgamma(nu / 2)
    fw = np.exp(logf) * 2 * nu * w
    fw /= (fw * dw).sum()                                  # 이산화 보정
    q = (np.arange(Q) + 0.5) / Q
    mu = r * np.tan(math.pi * q / 2) * math.sqrt(neff)
    weight = (w * fw * dw)[None, None, :]
    num = np.empty(len(tgrid))
    step = 24
    for s in range(0, len(tgrid), step):
        t = tgrid[s:s + step]
        z = t[:, None, None] * w[None, None, :] - mu[None, :, None]
        dens = (np.exp(-0.5 * z * z) / math.sqrt(2 * math.pi) * weight).sum(-1)   # (T, Q)
        num[s:s + step] = dens.mean(1)
    den = np.array([_central_t_pdf(float(t), nu) for t in tgrid])
    plus = num / den
    minus = plus[::-1]                                     # 격자가 0에 대칭이라 p(t|−δ) = p(−t|δ)
    return plus, 0.5 * (plus + minus)


def bf10_gint(t, n, r):
    """교차 확인용: Rouder 외 2009 식(양쪽 JZS), g에 대한 1차원 적분(로그 격자)."""
    nu = n - 1
    lg = np.linspace(-12, 12, 20001)
    g = np.exp(lg)
    a = 1 + n * g * r * r
    f = a ** -0.5 * (1 + t * t / (a * nu)) ** (-(nu + 1) / 2) * (2 * math.pi) ** -0.5 * g ** -1.5 * np.exp(-1 / (2 * g))
    integ = (f * g).sum() * (lg[1] - lg[0])
    return integ / (1 + t * t / nu) ** (-(nu + 1) / 2)


def selfcheck(r=math.sqrt(2) / 2):
    tg = np.round(np.arange(-12, 12.0001, 0.05), 4)
    rows = []
    for n in (5, 10, 20, 40):
        plus, two = bf_table(n, n - 1, r, tg)
        for t in (0.0, 1.0, 2.0, 3.0, 4.0):
            i = int(np.argmin(np.abs(tg - t)))
            rows.append({"n": n, "t": t, "bf10_grid": float(two[i]), "bf10_gint": float(bf10_gint(t, n, r)),
                         "bfplus0_grid": float(plus[i])})
    return rows


# ───────────────────────── 순차 설계 ─────────────────────────
def look_design(nk):
    """nk명일 때 순서 고정효과 추정의 유효 인원과 자유도(사람 i의 순서 = i % 3)."""
    cnt = np.bincount(np.arange(nk) % 3, minlength=3).astype(float)
    return 9.0 / (1.0 / cnt).sum(), nk - 3


def sequential(D, looks, tables, tgrid, upper=6.0, lower=1 / 6, n_min=5, sided="plus"):
    """D: (R, nmax). nk명마다 순서 고정효과 t(order_adjusted)로 BF를 구해 멈춤 규칙을 적용한다.
    sided='plus'면 BF+0(δ>0), 'two'면 BF10(위 문턱은 평균 부호로 지지·반대 방향을 가른다)."""
    R = D.shape[0]
    stop_n = np.full(R, looks[-1])
    outcome = np.zeros(R, dtype=int)   # 1: 지지 쪽 멈춤, −1: 영가설 쪽 멈춤, 2: 반대 방향(양쪽만), 0: 최대 인원에서 미결
    final_bf = np.full(R, np.nan)
    stopped = np.zeros(R, dtype=bool)
    for nk in looks:
        est, se, _, _, _ = order_adjusted(D[:, :nk])
        t = est / se
        tab = tables[nk][0 if sided == "plus" else 1]
        bf = np.exp(np.interp(np.clip(t, tgrid[0], tgrid[-1]), tgrid, np.log(tab)))
        active = ~stopped
        if nk >= n_min:
            up = active & (bf >= upper)
            dn = active & (bf <= lower)
            if sided == "two":
                outcome[up & (est < 0)] = 2
                outcome[up & (est >= 0)] = 1
            else:
                outcome[up] = 1
            outcome[dn] = -1
            hit = up | dn
            stop_n[hit] = nk
            final_bf[hit] = bf[hit]
            stopped |= hit
        if nk == looks[-1]:
            final_bf[~stopped] = bf[~stopped]
    return stop_n, outcome, final_bf


def seq_summary(stop_n, outcome, final_bf, D, true_mean):
    R = len(stop_n)
    # 멈춘 시점에서 고정 인원용 95% 구간(순서 고정효과)을 그대로 계산했을 때 참값을 포함하는 비율
    # 같은 구간으로 낸 3갈래 판정(지지: 하한 > 0, 반증: 하한 ≤ 0이고 상한 < MME, 판정 불가: 나머지)
    cover = 0
    vc = {"support": 0, "undecided": 0, "refute": 0}
    for nk in np.unique(stop_n):
        sel = stop_n == nk
        est, se, df, _, _ = order_adjusted(D[sel, :nk])
        h = tc(df) * se
        lo, hi = est - h, est + h
        cover += int(((lo <= true_mean) & (true_mean <= hi)).sum())
        sup = lo > 0
        vc["support"] += int(sup.sum())
        vc["refute"] += int(((~sup) & (hi < MME)).sum())
        vc["undecided"] += int(((~sup) & (hi >= MME)).sum())
    return {
        "expected_n": float(stop_n.mean()),
        "median_n": float(np.median(stop_n)),
        "p_n_le_30": float((stop_n <= 30).mean()),
        "p_stop_h1": float((outcome == 1).mean()),
        "p_stop_h0": float((outcome == -1).mean()),
        "p_stop_harm": float((outcome == 2).mean()),
        "p_max_undecided": float((outcome == 0).mean()),
        "ci_coverage_at_stop": cover / R,
        "ci_verdict_at_stop": {k: v / R for k, v in vc.items()},
    }


# ───────────────────────── 실행 ─────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--reps", type=int, default=4000, help="고정 인원 조건마다 반복 수")
    ap.add_argument("--seq-reps", type=int, default=4000, help="순차 설계 조건마다 반복 수")
    ap.add_argument("--sens-reps", type=int, default=2000, help="민감도 조건마다 반복 수")
    ap.add_argument("--rec-open-s", type=int, default=40, help="민감도·순차 기준 개방형 문장 수")
    ap.add_argument("--rec-n", type=int, default=30, help="민감도 기준 인원")
    ap.add_argument("--out", default=os.path.join(HERE, "..", "docs", "pilot", "design-simulation.json"))
    ap.add_argument("--selfcheck", action="store_true")
    a = ap.parse_args()

    r_prior = math.sqrt(2) / 2
    if a.selfcheck:
        for row in selfcheck(r_prior):
            print(row)
        return

    t0 = time.time()
    P = dict(PARAMS)
    rng = np.random.default_rng(a.seed)
    mu_closed = _closed_mu(P)
    lam_bias = (P["retest_ratio"] - 1) * P["retest_mean_pp"]
    res = {"seed": a.seed, "params": P, "mme_pp": MME, "reps": a.reps, "seq_reps": a.seq_reps,
           "sens_reps": a.sens_reps, "closed_mu_logit": mu_closed, "fixed": [], "sequential": [], "sensitivity": []}

    # 1) 고정 인원
    for n in N_LIST:
        for tau in TAUS:
            true_mean = tau + lam_bias
            for K in CLOSED_K:
                sc = run_chunked(lambda r: sim_closed(rng, r, n, K, tau, P, mu_closed), a.reps, 1000)
                s = summarize_fixed(index_of(sc), true_mean)
                s.update({"layer": "closed", "items": K, "n": n, "tau": tau,
                          "pre_mean": float(sc[..., 0].mean()), "pre_sd_between": float(sc[..., 0].std(1, ddof=1).mean())})
                res["fixed"].append(s)
            for S in OPEN_S:
                sc = run_chunked(lambda r: sim_open(rng, r, n, S, tau, P), a.reps, 250)
                s = summarize_fixed(index_of(sc), true_mean)
                s.update({"layer": "open", "items": S, "n": n, "tau": tau,
                          "pre_mean": float(sc[..., 0].mean()), "pre_sd_between": float(sc[..., 0].std(1, ddof=1).mean())})
                res["fixed"].append(s)
        print(f"[고정] n={n} 끝 ({time.time() - t0:.0f}s)", flush=True)

    # 2) 순차 베이즈(주결과 = 개방형). 표는 사전 척도·확인 시점마다 한 번만 만든다
    tgrid = np.round(np.arange(-12, 12.0001, 0.05), 4)
    looks = list(range(5, 41, 5))
    priors = (r_prior, 0.5, 0.35)
    tables = {r: {nk: bf_table(*look_design(nk), r, tgrid) for nk in looks} for r in priors}
    res["bf_selfcheck"] = selfcheck(r_prior)
    res["bf_at_t0"] = {str(r): {str(nk): float(np.interp(0.0, tgrid, tables[r][nk][1])) for nk in looks} for r in priors}
    print(f"[BF 표] 끝 ({time.time() - t0:.0f}s)", flush=True)
    seq_variants = [(r, n_min, "plus") for r in priors for n_min in (5, 10, 20)] + [(r_prior, 10, "two")]
    for S in OPEN_S:
        for tau in TAUS:
            true_mean = tau + lam_bias
            D = index_of(run_chunked(lambda r: sim_open(rng, r, 40, S, tau, P), a.seq_reps, 250))
            for r, n_min, sided in seq_variants:
                st = sequential(D, looks, tables[r], tgrid, n_min=n_min, sided=sided)
                s = seq_summary(*st, D, true_mean)
                s.update({"layer": "open", "items": S, "tau": tau, "n_min": n_min, "sided": sided, "prior_r": r})
                res["sequential"].append(s)
        print(f"[순차] S={S} 끝 ({time.time() - t0:.0f}s)", flush=True)

    # 3) 민감도(추천 기준 설정, τ = 5와 0)
    S0, n0 = a.rec_open_s, a.rec_n
    variants = [("기준", {})]
    variants += [(f"사전 평균 {v:.2f}", {"open_base_mean": v}) for v in (0.15, 0.45)]
    variants += [(f"문장 내 상관 {v}", {"open_icc": v}) for v in (0.10, 0.40)]
    variants += [(f"문장 난이도 SD {v}", {"open_sent_sd_logit": v}) for v in (0.5, 1.2)]
    variants += [(f"상태 잡음 {v}%p", {"state_sd_pp": v}) for v in (2.0, 5.0)]
    variants += [(f"전이 개인차 비 {v}", {"transfer_sd_ratio": v}) for v in (0.0, 1.0)]
    variants += [(f"재검사 비 λ {v}", {"retest_ratio": v}) for v in (0.0, 0.5)]
    for name, ov in variants:
        Pv = dict(P, **ov)
        for tau in (0.0, 5.0):
            D = index_of(run_chunked(lambda r: sim_open(rng, r, n0, S0, tau, Pv), a.sens_reps, 250))
            s = summarize_fixed(D, tau)   # 편향·포함률은 참 전이 τ 기준(λ < 1이면 (λ − 1)ρ만큼 낮게 나온다)
            s.update({"variant": name, "override": ov, "tau": tau, "n": n0, "items": S0})
            res["sensitivity"].append(s)
    print(f"[민감도] 끝 ({time.time() - t0:.0f}s)", flush=True)

    # 4) 잡음 바닥: 문장 수를 늘려도 줄지 않는 몫(회차 상태 잡음 × √6)을 보인다(τ = 0, n = 40)
    res["floor"] = []
    for S in (20, 40, 80, 160):
        for state in (P["state_sd_pp"], 0.0):
            Pv = dict(P, state_sd_pp=state)
            D = index_of(run_chunked(lambda r: sim_open(rng, r, 40, S, 0.0, Pv), 500, 100))
            _, _, _, _, sw = order_adjusted(D)
            res["floor"].append({"items": S, "state_sd_pp": state, "sd_index_within_order": float(sw.mean())})
    print(f"[바닥] 끝 ({time.time() - t0:.0f}s)", flush=True)

    res["elapsed_s"] = round(time.time() - t0, 1)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    _print_tables(res)
    print(f"\n저장: {os.path.abspath(a.out)} ({res['elapsed_s']}s)")


def _print_tables(res):
    print("\n## 고정 인원: 검출력(하한>0) / 반폭 / 지지·판정불가·반증")
    for row in res["fixed"]:
        v = row["verdict"]
        print(f"{row['layer']:6s} 문항{row['items']:3d} n{row['n']:3d} τ{row['tau']:4.0f}  검출력 {row['power']:.3f}  "
              f"반폭 {row['halfwidth_mean']:5.2f}  SD(D|순서) {row['sd_index_within_order']:5.2f}  "
              f"지지 {v['support']:.3f} 불가 {v['undecided']:.3f} 반증 {v['refute']:.3f}  "
              f"편향 {row['bias']:+.2f} 포함 {row['coverage']:.3f} (단순: 검출력 {row['naive']['power']:.3f} 포함 {row['naive']['coverage']:.3f})  "
              f"사전 {row['pre_mean']:.1f}±{row['pre_sd_between']:.1f}")
    print("\n## 순차 베이즈")
    for row in res["sequential"]:
        print(f"S{row['items']} τ{row['tau']:4.0f} r{row['prior_r']:.3f} n_min{row['n_min']:3d} {row['sided']:4s}  기대n {row['expected_n']:5.1f}  "
              f"H1멈춤 {row['p_stop_h1']:.3f}  H0멈춤 {row['p_stop_h0']:.3f}  반대 {row['p_stop_harm']:.3f}  "
              f"미결 {row['p_max_undecided']:.3f}  n≤30 {row['p_n_le_30']:.3f}  구간포함 {row['ci_coverage_at_stop']:.3f}")
    print("\n## 민감도")
    for row in res["sensitivity"]:
        v = row["verdict"]
        print(f"{row['variant']:16s} τ{row['tau']:3.0f}  검출력 {row['power']:.3f}  반폭 {row['halfwidth_mean']:5.2f}  "
              f"지지 {v['support']:.3f} 불가 {v['undecided']:.3f} 반증 {v['refute']:.3f}  편향 {row['bias']:+.2f}")
    print("\n## 잡음 바닥(SD(D|순서), τ=0, n=40)")
    for row in res["floor"]:
        print(f"문장 {row['items']:4d}  상태 잡음 {row['state_sd_pp']:.0f}%p  SD {row['sd_index_within_order']:.2f}")
    print("\n## BF 교차 확인")
    for row in res["bf_selfcheck"]:
        print(row)


if __name__ == "__main__":
    main()
