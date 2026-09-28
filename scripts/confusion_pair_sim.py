"""2단계 출제: 개인 혼동 짝 겨냥 시뮬레이션(docs/confusion-pair-serving.md 3~4절, 새 짝 뽑기는 6절).

    backend/.venv/bin/python scripts/confusion_pair_sim.py --seed 0 --explore [--out 결과.json]
    backend/.venv/bin/python scripts/confusion_pair_sim.py --seed 1 --det rate --m 3 --e 2 [--kappas 1,1.5,2,3] [--out 결과.json]
    # 6절: 보기 기록 + 탐색 문항 + 기회로 나눈 혼동률
    backend/.venv/bin/python scripts/confusion_pair_sim.py --seed 0 --explore2 [--out 결과.json]
    backend/.venv/bin/python scripts/confusion_pair_sim.py --seed 1 --det opp --probe top --m 3 --e 2 [--kappas 1,1.5,2,3]

A(지금: 약점 입모양 가중 + 일반 보기)와 B(혼동 짝 target 자모 단어 가중 + 대비 단어 보기)를 가상 학습자로 비교한다.
단어 풀·보기·혼동 기록은 실제 백엔드 함수(visual_difficulty, scoring.viseme_confusions, knowledge_tracing)를 쓴다.
--det: count(지정 규칙, 횟수순) · rate(목표 자모 시행 수로 나눈 비율순) · single·single_rate(한 자모만 다른 오답만, 사후 진단)
· oracle(실제 혼동 짝을 안다고 가정, 진단용) · opp(보기 기록으로 기회로 나눈 혼동률, 6절).
--probe: 레슨 12문항 중 1문항(첫 문항 제외)을 짝 탐색 문항으로. top(후보 짝 첫째, 없으면 무작위) · ucb(상한 신뢰 순서).
6절 비교는 P(지금 앱: 보기 기록 + 탐색 문항)를 기준으로 B(P + 겨냥 출제)를 잰다.
numpy + 순수 파이썬, 시드 고정. 맥에서 조합 하나(학습자 300명 × 480문항)에 약 5~10초. 결과: docs/confusion-pair-serving.md 5절, 7절.
"""
import argparse
import collections
import json
import os
import random
import statistics as st
import sys
import time
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))

import assessment  # noqa: E402
import curriculum  # noqa: E402
import knowledge_tracing as KT  # noqa: E402
import visual_difficulty as V  # noqa: E402
from scoring import viseme_confusions  # noqa: E402

G = 0.25            # 4지선다 우연
ETA = 0.06          # 짝 오독 감소율(짝 문항을 맞힐 때)
ALPHA = 0.03        # 입모양 기능 학습률(맞힐 때, 틀리면 절반)
S_REACH = 0.85      # 입모양 숙달 도달 기준
PAIR_REACH = 0.85   # 짝 정답률(1 - c) 도달 기준
LESSON = 12
KINDS_W = {"minimal_pair": 3.0, "close": 2.0, "distinct": 1.0}


# ── 혼동 짝 도구: 서버와 같은 규칙(backend/confusion_pairs.py) ────────────────────────
from confusion_pairs import (  # noqa: E402
    CONFUSION_ROWS, CONFUSION_TOP, JAMO_POS, OPP_ROWS, OpportunityCounter, PairIndex, confusion_pairs,
    contrast_words, decompose_syllable, jamo_slots, jamo_viseme, place_contrast, trial_pairs, visible_jamo_pair)


# ── 풀과 단어별 정적 정보 ──────────────────────────────────────────────────────
def build_pool():
    skip = set(assessment.test_only_words()) | set(getattr(curriculum, "STAGE2_EXCLUDED", {}))
    pool = tuple(w["word"] for w in curriculum.WORD_BANK if w["word"] not in skip)
    table = V.Stage2Table(pool)
    for w in table.words:
        table.classes(w)
    return table


