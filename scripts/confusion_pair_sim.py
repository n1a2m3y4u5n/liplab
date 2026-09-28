"""2단계 출제: 개인 혼동 짝 겨냥 시뮬레이션(docs/confusion-pair-serving.md 3~4절).

    backend/.venv/bin/python scripts/confusion_pair_sim.py --seed 0 --explore [--out 결과.json]
    backend/.venv/bin/python scripts/confusion_pair_sim.py --seed 1 --det rate --m 3 --e 2 [--kappas 1,1.5,2,3] [--out 결과.json]

A(지금: 약점 입모양 가중 + 일반 보기)와 B(혼동 짝 target 자모 단어 가중 + 대비 단어 보기)를 가상 학습자로 비교한다.
단어 풀·보기·혼동 기록은 실제 백엔드 함수(visual_difficulty, scoring.viseme_confusions, knowledge_tracing)를 쓴다.
--det: count(지정 규칙, 횟수순) · rate(목표 자모 시행 수로 나눈 비율순) · single·single_rate(한 자모만 다른 오답만, 사후 진단)
· oracle(실제 혼동 짝을 안다고 가정, 진단용).
numpy + 순수 파이썬, 시드 고정. 맥에서 조합 하나(학습자 300명 × 480문항)에 약 5~10초. 결과: docs/confusion-pair-serving.md 5절.
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


# ── 혼동 짝 도구: B 출제가 쓰는 규칙(서버 구현 후보였으나 기준 미달로 넣지 않음) ──────────────
JAMO_POS = ("초성", "중성", "종성")   # scoring.viseme_confusions의 position 값
_JAMO_LISTS = (tuple("ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"),
               tuple("ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"),
               ("",) + tuple("ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ"))
CONFUSION_TOP = 3        # 겨냥할 짝 수
CONFUSION_MIN_COUNT = 2  # 이만큼 나온 짝만
CONFUSION_ROWS = 200     # 최근 오답 행 수


def decompose_syllable(ch: str) -> Optional[Tuple[str, str, str]]:
    """한글 음절 → (초성, 중성, 종성). 받침 없으면 종성은 ''. 음절이 아니면 None."""
    if not V._is_syllable(ch):
        return None
    c = ord(ch) - 0xAC00
    return _JAMO_LISTS[0][c // 588], _JAMO_LISTS[1][(c % 588) // 28], _JAMO_LISTS[2][c % 28]


def jamo_slots(word: str) -> List[Tuple[int, str, str]]:
    """단어의 자모 자리 목록 [(음절 번호, 자리 이름, 자모)]. 받침 없는 종성은 넣지 않는다."""
    out = []
    for i, ch in enumerate(V._nfc(word)):
        d = decompose_syllable(ch)
        if d:
            out += [(i, JAMO_POS[j], d[j]) for j in range(3) if d[j]]
    return out


def jamo_viseme(jamo: str, j: int) -> Optional[int]:
    """자모의 입모양 번호(scoring.viseme_confusions와 같은 규칙). 없음(∅)·소리 없는 초성 ㅇ은 None."""
    from engine import DOUBLE_FINAL, VISEME_MAP
    if not jamo or jamo == "∅" or (j == 0 and jamo == "ㅇ"):
        return None
    return VISEME_MAP.get(DOUBLE_FINAL.get(jamo, jamo) if j == 2 else jamo, 15)


def visible_jamo_pair(position: str, target: str, read: str) -> bool:
    """두 자모를 눈으로 가를 수 있나. 입모양이 같거나 둘 다 입 안쪽 무리면 False(same_viseme와 같은 판정).
    기록된 same_viseme는 규칙이 바뀌기 전 값일 수 있어 지금 규칙으로 다시 본다."""
    if position not in JAMO_POS or not target or target == read:
        return False
    j = JAMO_POS.index(position)
    vt, vr = jamo_viseme(target, j), jamo_viseme(read, j)
    if vt == vr:
        return False
    return not (vt in V.INSIDE_CLUSTER and vr in V.INSIDE_CLUSTER)


def confusion_pairs(rows: Iterable, top: int = CONFUSION_TOP, min_count: int = CONFUSION_MIN_COUNT,
                    trial_targets: Optional[Sequence[str]] = None) -> List[Dict]:
    """오답 행들의 confusions(최신순)에서 눈으로 가를 수 있는 (자리, target, read) 짝을 세어 min_count번 이상인 상위 top개.
    기본은 횟수순(같으면 먼저, 즉 최근에 나온 짝이 앞). trial_targets(같은 기간 전체 시행의 정답 단어)를 주면
    횟수 / 그 자리에 target 자모가 든 시행 수(비율)순으로 고른다. 반환: [{position, target, read, count}]"""
    cnt: Dict[Tuple[str, str, str], int] = {}
    for confusions in rows:
        for cf in (confusions or []):
            if not isinstance(cf, dict) or cf.get("same_viseme"):
                continue
            key = (cf.get("position"), cf.get("target"), cf.get("read"))
            if visible_jamo_pair(*key):
                cnt[key] = cnt.get(key, 0) + 1
    order = {k: i for i, k in enumerate(cnt)}
    keys = [k for k, c in cnt.items() if c >= min_count]
    if trial_targets is not None:
        seen: Dict[Tuple[str, str], int] = {}
        for w in trial_targets:
            for pt in {(p, j) for _, p, j in jamo_slots(w or "")}:
                seen[pt] = seen.get(pt, 0) + 1
        rate = {k: cnt[k] / max(1, seen.get(k[:2], 0), cnt[k]) for k in keys}
        best = sorted(keys, key=lambda k: (-rate[k], -cnt[k], order[k]))[:top]
    else:
        best = sorted(keys, key=lambda k: (-cnt[k], order[k]))[:top]
    return [{"position": p, "target": t, "read": r, "count": cnt[(p, t, r)]} for p, t, r in best]


def swap_jamo(word: str, i: int, position: str, read: str) -> Optional[str]:
    """word의 i번째 음절 position 자리를 read 자모로 바꾼 말. 받침 '∅'은 받침을 뺀다. 만들 수 없으면 None."""
    word = V._nfc(word)
    j = JAMO_POS.index(position) if position in JAMO_POS else -1
    d = decompose_syllable(word[i]) if 0 <= i < len(word) else None
    r = "" if read == "∅" else read
    if j < 0 or d is None or r not in _JAMO_LISTS[j] or (j < 2 and not r):
        return None
    parts = list(d)
    parts[j] = r
    code = (_JAMO_LISTS[0].index(parts[0]) * 588 + _JAMO_LISTS[1].index(parts[1]) * 28
            + _JAMO_LISTS[2].index(parts[2]))
    return word[:i] + chr(0xAC00 + code) + word[i + 1:]


def contrast_words(word: str, position: str, target: str, read: str, index: "V.VocabIndex") -> List[str]:
    """대비 단어: word의 target 자모(같은 자리)를 read 자모로 바꾼 실재 단어(index 안). 동구형이음·준동구형은 뺀다."""
    out: List[str] = []
    for i, p, jm in jamo_slots(word):
        if p != position or jm != target:
            continue
        nw = swap_jamo(word, i, position, read)
        if nw and nw != word and nw in index and nw not in out \
                and V.distractor_kind(index._seq_of(word), index._seq_of(nw)) not in ("homophene", "near_homophene"):
            out.append(nw)
    return out


def place_contrast(word: str, distractors: List[str], focus: Sequence[Dict], index: "V.VocabIndex",
                   rng=None, contrast_fn=None) -> List[str]:
    """보기 한 자리를 대비 단어로 둔다. focus 순서대로 word에 대비 단어가 있는 첫 짝을 쓴다. 이미 보기에 있으면 그대로,
    없으면 마지막 자리(숙달 전에는 뚜렷이 다른 단어 자리)를 바꾼다. 대비 단어가 없으면 보기를 바꾸지 않는다."""
    rng = rng or random.Random()
    fn = contrast_fn or (lambda w, p, t, r: contrast_words(w, p, t, r, index))
    for f in focus or ():
        cands = [c for c in fn(word, f["position"], f["target"], f["read"]) if c != word]
        if not cands:
            continue
        if set(cands) & set(distractors):
            return list(distractors)
        out = list(distractors)
        pick = rng.choice(cands)
        if out:
            out[-1] = pick
        else:
            out.append(pick)
        return out
    return list(distractors)


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

    def cmask(self, pos, t, r):
        k = (pos, t, r)
        if k not in self._cmask:
            self._cmask[k] = np.array([bool(self.contrast(w, pos, t, r)) for w in self.words])
        return self._cmask[k]


def candidate_pairs(P):
    """가상 학습자 혼동 짝 후보: 같은 자리, 눈으로 가를 수 있음, target·read 자모가 그 자리에서 풀의 10단어 이상에 나옴
    (받침 없음 ∅은 받침 없는 음절이 있는 단어 수). read 자모가 드물면 4지선다 보기에 거의 안 나와 기록으로 드러날 수 없다."""
    freq = collections.Counter()
    for w in P.words:
        s = {(p, j) for _, p, j in P.slots[w]}
        if any(decompose_syllable(ch) and not decompose_syllable(ch)[2] for ch in w):
            s.add(("종성", "∅"))
        freq.update(s)
    common = {k for k, c in freq.items() if c >= 10}
    out = []
    for (p, t) in common:
        if t == "∅":
            continue
        for (p2, r) in common:
            if p2 == p and r != t and visible_jamo_pair(p, t, r):
                out.append((p, t, r))
    return sorted(out)


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
def run_learner(P, L, cond, kappa, seed, T):
    """cond: {'B': bool, 'm', 'e'}. 반환: 짝 도달 시도 수들, 다른 입모양 도달 시도 수들, 정답 수, 초점 정밀도."""
    rng = random.Random(seed)
    nrng = np.random.default_rng(seed)
    s = dict(L["s"])
    pairs = [dict(p) for p in L["pairs"]]
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
    t = 0
    while t < T:
        recs = [{"viseme_id": v, "error_count": err[v], "total_attempts": att[v],
                 "last_error_at": None} for v in range(1, 11) if att[v]]
        mast = KT.estimate_mastery(recs)
        # 방금 틀린 기록이라 최근 오답 감쇠 최대(× 0.75)
        mast = {v: m * (1 - KT._RECENCY_WEIGHT) if err[v] else m for v, m in mast.items()}
        weak = {v for v, m in mast.items() if m < 0.7}
        focus = []
        if cond.get("det") == "oracle":   # 진단용: 실제 혼동 짝을 안다고 가정(서버는 알 수 없음)
            focus = [{"position": p["pos"], "target": p["t"], "read": p["r"], "count": 2} for p in L["pairs"]]
        elif cond["B"]:
            wrong = [cf for _, cf in rows200 if cf is not None]
            if cond.get("det") in ("single", "single_rate"):   # 사후 진단: 한 자모만 다른 오답만 센다
                wrong = [cf if len(cf) == 1 else [] for cf in wrong]
            if cond.get("det") in ("rate", "single_rate"):
                focus = confusion_pairs(wrong, trial_targets=[x for x, _ in rows200])
            else:
                focus = confusion_pairs(wrong[:200])
        if focus:
            truth = {(p["pos"], p["t"], p["r"]) for p in pairs}
            got = {(f["position"], f["target"], f["read"]) for f in focus}
            prec.append(len(got & truth) / len(got))
            rec.append(len(got & truth) / len(truth))
        pri = lesson_priorities(P, sp_n, weak, focus, cond.get("m", 1), cond.get("e", 1))
        idxs = nrng.choice(P.n, size=LESSON, replace=False, p=pri / pri.sum())
        level = V.option_level(mastered)
        for ii in idxs:
            if t >= T:
                break
            t += 1
            w = P.words[ii]
            dis = V.pick_distractors(w, P.t.index, level, rng, classes=P.t.classes(w))
            if focus:
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
    return {"pair": [x if x is not None else T for x in p_reach],
            "pair_contrast": [bool(P.cmask(p["pos"], p["t"], p["r"]).any()) for p in L["pairs"]],
            "other": [v_reach.get(v, T) for v in others],
            "correct": n_correct, "n": t,
            "prec": st.mean(prec) if prec else None, "rec": st.mean(rec) if rec else None}


def run(P, learners, cond, kappa, seed, T):
    pair, pc, other, corr, n, prec, rec = [], [], [], 0, 0, [], []
    for li, L in enumerate(learners):
        r = run_learner(P, L, cond, kappa, seed * 100003 + li, T)
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
            "focus_recall": round(st.mean(rec), 3) if rec else None}


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
    ap.add_argument("--m", type=float, default=2.0)
    ap.add_argument("--e", type=float, default=1.0)
    ap.add_argument("--det", default="count", choices=("count", "rate", "oracle", "single", "single_rate"))
    ap.add_argument("--kappas", default="1,1.5,2,3")
    ap.add_argument("--out")
    args = ap.parse_args()
    t0 = time.time()
    P = Pool(build_pool())
    learners, cands = make_learners(P, args.n, args.seed)
    res = {"seed": args.seed, "n": args.n, "T": args.T, "pool": P.n, "candidate_pairs": len(cands),
           "candidate_pairs_with_contrast": sum(bool(P.cmask(*c).any()) for c in cands), "rows": []}
    if args.explore:
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
