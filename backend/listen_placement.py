"""
소리 듣기 배치검사 후보 D(docs/listen-placement3-2026-10.md 2절, 10절 설계). 서버 플래그 LISTEN_PLACEMENT=D일 때만 API가 쓴다(기본 끔).

1·2단계는 건너뛰지 않고 두 단계의 시작 수준만 정하며, 3~5단계 가운데 어디까지 열지를 정한다. 동결한 조합은
D|g1|m4|s0.95|upper|mode|q0.8(γ 1, 최소 4문항, 위 단계 최대 확률 0.95에서 멈춤, 16문항·300초 상한, 위 단계 mode, 두 수준 q 0.8)이다.
채점 모형·문항 고르기·멈춤·결정은 scripts/listen_placement_model.py, listen_placement2_sim.py(후보 A의 수준 모형),
listen_placement3_sim.py(BatchD, run_chunk_d, eval_d)의 식을 한 사람(B = 1)용으로 그대로 옮겼다. 식과 연산 차례를 바꾸지 않아야
시뮬레이션과 같은 결정을 낸다(test_listen_placement.py의 일치 시험이 시뮬레이터를 직접 돌려 확인한다).

**순수 함수만 둔다**(DB·네트워크 없음). 두 층으로 나눈다.
  1. 채점·결정 층: 답 열(종류와 정오·맞힌 낱말 수) → 다음 문항 종류(소음 속 문장이면 SNR) 또는 결과. step()
  2. 문항 층: 회기 seed와 지금까지 낸 문항으로 실제 문항(짝·낱말·문장·목소리)을 정하고, 화면이 보낸 날 답을 다시 채점한다. replay()
문항 풀(1차 4.2절): 훈련 문장 13개(일반화 검사 낱말이 글자로 없음, 검사 폼 문장 아님)와 훈련 목소리 m1·f1 번갈아,
소리 구별 수준 4 짝 가운데 피할 목소리가 훈련 목소리 셋 이상인 짝을 뺀 17개, 낱말 수준 3(일반화 검사 낱말·교체 후보를 정답·보기에서 빼고
피할 목소리가 없는 정답만). 검사 목소리(m3)는 쓰지 않는다. 한 회기에서 같은 문장·낱말·짝을 두 번 내지 않는다.
배치검사 답은 숙달·수준·소음 계단·복습에 넣지 않는다(API가 따로 기록한다).
"""
import functools
import math
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

VERSION = "D|g1|m4|s0.95|upper|mode|q0.8"
GAMMA = 1.0
MIN_ITEMS = 4
STOP_S = 0.95
UPPER_RULE = "mode"
LEVEL_RULE = "q0.8"

# ── 채점 모형(사전 등록 값, scripts/listen_placement_model.py와 같다) ──────────
A0, B_LINK = 3.9, 0.175
SIG_U, TAU = 0.7, 0.7
PRIOR_TH = (5.0, 10.0)
LAPSE = 0.02
C_AX = math.log(0.8 / 0.2)
C_WORD = math.log((0.8 - 0.25) / 0.75 / (1 - (0.8 - 0.25) / 0.75))
C_Q = math.log(0.8 / 0.2)
SRT_MASTER = 0.0

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
_EPS = 1e-12
KIND_OF = ["pa", "pw", "pq"] + ["pn"] * len(SNR_CANDS)

# 문장 풀과 목소리 보정(1차 4.2절). 실효 SNR = SNR − VOFF(목소리), 문장 문항마다 m1·f1 번갈아(첫 문장 m1)
SENTENCE_POOL = ("t002", "t003", "t004", "t009", "t011", "t012", "t014", "t023", "t029", "t042", "t076", "t087", "t092")
SENT_VOICES = ("m1", "f1")
VOFF = {"m1": -2.35, "f1": -1.18}
TRAIN_VOICES = ("m1", "f1", "m2", "f2")


def _sig(x):
    return 1.0 / (1.0 + np.exp(-x))


def slope_of(th):
    return np.clip(0.16 - 0.004 * (np.asarray(th, float) + 4.0), 0.05, 0.20)


SLg = slope_of(THg)
P_Q = np.clip((1 - LAPSE) * _sig(Zg), _EPS, 1 - _EPS)
_ZD = Zg[:, None] + DG[None, :]
P_A = np.clip(LAPSE * 0.5 + (1 - LAPSE) * (0.5 + 0.5 * _sig(_ZD)), _EPS, 1 - _EPS)
P_W = np.clip(LAPSE * 0.25 + (1 - LAPSE) * (0.25 + 0.75 * _sig(_ZD)), _EPS, 1 - _EPS)
LP_A, LQ_A = np.log(P_A), np.log1p(-P_A)
LP_W, LQ_W = np.log(P_W), np.log1p(-P_W)
Q_PASS = (Zg >= C_Q).astype(float)
N_PASS = (THg <= SRT_MASTER).astype(float)