class Pool:
    def __init__(self, table):
        self.t = table
        self.words = list(table.words)
        self.n = len(self.words)
        self.pos = {w: i for i, w in enumerate(self.words)}
        self.q = np.array([table.quantile[w] for w in self.words])
        self.D = {w: table.score[w] for w in self.words}
        self.vis = {w: sorted({v for v in table.index.seq[w] if 1 <= v <= 10}) for w in self.words}
        self.vmat = np.zeros((self.n, 11), dtype=bool)
        for i, w in enumerate(self.words):
            self.vmat[i, self.vis[w]] = True
        self.minset = {w: set(table.classes(w)["minimal_pair"]) for w in self.words}
        self.kind = {}
        for w in self.words:
            cls = table.classes(w)
            self.kind[w] = {x: k for k in ("minimal_pair", "close", "distinct") for x in cls[k]}
        self.slots = {w: jamo_slots(w) for w in self.words}
        self.pidx = PairIndex(table)
        self._vdiff = {}
        self._tmask = {}
        self._contrast = {}
        self._cmask = {}

    def has_target(self, w, pos, t):
        return any(p == pos and j == t for _, p, j in self.slots[w])

    def tmask(self, pos, t):
        k = (pos, t)
        if k not in self._tmask:
            self._tmask[k] = np.array([self.has_target(w, pos, t) for w in self.words])
        return self._tmask[k]

    def contrast(self, w, pos, t, r):
        k = (w, pos, t, r)
        if k not in self._contrast:
            self._contrast[k] = contrast_words(w, pos, t, r, self.t.index)
        return self._contrast[k]

    def vdiff(self, w, o):
        """정답 w와 보기 o가 갈린 눈으로 가를 수 있는 짝 집합(confusion_pairs.trial_pairs와 같은 규칙)."""
        k = (w, o)
        if k not in self._vdiff:
            self._vdiff[k] = frozenset(trial_pairs(w, None, [o])[0])
        return self._vdiff[k]

    def cmask(self, pos, t, r):
        k = (pos, t, r)
        if k not in self._cmask:
            self._cmask[k] = np.array([bool(self.contrast(w, pos, t, r)) for w in self.words])
        return self._cmask[k]


def candidate_pairs(P):
    """가상 학습자 혼동 짝 후보(= 서버 PairIndex.candidates): 같은 자리, 눈으로 가를 수 있음, target·read 자모가 그 자리에서
    풀의 10단어 이상에 나옴(받침 없음 ∅은 받침 없는 음절이 있는 단어 수). read 자모가 드물면 4지선다 보기에 거의 안 나와
    기록으로 드러날 수 없다."""
    return list(P.pidx.candidates)


def make_learners(P, n, seed):
    rng = random.Random(seed)
    cands = candidate_pairs(P)
    out = []
    for _ in range(n):
        s = {v: rng.uniform(0.35, 0.75) for v in range(1, 11)}
        k = rng.randint(1, 3)
        pairs, used = [], set()
        while len(pairs) < k:
            p, t, r = rng.choice(cands)
            if (p, t) in used:
                continue
            used.add((p, t))
            pairs.append({"pos": p, "t": t, "r": r, "c": rng.uniform(0.4, 0.7)})
        out.append({"s": s, "pairs": pairs})
    return out, cands


# ── 서버 규칙 흉내 ─────────────────────────────────────────────────────────────
def ewma(prev, n, correct, a=0.08):
    raw = prev * (1 - (1 - a) ** n)
    raw += a * ((100.0 if correct else 0.0) - raw)
    return min(100.0, max(0.0, raw / (1 - (1 - a) ** (n + 1))))


def lesson_priorities(P, n_answers, weak, focus, m, e):
    tq = V.next_target_quantile(n_answers)
    pri = 1 + np.round(29 * np.exp(-0.5 * ((P.q - tq) / 0.1) ** 2))
    if weak:
        wm = P.vmat[:, sorted(weak)].any(axis=1)
        pri = np.where(wm, np.maximum(pri + 1, np.round(pri * 1.5)), pri)
    if focus:
        tm = np.zeros(P.n, dtype=bool)
        cm = np.zeros(P.n, dtype=bool)
        for f in focus:
            tm |= P.tmask(f["position"], f["target"])
            cm |= P.cmask(f["position"], f["target"], f["read"])
        pri = np.where(tm, np.maximum(pri + 1, np.round(pri * m)), pri)
        if e > 1:
            pri = np.where(cm, np.maximum(pri + 1, np.round(pri * e)), pri)
    return pri


