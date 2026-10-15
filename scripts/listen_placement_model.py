"""
소리 듣기 배치검사(시작 단계 정하기)의 채점 모형. docs/listen-placement-2026-10.md 4.3~4.4절.

격자 사후분포(EAP)로 '처음으로 숙달하지 못한 단계'(1~5)의 확률을 구한다. 독화 배치검사(assessment.ability_eap,
stage_probabilities)와 같은 방식이고, 소리 듣기 단계마다 과제가 달라 능력을 둘로 둔다.
  θ  잡담 잡음 속 SRT50(dB, 네 훈련 목소리 평균 기준). 소음 속 문장이 직접 알려 준다
  z  조용한 곳 능력(로짓) = A0 − B_LINK·θ + u. 조용한 곳 문장이 직접 알려 주고, 소음 속 문장은 연결 가정으로 간접 알려 준다
  d  과제별 편차(소리 구별 d_a, 낱말 고르기 d_w). 그 과제 문항만 알려 준다(z가 주어지면 과제끼리 독립)
시작 단계: 1 소리 구별(z + d_a < C_AX) → 2 낱말 고르기(z + d_w < C_WORD) → 3 문장(z < C_Q) → 4 소음 속(θ > 0) → 5 대화.

순수 numpy. 배치(B명)로 계산한다. 2026-10-15 탐색에서 사전 기준을 넘은 절차가 없어(문서 8절) 앱에는 넣지 않았고,
시뮬레이션(scripts/listen_placement_sim.py)만 쓴다. 다음 등록에서 앱에 넣게 되면 backend로 옮기고 한 사람(B = 1)용 함수를 더한다.
"""
import math
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

# ── 채점 모형(사전 등록 값) ────────────────────────────────────────────
A0, B_LINK = 3.9, 0.175          # z = A0 − B_LINK·θ + u
SIG_U, TAU = 0.7, 0.7            # u, d의 사전 SD(로짓)
PRIOR_TH = (5.0, 10.0)           # θ ~ N(5, 10²)
LAPSE = 0.02                     # 문장 낱말은 0.98배, 고르는 문항은 2%를 우연 수준으로
C_AX = math.log(0.8 / 0.2)       # 소리 구별 수준 4: 1/2 + 1/2·L ≥ 0.9
C_WORD = math.log((0.8 - 0.25) / 0.75 / (1 - (0.8 - 0.25) / 0.75))   # 낱말 수준 3: 1/4 + 3/4·L ≥ 0.8
C_Q = math.log(0.8 / 0.2)        # 조용한 곳 문장 낱말 비율 0.8
SRT_MASTER = 0.0                 # 4단계: SRT50 ≤ 0 dB

TH = np.arange(-12.0, 30.0 + 1e-9, 1.0)
UG = np.round(np.arange(-2.1, 2.1 + 1e-9, 0.35), 6)
DG = UG.copy()
THg = np.repeat(TH, len(UG))
Ug = np.tile(UG, len(TH))
Zg = A0 - B_LINK * THg + Ug
G, D = len(THg), len(DG)
LOGPRIOR = -0.5 * ((THg - PRIOR_TH[0]) / PRIOR_TH[1]) ** 2 - 0.5 * (Ug / SIG_U) ** 2
_pd = np.exp(-0.5 * (DG / TAU) ** 2)
PD = _pd / _pd.sum()

SNR_CANDS = (-6.0, -3.0, 0.0, 3.0, 6.0, 10.0, 14.0, 18.0)
COST = {"pa": 12, "pw": 15, "pq": 40, "pn": 40}   # 초(listen_curriculum.TODAY_SECONDS의 ax·word_id·sentence·noise)
N_WORDS = 4
MAX_ITEMS, MAX_SECONDS = 16, 300
STAGES = (1, 2, 3, 4, 5)
_EPS = 1e-12


def _sig(x):
    return 1.0 / (1.0 + np.exp(-x))


def slope_of(th):
    """3.1절 기울기 직선(잡음 없음)."""
    return np.clip(0.16 - 0.004 * (np.asarray(th, float) + 4.0), 0.05, 0.20)