def p_noise(x_eff) -> np.ndarray:
    x = np.asarray(x_eff, float)[..., None]
    return np.clip((1 - LAPSE) * _sig(4.0 * SLg * (x - THg)), _EPS, 1 - _EPS)


def binom_pmf(p: np.ndarray, n: int = N_WORDS) -> np.ndarray:
    ks = np.arange(n + 1).reshape((-1,) + (1,) * p.ndim)
    c = np.array([math.comb(n, k) for k in range(n + 1)], float).reshape(ks.shape)
    return c * p[None] ** ks * (1 - p[None]) ** (n - ks)


_PMF_Q = binom_pmf(P_Q)
_PMF_N = np.stack([binom_pmf(p_noise(x)) for x in SNR_CANDS], 0)


def sentence_loglik(k, n, p) -> np.ndarray:
    k = np.asarray(k, float)[:, None]
    n = np.asarray(n, float)[:, None]
    return k * np.log(p) + (n - k) * np.log1p(-p)


def _norm(logw):
    w = np.exp(logw - logw.max(-1, keepdims=True))
    return w / w.sum(-1, keepdims=True)


def _entropy(p):
    p = np.clip(p, 1e-15, 1.0)
    return -(p * np.log(p)).sum(-1)


# ── 후보 D의 수준 모형(2차 1.3절, 3차 2.3절) ───────────────────────────
KAPPA_M = 1.0
PASS_L = [(_ZD >= th).astype(float) for th in [C_AX - KAPPA_M * (4 - lv) for lv in (1, 2, 3)]]     # 소리 구별 수준 1·2·3 숙달
PASS_LW = [(_ZD >= th).astype(float) for th in [C_WORD - KAPPA_M * (3 - lv) for lv in (1, 2)]]    # 낱말 수준 1·2 숙달
U3 = np.stack([1 - Q_PASS, Q_PASS * (1 - N_PASS), Q_PASS * N_PASS], -1)   # (G, 3) 위 단계 T₃ = 3, 4, 5


def _task_multi(n, k, LPm, LQm, passes):
    n = np.asarray(n, float)[:, None, None]
    k = np.asarray(k, float)[:, None, None]
    L = k * LPm[None] + (n - k) * LQm[None]
    m = L.max(-1, keepdims=True)
    e = np.exp(L - m) * PD
    s = e.sum(-1)
    return np.log(s) + m[..., 0], [(e * P[None]).sum(-1) / s for P in passes]


def level_matrix(rs):
    r1, r2, r3 = rs
    return np.clip(np.stack([1 - r1, r1 - r2, r2 - r3, r3], -1), 0.0, 1.0)


def level_matrix3(rs):
    r1, r2 = rs
    return np.clip(np.stack([1 - r1, r1 - r2, r2], -1), 0.0, 1.0)