def read_slot_has(o, slots_ij, r):
    for i, j in slots_ij:
        if i < len(o):
            d = decompose_syllable(o[i])
            if d and (d[j] or "∅") == r:
                return True
    return False


# ── 한 학습자 ─────────────────────────────────────────────────────────────────
def pick_probe_pair(P, policy, opp, opp_focus, rng):
    """탐색 문항 짝. top: 기회로 나눈 혼동률 후보 가운데 대비 단어가 있는 첫 짝, 없으면 탐색 가능한 짝 무작위(서버 probe_items와 같다).
    ucb: 탐색 가능한 짝을 상한 신뢰 순서로(같으면 무작위)."""
    if policy == "top":
        for f in opp_focus:
            key = (f["position"], f["target"], f["read"])
            if P.pidx.contrast.get(key):
                return key, True
        return rng.choice(P.pidx.probe_pairs), False
    pp = list(P.pidx.probe_pairs)
    rng.shuffle(pp)
    return opp.ucb(pp)[0], None


def run_learner(P, L, cond, kappa, seed, T):
    """cond: {'B': bool, 'm', 'e', 'det', 'probe'}. 반환: 짝 도달 시도 수들, 다른 입모양 도달 시도 수들, 정답 수, 초점 정밀도."""
    rng = random.Random(seed)
    nrng = np.random.default_rng(seed)
    s = dict(L["s"])
    pairs = [dict(p) for p in L["pairs"]]
    truth = {(p["pos"], p["t"], p["r"]) for p in pairs}
    involved = set()
    for p in pairs:
        j = JAMO_POS.index(p["pos"])
        for x in (p["t"], p["r"]):
            v = jamo_viseme(x, j)
            if v is not None:
                involved.add(v)
    others = [v for v in range(1, 11) if v not in involved and s[v] < S_REACH]
    v_reach = {}
    p_reach = [None] * len(pairs)
    att = {v: 0 for v in range(1, 11)}
    err = {v: 0 for v in range(1, 11)}
    sp_n, sp_est, mastered = 0, 0.0, False
    rows200 = collections.deque(maxlen=200)   # 최근 시행 (정답 단어, 오답이면 confusions)
    n_correct = 0
    prec, rec = [], []
    # 6절: 보기 기록으로 기회로 나눈 혼동률(서버 confusion_pairs.OpportunityCounter와 같은 규칙), 탐색 문항
    probe_pol = cond.get("probe")
    n_probes = cond.get("probes", 1)              # 레슨당 탐색 문항 수(사전 기준은 1, 2 이상은 사후 진단이며 ucb 순서)
    opp_window = cond.get("opp_rows", OPP_ROWS)   # 기회 창(사전 기준 200, 사후 진단에서 늘려 본다)
    use_opp = cond.get("det") == "opp" or probe_pol is not None
    opp = OpportunityCounter() if use_opp else None
    opp_rows = collections.deque()
    opp_rec_all, opp_prec, opp_rec = [], [], []
    detected = set()
    n_probe = n_probe_true = n_probe_cand = 0
    t = 0
    while t < T:
        recs = [{"viseme_id": v, "error_count": err[v], "total_attempts": att[v],
                 "last_error_at": None} for v in range(1, 11) if att[v]]
        mast = KT.estimate_mastery(recs)
        # 방금 틀린 기록이라 최근 오답 감쇠 최대(× 0.75)
        mast = {v: m * (1 - KT._RECENCY_WEIGHT) if err[v] else m for v, m in mast.items()}
        weak = {v for v, m in mast.items() if m < 0.7}
        opp_focus = opp.top() if opp is not None else []
        if opp is not None:
            got = {(f["position"], f["target"], f["read"]) for f in opp_focus}
            detected |= got & truth
            opp_rec_all.append(len(got & truth) / len(truth))
            if got:
                opp_prec.append(len(got & truth) / len(got))
                opp_rec.append(len(got & truth) / len(truth))
        focus = []
        if cond.get("det") == "oracle":   # 진단용: 실제 혼동 짝을 안다고 가정(서버는 알 수 없음)
            focus = [{"position": p["pos"], "target": p["t"], "read": p["r"], "count": 2} for p in L["pairs"]]
        elif cond["B"] and cond.get("det") == "opp":
            focus = opp_focus
        elif cond["B"]:
            wrong = [cf for _, cf in rows200 if cf is not None]
            if cond.get("det") in ("single", "single_rate"):   # 사후 진단: 한 자모만 다른 오답만 센다
                wrong = [cf if len(cf) == 1 else [] for cf in wrong]
            if cond.get("det") in ("rate", "single_rate"):
                focus = confusion_pairs(wrong, trial_targets=[x for x, _ in rows200])
            else:
                focus = confusion_pairs(wrong[:200])
        if focus:
            got = {(f["position"], f["target"], f["read"]) for f in focus}
            prec.append(len(got & truth) / len(got))
            rec.append(len(got & truth) / len(truth))
        pri = lesson_priorities(P, sp_n, weak, focus, cond.get("m", 1), cond.get("e", 1))
        idxs = nrng.choice(P.n, size=LESSON, replace=False, p=pri / pri.sum())
        level = V.option_level(mastered)
        probe_slot, probe_pair = -1, None
        probe_at = {}   # 사후 진단(--probes 2 이상): 자리 → 짝
        if probe_pol and n_probes > 1:
            order = opp.ucb(rng.sample(P.pidx.probe_pairs, len(P.pidx.probe_pairs)))
            idxs = list(idxs)
            for j, slot in enumerate(rng.sample(range(1, LESSON), min(n_probes, LESSON - 1))):
                pp = order[j]
                used = {P.words[i] for k, i in enumerate(idxs) if k != slot}
                ws = [w for w in P.pidx.contrast[pp] if w not in used]
                if ws:
                    idxs[slot] = P.pos[rng.choices(ws, weights=[float(pri[P.pos[w]]) for w in ws])[0]]
                    probe_at[slot] = pp
                    n_probe += 1
                    n_probe_true += pp in truth
        elif probe_pol:
            probe_pair, from_cand = pick_probe_pair(P, probe_pol, opp, opp_focus, rng)
            probe_slot = rng.randint(1, LESSON - 1)
            lesson_words = {P.words[i] for k, i in enumerate(idxs) if k != probe_slot}
            ws = [w for w in P.pidx.contrast[probe_pair] if w not in lesson_words]
            if ws:
                pw = rng.choices(ws, weights=[float(pri[P.pos[w]]) for w in ws])[0]
                idxs = list(idxs)
                idxs[probe_slot] = P.pos[pw]
                n_probe += 1
                n_probe_true += probe_pair in truth
                n_probe_cand += bool(from_cand)
            else:
                probe_slot = -1
        for si, ii in enumerate(idxs):
            if t >= T:
                break
            t += 1
            w = P.words[ii]
            dis = V.pick_distractors(w, P.t.index, level, rng, classes=P.t.classes(w))
            if si == probe_slot or si in probe_at:
                pp = probe_at.get(si, probe_pair)
                pf = [{"position": pp[0], "target": pp[1], "read": pp[2]}]
                dis = place_contrast(w, dis, pf, P.t.index, rng, contrast_fn=P.contrast)
            elif focus:
                dis = place_contrast(w, dis, focus, P.t.index, rng, contrast_fn=P.contrast)
            # 오독
            here = [k for k, p in enumerate(pairs) if P.has_target(w, p["pos"], p["t"])]
            present = {k: set(P.contrast(w, pairs[k]["pos"], pairs[k]["t"], pairs[k]["r"])) & set(dis) for k in here}
            mis = None
            for k in here:
                if rng.random() < pairs[k]["c"]:
                    mis = k
                    break
            if mis is not None:
                p = pairs[mis]
                if present[mis]:
                    chosen = sorted(present[mis])[0]
                else:
                    j = JAMO_POS.index(p["pos"])
                    ij = [(i, j) for i, pp, jj in P.slots[w] if pp == p["pos"] and jj == p["t"]]
                    same = [o for o in dis if read_slot_has(o, ij, p["r"])]
                    if same and rng.random() < 0.7:
                        chosen = rng.choice(same)
                    elif rng.random() < 0.5:
                        chosen = w
                    else:
                        chosen = rng.choice(dis)
            else:
                S = sum(s[v] for v in P.vis[w]) / max(1, len(P.vis[w]))
                nmin = sum(1 for o in dis if o in P.minset[w])
                pc = G + (1 - G) * S * (1 - 0.3 * P.D[w]) * (1 - 0.08 * nmin)
                if rng.random() < pc:
                    chosen = w
                else:
                    ws = [KINDS_W.get(P.kind[w].get(o, "distinct"), 1.0) for o in dis]
                    chosen = rng.choices(dis, weights=ws)[0]
            correct = chosen == w
            n_correct += correct
            # 학습
            for v in P.vis[w]:
                s[v] += (ALPHA if correct else ALPHA / 2) * (1 - s[v])
                att[v] += 1
                err[v] += 0 if correct else 1
            for k in here:
                p = pairs[k]
                if correct:
                    km = kappa if present[k] else 1.0
                    p["c"] *= 1 - ETA * km
                else:
                    km = kappa if chosen in present[k] else 1.0
                    p["c"] *= 1 - 0.5 * ETA * km
            for k, p in enumerate(pairs):
                if p_reach[k] is None and 1 - p["c"] >= PAIR_REACH:
                    p_reach[k] = t
            for v in others:
                if v not in v_reach and s[v] >= S_REACH:
                    v_reach[v] = t
            # 서버 기록
            sp_est = ewma(sp_est, sp_n, correct)
            sp_n += 1
            if sp_n >= 6 and sp_est >= 85:
                mastered = True
            rows200.appendleft((w, None if correct else viseme_confusions(w, chosen)))
            if opp is not None:   # 보기 기록(TrialAttempt.options) → 최근 OPP_ROWS 시행 창
                o_set = frozenset().union(*(P.vdiff(w, o) for o in dis))
                row = (w, chosen, [w, *dis], (o_set, P.vdiff(w, chosen) if not correct else frozenset()))
                opp.add(row[0], row[1], row[2], row[3])
                opp_rows.append(row)
                if len(opp_rows) > opp_window:
                    old = opp_rows.popleft()
                    opp.remove(old[0], old[1], old[2], old[3])
    return {"pair": [x if x is not None else T for x in p_reach],
            "pair_contrast": [bool(P.cmask(p["pos"], p["t"], p["r"]).any()) for p in L["pairs"]],
            "other": [v_reach.get(v, T) for v in others],
            "correct": n_correct, "n": t,
            "prec": st.mean(prec) if prec else None, "rec": st.mean(rec) if rec else None,
            "opp_prec": st.mean(opp_prec) if opp_prec else None, "opp_rec": st.mean(opp_rec) if opp_rec else None,
            "opp_rec_all": st.mean(opp_rec_all) if opp_rec_all else None,
            "detected": len(detected), "n_true": len(truth),
            "n_probe": n_probe, "n_probe_true": n_probe_true, "n_probe_cand": n_probe_cand}