SLg = slope_of(THg)
P_Q = np.clip((1 - LAPSE) * _sig(Zg), _EPS, 1 - _EPS)                       # (G,) 조용한 곳 낱말
_ZD = Zg[:, None] + DG[None, :]
P_A = np.clip(LAPSE * 0.5 + (1 - LAPSE) * (0.5 + 0.5 * _sig(_ZD)), _EPS, 1 - _EPS)    # (G, D)
P_W = np.clip(LAPSE * 0.25 + (1 - LAPSE) * (0.25 + 0.75 * _sig(_ZD)), _EPS, 1 - _EPS)
LP_A, LQ_A = np.log(P_A), np.log1p(-P_A)
LP_W, LQ_W = np.log(P_W), np.log1p(-P_W)
PASS_A = (_ZD >= C_AX).astype(float)
PASS_W = (_ZD >= C_WORD).astype(float)
Q_PASS = (Zg >= C_Q).astype(float)
N_PASS = (THg <= SRT_MASTER).astype(float)
_BIN = np.array([math.comb(N_WORDS, k) for k in range(N_WORDS + 1)], float)


def p_noise(x_eff) -> np.ndarray:
    """실효 SNR x(...,) → (..., G) 낱말 정답 확률."""
    x = np.asarray(x_eff, float)[..., None]
    return np.clip((1 - LAPSE) * _sig(4.0 * SLg * (x - THg)), _EPS, 1 - _EPS)


def binom_pmf(p: np.ndarray, n: int = N_WORDS) -> np.ndarray:
    """p (..., G) → (n+1, ..., G)."""
    ks = np.arange(n + 1).reshape((-1,) + (1,) * p.ndim)
    c = np.array([math.comb(n, k) for k in range(n + 1)], float).reshape(ks.shape)
    return c * p[None] ** ks * (1 - p[None]) ** (n - ks)


_PMF_Q = binom_pmf(P_Q)                                                      # (5, G)
_PMF_N = np.stack([binom_pmf(p_noise(x)) for x in SNR_CANDS], 0)             # (X, 5, G)


def sentence_loglik(k, n, p) -> np.ndarray:
    """k·n (B,), p (B, G) 또는 (G,) → (B, G)."""
    k = np.asarray(k, float)[:, None]
    n = np.asarray(n, float)[:, None]
    return k * np.log(p) + (n - k) * np.log1p(-p)


def _task(n, k, LP, LQ, PASS):
    """과제 자료(정답 k / n, (B,)) → (그 과제의 주변 로그가능도 (B, G), 통과 확률 π (B, G))."""
    n = np.asarray(n, float)[:, None, None]
    k = np.asarray(k, float)[:, None, None]
    L = k * LP[None] + (n - k) * LQ[None]                 # (B, G, D)
    m = L.max(-1, keepdims=True)
    e = np.exp(L - m) * PD
    s = e.sum(-1)
    return np.log(s) + m[..., 0], (e * PASS[None]).sum(-1) / s


def stage_matrix(pi_a, pi_w) -> np.ndarray:
    """격자 점마다 시작 단계 확률 (B, G, 5)."""
    q, nn = Q_PASS[None], N_PASS[None]
    base = pi_a * pi_w
    return np.stack([1 - pi_a, pi_a * (1 - pi_w), base * (1 - q), base * q * (1 - nn), base * q * nn], -1)


def _norm(logw):
    w = np.exp(logw - logw.max(-1, keepdims=True))
    return w / w.sum(-1, keepdims=True)


def _entropy(p):
    p = np.clip(p, 1e-15, 1.0)
    return -(p * np.log(p)).sum(-1)