class _State:
    """한 사람의 충분 통계(시뮬레이션 Batch와 같은 모양, B = 1)."""

    def __init__(self):
        self.ll = np.zeros((1, G))
        self.na = np.zeros(1)
        self.ka = np.zeros(1)
        self.nw = np.zeros(1)
        self.kw = np.zeros(1)

    def post_d(self):
        la, ra = _task_multi(self.na, self.ka, LP_A, LQ_A, PASS_L)
        lw, rw = _task_multi(self.nw, self.kw, LP_W, LQ_W, PASS_LW)
        w = _norm(LOGPRIOR[None] + self.ll + la + lw)
        return w, level_matrix(ra), level_matrix3(rw), la, lw

    def probs_d(self):
        w, V1, V2, _, _ = self.post_d()
        return w @ U3, np.einsum("bg,bgs->bs", w, V1), np.einsum("bg,bgs->bs", w, V2)

    def choose_d(self, gamma, avail):
        w, V1, V2, la, lw = self.post_d()
        E = _entropy
        H0 = E(w @ U3) + E(np.einsum("bg,bgs->bs", w, V1)) + E(np.einsum("bg,bgs->bs", w, V2))
        b = w.shape[0]
        score = np.full((b, len(KIND_OF)), -np.inf)

        def gain_pmf(pmf):
            wk = w[:, None, :] * pmf[None]
            pred = wk.sum(-1)
            d = np.maximum(pred[..., None], 1e-300)
            hu = E((wk @ U3) / d)
            h1 = E(np.einsum("bkg,bgs->bks", wk, V1) / d)
            h2 = E(np.einsum("bkg,bgs->bks", wk, V2) / d)
            return H0 - (pred * (hu + h1 + h2)).sum(-1)

        def gain_task(kind):
            out = 0.0
            for ok in (1.0, 0.0):
                if kind == "pa":
                    l2, r2 = _task_multi(self.na + 1, self.ka + ok, LP_A, LQ_A, PASS_L)
                    w2 = w * np.exp(l2 - la)
                    A1, A2 = level_matrix(r2), V2
                else:
                    l2, r2 = _task_multi(self.nw + 1, self.kw + ok, LP_W, LQ_W, PASS_LW)
                    w2 = w * np.exp(l2 - lw)
                    A1, A2 = V1, level_matrix3(r2)
                pred = w2.sum(-1)
                d = np.maximum(pred[:, None], 1e-300)
                h = E((w2 @ U3) / d) + E(np.einsum("bg,bgs->bs", w2, A1) / d) + E(np.einsum("bg,bgs->bs", w2, A2) / d)
                out = out + pred * h
            return H0 - out

        for ci, name in enumerate(KIND_OF):
            if name == "pa":
                g = gain_task("pa")
            elif name == "pw":
                g = gain_task("pw")
            elif name == "pq":
                g = gain_pmf(_PMF_Q)
            else:
                g = gain_pmf(_PMF_N[ci - 3])
            score[:, ci] = np.where(avail[name], g / (COST[name] ** gamma), -np.inf)
        best = int(score.argmax(-1)[0])
        return KIND_OF[best], (SNR_CANDS[best - 3] if best >= 3 else None)


def decide_n(probs, rule: str) -> int:
    """(S,) → 1..S(mode 또는 P(≥ k) ≥ q인 가장 큰 k). listen_placement3_sim.decide_n과 같다."""
    probs = np.asarray(probs, float)
    S = probs.shape[-1]
    if rule == "mode":
        return int(probs.argmax(-1) + 1)
    q = float(rule[1:])
    tail = np.cumsum(probs[..., ::-1], -1)[..., ::-1]
    return int(np.where(tail >= q - 1e-12, np.arange(1, S + 1), 0).max(-1))


# ── 채점·결정 층 ─────────────────────────────────────────────────────
def _norm_answer(a: Dict) -> Dict:
    kind = a.get("kind")
    if kind in ("pa", "pw"):
        return {"kind": kind, "ok": bool(a["ok"])}
    if kind == "pq":
        return {"kind": kind, "k": int(max(0, min(N_WORDS, int(a["k"]))))}
    if kind == "pn":
        snr = float(a["snr"])
        if snr not in SNR_CANDS:
            raise ValueError("snr must be one of SNR_CANDS")
        return {"kind": kind, "snr": snr, "k": int(max(0, min(N_WORDS, int(a["k"]))))}
    raise ValueError(f"unknown kind {kind!r}")


def state_of(answers: Sequence[Dict]) -> Tuple[_State, float, int]:
    """답 열 → (충분 통계, 걸린 초, 낸 문장 수). 문장 목소리는 낸 차례로 정한다(m1, f1, m1, ...)."""
    st = _State()
    elapsed = 0.0
    n_sent = 0
    for a in answers:
        a = _norm_answer(a)
        kind = a["kind"]
        if kind == "pa":
            st.na += 1
            st.ka += np.asarray([a["ok"]], float)
        elif kind == "pw":
            st.nw += 1
            st.kw += np.asarray([a["ok"]], float)
        else:
            voice = SENT_VOICES[n_sent % 2]
            n_sent += 1
            k = np.array([a["k"]])
            n = np.full(1, N_WORDS)
            if kind == "pq":
                st.ll += sentence_loglik(k, n, P_Q)
            else:
                xe = np.array([a["snr"]]) - np.array([VOFF[voice]])
                st.ll += sentence_loglik(k, n, p_noise(np.asarray(xe, float)))
        elapsed += COST[kind]
    return st, elapsed, n_sent


def probabilities(answers: Sequence[Dict]) -> Dict[str, List[float]]:
    st, _, _ = state_of(answers)
    pu, p1, p2 = st.probs_d()
    return {"upper": pu[0].tolist(), "level1": p1[0].tolist(), "level2": p2[0].tolist()}