def run(P, learners, cond, kappa, seed, T):
    pair, pc, other, corr, n, prec, rec = [], [], [], 0, 0, [], []
    oprec, orec, orec_all, det, ntrue, npr, nprt, nprc = [], [], [], 0, 0, 0, 0, 0
    for li, L in enumerate(learners):
        r = run_learner(P, L, cond, kappa, seed * 100003 + li, T)
        if r["opp_rec_all"] is not None:
            orec_all.append(r["opp_rec_all"])
            det += r["detected"]
            ntrue += r["n_true"]
        if r["opp_prec"] is not None:
            oprec.append(r["opp_prec"])
            orec.append(r["opp_rec"])
        npr += r["n_probe"]
        nprt += r["n_probe_true"]
        nprc += r["n_probe_cand"]
        pair += r["pair"]
        pc += r["pair_contrast"]
        other += r["other"]
        corr += r["correct"]
        n += r["n"]
        if r["prec"] is not None:
            prec.append(r["prec"])
            rec.append(r["rec"])
    with_c = [x for x, c in zip(pair, pc) if c]
    no_c = [x for x, c in zip(pair, pc) if not c]
    return {"pair_median": st.median(pair), "pair_mean": round(st.mean(pair), 1),
            "pair_censored": round(sum(x >= T for x in pair) / len(pair), 3),
            "pair_median_with_contrast": st.median(with_c) if with_c else None,
            "pair_median_no_contrast": st.median(no_c) if no_c else None,
            "n_pairs": len(pair), "n_pairs_with_contrast": len(with_c),
            "other_median": st.median(other), "other_mean": round(st.mean(other), 1),
            "accuracy": round(corr / n, 4),
            "focus_precision": round(st.mean(prec), 3) if prec else None,
            "focus_recall": round(st.mean(rec), 3) if rec else None,
            # 6절: 기회로 나눈 혼동률 후보(서빙에 쓰든 안 쓰든 잰다). recall_all은 후보가 빈 레슨을 0으로 넣은 평균
            "opp_precision": round(st.mean(oprec), 3) if oprec else None,
            "opp_recall": round(st.mean(orec), 3) if orec else None,
            "opp_recall_all": round(st.mean(orec_all), 3) if orec_all else None,
            "opp_detected": round(det / ntrue, 3) if ntrue else None,
            "probe_true_share": round(nprt / npr, 3) if npr else None,
            "probe_candidate_share": round(nprc / npr, 3) if npr else None}