class Batch:
    """B명의 배치검사 상태(충분 통계). ll: 문장 로그가능도 (B, G), na·ka·nw·kw: 소리 구별·낱말 문항 수와 정답 수."""

    def __init__(self, b: int):
        self.ll = np.zeros((b, G))
        self.na = np.zeros(b)
        self.ka = np.zeros(b)
        self.nw = np.zeros(b)
        self.kw = np.zeros(b)

    def add_noise(self, idx, x_eff, k, n):
        self.ll[idx] += sentence_loglik(k, n, p_noise(np.asarray(x_eff, float)))

    def add_quiet(self, idx, k, n):
        self.ll[idx] += sentence_loglik(k, n, P_Q)

    def add_ax(self, idx, ok):
        self.na[idx] += 1
        self.ka[idx] += np.asarray(ok, float)

    def add_word(self, idx, ok):
        self.nw[idx] += 1
        self.kw[idx] += np.asarray(ok, float)

    def posterior(self):
        """(정규화한 사후 무게 w (B, G), 시작 단계 행렬 S (B, G, 5), 과제별 (주변 로그가능도, π))."""
        la, pa = _task(self.na, self.ka, LP_A, LQ_A, PASS_A)
        lw, pw = _task(self.nw, self.kw, LP_W, LQ_W, PASS_W)
        logw = LOGPRIOR[None] + self.ll + la + lw
        return _norm(logw), stage_matrix(pa, pw), (la, pa), (lw, pw)

    def stage_probs(self) -> np.ndarray:
        w, S, _, _ = self.posterior()
        return np.einsum("bg,bgs->bs", w, S)

    def choose(self, gamma: float = 1.0, allowed: Sequence[str] = ("pa", "pw", "pq", "pn"),
               avail: Optional[Dict[str, np.ndarray]] = None) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """후보마다 시작 단계 분포의 기대 엔트로피 감소 / (초)^γ가 가장 큰 것. 반환 (종류 색인 (B,), SNR (B,), 점수 (B, C)).
        종류 색인: 0 pa, 1 pw, 2 pq, 3.. pn(SNR_CANDS 순서). avail[종류]가 거짓인 사람은 그 종류를 고르지 않는다(문항 소진)."""
        w, S, (la, _), (lw, _) = self.posterior()
        H0 = _entropy(np.einsum("bg,bgs->bs", w, S))
        b = w.shape[0]
        names = ["pa", "pw", "pq"] + ["pn"] * len(SNR_CANDS)
        score = np.full((b, len(names)), -np.inf)

        def gain_from_pmf(pmf):
            u = np.einsum("bg,kg,bgs->bks", w, pmf, S)            # (B, K, 5)
            pred = u.sum(-1)
            post = u / np.maximum(pred[..., None], 1e-300)
            return H0 - (pred * _entropy(post)).sum(-1)

        def gain_task(kind):
            out = 0.0
            for ok in (1.0, 0.0):
                if kind == "pa":
                    l2, p2 = _task(self.na + 1, self.ka + ok, LP_A, LQ_A, PASS_A)
                    _, pw_ = _task(self.nw, self.kw, LP_W, LQ_W, PASS_W)
                    S2 = stage_matrix(p2, pw_)
                    w2 = w * np.exp(l2 - la)
                else:
                    l2, p2 = _task(self.nw + 1, self.kw + ok, LP_W, LQ_W, PASS_W)
                    _, pa_ = _task(self.na, self.ka, LP_A, LQ_A, PASS_A)
                    S2 = stage_matrix(pa_, p2)
                    w2 = w * np.exp(l2 - lw)
                pred = w2.sum(-1)
                post = np.einsum("bg,bgs->bs", w2, S2) / np.maximum(pred[:, None], 1e-300)
                out = out + pred * _entropy(post)
            return H0 - out

        for ci, name in enumerate(names):
            if name not in allowed:
                continue
            if name == "pa":
                g = gain_task("pa")
            elif name == "pw":
                g = gain_task("pw")
            elif name == "pq":
                g = gain_from_pmf(_PMF_Q)
            else:
                g = gain_from_pmf(_PMF_N[ci - 3])
            sc = g / (COST[name] ** gamma)
            if avail is not None and name in avail:
                sc = np.where(avail[name], sc, -np.inf)
            score[:, ci] = sc
        best = score.argmax(-1)
        snr = np.array([SNR_CANDS[i - 3] if i >= 3 else np.nan for i in best])
        return best, snr, score


KIND_OF = ["pa", "pw", "pq"] + ["pn"] * len(SNR_CANDS)


def decide(probs: np.ndarray, rule: str = "mode") -> np.ndarray:
    """시작 단계 확률 (..., 5) → 배치 단계(1~5). rule 'mode' 또는 'q0.7'처럼 P(참 ≥ k) ≥ q인 가장 큰 k."""
    probs = np.asarray(probs, float)
    if rule == "mode":
        return probs.argmax(-1) + 1
    q = float(rule[1:])
    tail = np.cumsum(probs[..., ::-1], -1)[..., ::-1]     # P(참 ≥ k), k = 1..5
    ok = tail >= q - 1e-12
    return np.where(ok, np.arange(1, 6), 0).max(-1)