def result_of(answers: Sequence[Dict]) -> Dict:
    """지금 답으로 낸 결정. upper: 3~upper단계를 연다(3·4·5), level1: 1단계 시작 수준(1~4), level2: 2단계 시작 수준(1~3)."""
    st, elapsed, _ = state_of(answers)
    pu, p1, p2 = st.probs_d()
    return {"upper": decide_n(pu[0], UPPER_RULE) + 2, "level1": decide_n(p1[0], LEVEL_RULE), "level2": decide_n(p2[0], LEVEL_RULE),
            "items": len(answers), "seconds": elapsed, "version": VERSION,
            "probs": {"upper": [round(float(x), 4) for x in pu[0]], "level1": [round(float(x), 4) for x in p1[0]],
                      "level2": [round(float(x), 4) for x in p2[0]]}}


def step(answers: Sequence[Dict]) -> Dict:
    """답 열 → {"done": False, "kind", "snr"} 또는 {"done": True, "result"}.
    멈춤(시뮬레이션 eval_d와 같음): 4문항 이상이고 위 단계 최대 확률 ≥ 0.95, 16문항, 다음 문항을 내면 300초를 넘거나 문장이 떨어짐."""
    st, elapsed, n_sent = state_of(answers)
    t = len(answers)
    pu, _, _ = st.probs_d()
    if t >= MIN_ITEMS and pu.max(-1)[0] >= STOP_S:
        return {"done": True, "reason": "confident", "result": result_of(answers)}
    if t >= MAX_ITEMS:
        return {"done": True, "reason": "max_items", "result": result_of(answers)}
    rem = MAX_SECONDS - elapsed
    avail = {k: np.array([rem >= COST[k]]) for k in COST}
    for k in ("pq", "pn"):
        avail[k] = avail[k] & np.array([n_sent < len(SENTENCE_POOL)])
    if not any(bool(v[0]) for v in avail.values()):
        return {"done": True, "reason": "time", "result": result_of(answers)}
    kind, snr = st.choose_d(GAMMA, avail)
    return {"done": False, "kind": kind, "snr": snr, "index": t, "elapsed": elapsed}


# ── 문항 층(회기 seed → 실제 문항, 날 답 다시 채점) ─────────────────────
def _rng(seed: str):
    import listen_curriculum as L
    return L._rng(seed)


@functools.lru_cache(maxsize=1)
def pools() -> Dict:
    """배치검사 문항 풀(1차 4.2절). listen_curriculum의 콘텐츠·피할 목소리 표로 만든다."""
    import listen_curriculum as L
    sents = [(sid, L.TRAIN_BY_ID[sid]) for sid in SENTENCE_POOL]
    pairs = [p for p in L.AX_PAIRS if p["level"] == 4
             and len(set(L.avoid_voices_ax(p["a"], p["b"])) & set(TRAIN_VOICES)) < 3]
    wpool = L.word_pool(exclude=set(L.GEN_REPLACE_CANDIDATES))
    nb = L._neighbors(wpool)
    hi, need = L.WORD_LEVELS[3]["hi"], L.WORD_LEVELS[3]["n"] - 1
    targets = [w for w in wpool if sum(1 for d, _ in nb.get(w, []) if d <= hi) >= need and not L.avoid_voices_word(w)]
    return {"sentences": sents, "pairs": pairs, "word_pool": wpool, "word_targets": targets}


def _voice_avoiding(j: int, avoid: Sequence[str]) -> str:
    """m1·f1을 번갈아 쓰되 피할 목소리면 다른 훈련 목소리로."""
    order = [SENT_VOICES[j % 2], SENT_VOICES[(j + 1) % 2], "m2", "f2"]
    return next((v for v in order if v not in set(avoid or ())), order[0])