def compare(a, b):
    return {"pair_reduction": round(1 - b["pair_median"] / a["pair_median"], 3),
            "other_delay": round(b["other_median"] / a["other_median"] - 1, 3),
            "acc_diff_pp": round(100 * (b["accuracy"] - a["accuracy"]), 2)}


def passes(c):
    return c["pair_reduction"] >= 0.20 and c["other_delay"] <= 0.10 and c["acc_diff_pp"] >= -5.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--n", type=int, default=300)
    ap.add_argument("--T", type=int, default=480)
    ap.add_argument("--explore", action="store_true", help="m·e 여섯 조합을 κ 1.5에서")
    ap.add_argument("--explore2", action="store_true", help="6절 탐색: A, P(top·ucb), B opp m·e 여섯 조합(κ 1.5)")
    ap.add_argument("--probe", default="none", choices=("none", "top", "ucb"))
    ap.add_argument("--probes", type=int, default=1, help="레슨당 탐색 문항 수(사후 진단, 2 이상은 ucb 순서)")
    ap.add_argument("--opp-rows", type=int, default=OPP_ROWS, help="기회 창(사후 진단)")
    ap.add_argument("--m", type=float, default=2.0)
    ap.add_argument("--e", type=float, default=1.0)
    ap.add_argument("--det", default="count", choices=("count", "rate", "oracle", "single", "single_rate", "opp"))
    ap.add_argument("--kappas", default="1,1.5,2,3")
    ap.add_argument("--out")
    args = ap.parse_args()
    t0 = time.time()
    P = Pool(build_pool())
    learners, cands = make_learners(P, args.n, args.seed)
    res = {"seed": args.seed, "n": args.n, "T": args.T, "pool": P.n, "candidate_pairs": len(cands),
           "candidate_pairs_with_contrast": sum(bool(P.cmask(*c).any()) for c in cands), "rows": []}
    probe = None if args.probe == "none" else args.probe
    if args.explore2:
        kappa = 1.5
        a = run(P, learners, {"B": False}, kappa, args.seed, args.T)
        res["rows"].append({"cond": "A", "kappa": kappa, **a})
        print(f"A: {a}  ({time.time() - t0:.0f}s)", flush=True)
        lg = run(P, learners, {"B": False, "det": "opp"}, kappa, args.seed, args.T)   # 보기 기록만(탐색 문항 없음)
        res["rows"].append({"cond": "L", "kappa": kappa, **lg})
        print(f"L: {lg}  ({time.time() - t0:.0f}s)", flush=True)
        base = {}
        for pol in ("top", "ucb"):
            b = run(P, learners, {"B": False, "probe": pol}, kappa, args.seed, args.T)
            base[pol] = b
            c = compare(a, b)
            res["rows"].append({"cond": f"P {pol}", "kappa": kappa, **b, **{f"vsA_{k}": v for k, v in c.items()}})
            print(f"P {pol}: {b} vsA {c}  ({time.time() - t0:.0f}s)", flush=True)
        # 사전 기준(6.3): 기회로 나눈 후보의 재현율(opp_recall_all)이 높은 탐색 정책 하나로 B를 잰다. 같으면 top(지정 규칙)
        pol = "ucb" if base["ucb"]["opp_recall_all"] > base["top"]["opp_recall_all"] else "top"
        res["probe_policy"] = pol
        for m in (1.5, 2.0, 3.0):
            for e in (1.0, 2.0):
                b = run(P, learners, {"B": True, "m": m, "e": e, "det": "opp", "probe": pol}, kappa, args.seed, args.T)
                c = compare(base[pol], b)
                ca = compare(a, b)
                name = f"B opp {pol} m={m} e={e}"
                res["rows"].append({"cond": name, "kappa": kappa, **b, **c, "pass": passes(c),
                                    **{f"vsA_{k}": v for k, v in ca.items()}})
                print(f"{name}: {b} vsP {c} pass={passes(c)} vsA {ca}  ({time.time() - t0:.0f}s)", flush=True)
        o = run(P, learners, {"B": True, "m": 3.0, "e": 2.0, "det": "oracle", "probe": pol}, kappa, args.seed, args.T)
        c = compare(base[pol], o)
        res["rows"].append({"cond": f"O oracle {pol} m=3.0 e=2.0", "kappa": kappa, **o, **c})
        print(f"oracle: {o} vsP {c}  ({time.time() - t0:.0f}s)", flush=True)
    elif args.det == "opp" or probe:
        for kappa in [float(x) for x in args.kappas.split(",")]:
            a = run(P, learners, {"B": False}, kappa, args.seed, args.T)
            extra = {"probes": args.probes, "opp_rows": args.opp_rows}
            base = run(P, learners, {"B": False, "probe": probe, **extra}, kappa, args.seed, args.T)
            b = run(P, learners, {"B": True, "m": args.m, "e": args.e, "det": args.det, "probe": probe, **extra},
                    kappa, args.seed, args.T)
            c = compare(base, b)
            ca = compare(a, b)
            res["rows"].append({"cond": "A", "kappa": kappa, **a})
            res["rows"].append({"cond": f"P {probe} probes={args.probes} rows={args.opp_rows}", "kappa": kappa, **base})
            res["rows"].append({"cond": f"B {args.det} {probe} m={args.m} e={args.e}", "kappa": kappa, **b, **c,
                                "pass": passes(c), **{f"vsA_{k}": v for k, v in ca.items()}})
            print(f"κ={kappa} A: {a}\n        P: {base}\n        B: {b} vsP {c} pass={passes(c)} vsA {ca}"
                  f"  ({time.time() - t0:.0f}s)", flush=True)
    elif args.explore:
        kappa = 1.5
        a = run(P, learners, {"B": False}, kappa, args.seed, args.T)
        res["rows"].append({"cond": "A", "kappa": kappa, **a})
        print(f"A κ={kappa}: {a}  ({time.time() - t0:.0f}s)", flush=True)
        for det in ("count", "rate"):
            for m in (1.5, 2.0, 3.0):
                for e in (1.0, 2.0):
                    b = run(P, learners, {"B": True, "m": m, "e": e, "det": det}, kappa, args.seed, args.T)
                    c = compare(a, b)
                    name = f"B {det} m={m} e={e}"
                    res["rows"].append({"cond": name, "kappa": kappa, **b, **c, "pass": passes(c)})
                    print(f"{name}: {b} {c} pass={passes(c)}  ({time.time() - t0:.0f}s)", flush=True)
    else:
        for kappa in [float(x) for x in args.kappas.split(",")]:
            a = run(P, learners, {"B": False}, kappa, args.seed, args.T)
            b = run(P, learners, {"B": True, "m": args.m, "e": args.e, "det": args.det}, kappa, args.seed, args.T)
            c = compare(a, b)
            res["rows"].append({"cond": "A", "kappa": kappa, **a})
            res["rows"].append({"cond": f"B {args.det} m={args.m} e={args.e}", "kappa": kappa, **b, **c, "pass": passes(c)})
            print(f"κ={kappa} A: {a}\n        B: {b} {c} pass={passes(c)}  ({time.time() - t0:.0f}s)", flush=True)
    res["seconds"] = round(time.time() - t0, 1)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