def make_item(seed: str, kind: str, snr: Optional[float], counts: Dict[str, int]) -> Dict:
    """counts: 지금까지 낸 종류별 수(pa, pw, sent). 같은 회기에서 같은 문장·낱말·짝을 두 번 내지 않는다(seed로 섞은 차례를 앞에서부터)."""
    import listen_curriculum as L
    P = pools()
    if kind == "pa":
        j = counts.get("pa", 0)
        order = list(range(len(P["pairs"])))
        _rng(f"pl:{seed}:pa").shuffle(order)
        same_seq = [True, False] * ((MAX_ITEMS + 1) // 2 + 1)
        _rng(f"pl:{seed}:same").shuffle(same_seq)
        p = P["pairs"][order[j % len(order)]]
        a, b = (p["a"], p["b"]) if _rng(f"pl:{seed}:pa:{j}").random() < 0.5 else (p["b"], p["a"])
        first, second = (a, a) if same_seq[j] else (a, b)
        avoid = L.avoid_voices_ax(p["a"], p["b"])
        return {"kind": "pa", "key": f"pl:pa:{first}|{second}", "first": first, "second": second,
                "kind_label": L.AX_KIND_LABEL[p["kind"]], "voice": _voice_avoiding(j, avoid), "seconds": COST["pa"]}
    if kind == "pw":
        j = counts.get("pw", 0)
        order = list(P["word_targets"])
        _rng(f"pl:{seed}:pw").shuffle(order)
        for target in order[j:] + order[:j]:
            it = L.word_item(target, 3, P["word_pool"], f"pl:{seed}")
            if it:
                return {"kind": "pw", "key": f"pl:pw:{target}", "target": target, "options": it["options"],
                        "voice": SENT_VOICES[j % 2], "seconds": COST["pw"]}
        raise ValueError("no word item")
    j = counts.get("sent", 0)
    order = list(range(len(P["sentences"])))
    _rng(f"pl:{seed}:sent").shuffle(order)
    sid, text = P["sentences"][order[j]]
    voice = SENT_VOICES[j % 2]
    if kind == "pq":
        return {"kind": "pq", "key": f"pl:pq:{sid}", "id": sid, "text": text, "voice": voice, "seconds": COST["pq"]}
    return {"kind": "pn", "key": f"pl:pn:{sid}:{snr:g}", "id": sid, "text": text, "voice": voice, "snr_db": float(snr),
            "noise": "babble", "seconds": COST["pn"]}


def score_raw(item: Dict, raw: Dict) -> Tuple[Dict, Dict]:
    """화면이 보낸 날 답(same·answer)을 서버가 다시 채점한다 → (채점 층 답, 기록용 답)."""
    kind = item["kind"]
    if kind == "pa":
        if raw.get("same") is None:
            raise ValueError("same is required")
        ok = bool(raw["same"]) == (item["first"] == item["second"])
        return {"kind": "pa", "ok": ok}, {"key": item["key"], "same": bool(raw["same"]), "ok": ok}
    ans = (raw.get("answer") or "")[:300]
    if kind == "pw":
        ok = ans == item["target"]
        return {"kind": "pw", "ok": ok}, {"key": item["key"], "answer": ans, "ok": ok}
    import listen_curriculum as L
    fb = L.word_score(item["text"], ans)["feedback"]
    total = fb.get("total_words") or 0
    k = int(fb.get("correct_words") or 0) if total == N_WORDS else int(round((fb.get("correct_words") or 0) / max(1, total) * N_WORDS))
    k = max(0, min(N_WORDS, k))
    core = {"kind": kind, "k": k}
    if kind == "pn":
        core["snr"] = item["snr_db"]
    return core, {"key": item["key"], "answer": ans, "k": k}


def _public(item: Dict) -> Dict:
    return {k: v for k, v in item.items()}


def replay(seed: str, raw_answers: Sequence[Dict]) -> Dict:
    """회기 seed와 지금까지의 날 답 열 → 다음 문항 또는 결과. 답마다 그 자리에서 냈어야 할 문항(item_key)과 같은지 확인한다
    (다르면 ValueError, API는 400). 반환 {"done", "item"?, "result"?, "n", "elapsed", "log"}."""
    core: List[Dict] = []
    log: List[Dict] = []
    counts = {"pa": 0, "pw": 0, "sent": 0}
    for i, raw in enumerate(raw_answers):
        s = step(core)
        if s["done"]:
            raise ValueError(f"answer {i} after the test ended")
        item = make_item(seed, s["kind"], s["snr"], counts)
        if raw.get("item_key") != item["key"]:
            raise ValueError(f"answer {i} does not match the item")
        c, rec = score_raw(item, raw)
        core.append(c)
        log.append(rec)
        counts["sent" if s["kind"] in ("pq", "pn") else s["kind"]] += 1
    s = step(core)
    out = {"done": s["done"], "n": len(core), "log": log}
    if s["done"]:
        out["result"] = s["result"]
        out["reason"] = s["reason"]
    else:
        out["item"] = _public(make_item(seed, s["kind"], s["snr"], counts))
        out["elapsed"] = s["elapsed"]
    out["max_items"], out["max_seconds"] = MAX_ITEMS, MAX_SECONDS
    return out
