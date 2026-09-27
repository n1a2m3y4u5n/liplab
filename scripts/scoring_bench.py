"""독화 이해 채점 v2 벤치(docs/scoring-v2.md 3~4절).

    backend/.venv/bin/python scripts/scoring_bench.py --tune   # 개발 절반에서 c(우연 공제)·b(우연 보정)를 정한다
    backend/.venv/bin/python scripts/scoring_bench.py --eval   # scoring.VISUAL_CHANCE·VISUAL_BASELINE으로 시험 절반을 잰다

문장은 앱 콘텐츠만 쓴다(AI Hub 자료 없음). 개발/시험은 문장 SHA-1 해시 짝홀로 나누고, 오류 유형은 시드 0으로 만든다.
"""
import argparse
import asyncio
import hashlib
import json
import os
import random
import re
import statistics as st
import sys

START_DIR = os.getcwd()
HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.join(os.path.dirname(HERE), "backend")
sys.path.insert(0, BACKEND)
os.chdir(BACKEND)

import conversation_scenario as cs   # noqa: E402
import curriculum                    # noqa: E402
import llm_service                   # noqa: E402
import scoring                       # noqa: E402
from engine import VISEME_MAP, decompose_hangul   # noqa: E402

CHO = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
JUNG = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"
JONG = [""] + list("ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ")
TYPES = ["E", "H1", "X1", "D1", "D2", "S", "U", "A", "P"]


def compose(i, m, f):
    return chr(0xAC00 + (CHO.index(i) * 21 + JUNG.index(m)) * 28 + JONG.index(f or ""))


def build_pool():
    pool = set()
    for v in llm_service.FALLBACK_TURNS.values():
        pool.update(v)
    pool.update(llm_service.FALLBACK_TURNS_GENERIC)
    ap = json.load(open(os.path.join(BACKEND, "data", "curriculum", "approved.json"), encoding="utf-8"))
    for c in ap.get("closures", []) + list(curriculum.CLOSURE_ITEMS):
        d, a = c.get("display"), c.get("answer")
        if d and a and "___" in d:
            pool.add(d.replace("___", a))
    for name in dir(cs):
        obj = getattr(cs, name)
        if isinstance(obj, dict):
            for v in obj.values():
                if isinstance(v, list):
                    pool.update(x for x in v if isinstance(x, str))
        elif isinstance(obj, list):
            pool.update(x for x in obj if isinstance(x, str))
    out = sorted(s.strip() for s in pool
                 if re.fullmatch(r"[가-힣0-9 ,.?!~]{6,40}", s.strip()) and " " in s.strip())
    return out


def split(pool):
    dev, test = [], []
    for s in pool:
        (dev if int(hashlib.sha1(s.encode()).hexdigest(), 16) % 2 == 0 else test).append(s)
    return dev, test


def _swap_initial(sent, rng, same_group):
    """한 음절의 초성을 같은(same_group=True) 또는 다른 입모양 그룹의 자음으로 바꾼다. 못 바꾸면 None."""
    idx = [k for k, ch in enumerate(sent) if "가" <= ch <= "힣"]
    rng.shuffle(idx)
    for k in idx:
        i, m, f = decompose_hangul(sent[k])
        if not i or i == "ㅇ":
            continue
        g = VISEME_MAP.get(i)
        cands = [c for c in CHO if c not in (i, "ㅇ") and ((VISEME_MAP.get(c) == g) == same_group)]
        if not cands:
            continue
        return sent[:k] + compose(rng.choice(cands), m, f) + sent[k + 1:]
    return None


def make_cases(sents, seed=0):
    rng = random.Random(seed)
    cases = {t: [] for t in TYPES}
    for s in sents:
        w = s.split()
        others = [x for x in sents if x != s]
        cases["E"].append((s, s))
        h = _swap_initial(s, rng, True)
        x = _swap_initial(s, rng, False)
        if h and x:   # H1·X1은 같은 문장에서 둘 다 만들 수 있을 때만(짝지은 비교)
            cases["H1"].append((s, h))
            cases["X1"].append((s, x))
        if len(w) >= 3:
            i = rng.randrange(len(w))
            cases["D1"].append((s, " ".join(w[:i] + w[i + 1:])))
        if len(w) >= 4:
            i, j = sorted(rng.sample(range(len(w)), 2))
            cases["D2"].append((s, " ".join(w[:i] + w[i + 1:j] + w[j + 1:])))
            cases["P"].append((s, " ".join(w[:len(w) // 2])))
        if len(w) >= 2:
            i = rng.randrange(len(w) - 1)
            ww = list(w)
            ww[i], ww[i + 1] = ww[i + 1], ww[i]
            cases["S"].append((s, " ".join(ww)))
        cases["U"].append((s, rng.choice(others)))
        cases["A"].append((s, s + " " + rng.choice(others)))
    return cases


def jamos(text):
    return scoring.to_pronounced_jamos(text.replace(" ", ""))


def score_new(c, u, chance=None, baseline=None):
    return scoring.calculate_visual_score(jamos(c), jamos(u), chance, baseline)["score"]


def score_old(c, u):
    return asyncio.run(scoring.calculate_score(c, u))["score"]


def summarize(xs):
    xs = sorted(xs)
    q = lambda p: xs[int(p * (len(xs) - 1))]   # noqa: E731
    return {"n": len(xs), "mean": round(st.mean(xs), 1), "median": round(q(.5), 1),
            "p10": round(q(.1), 1), "p90": round(q(.9), 1),
            "ge55": round(sum(v >= 55 for v in xs) / len(xs), 3), "ge60": round(sum(v >= 60 for v in xs) / len(xs), 3)}


def tune(dev_cases):
    grid_c = [round(0.05 * k, 2) for k in range(0, 13)]
    grid_b = [round(0.05 * k, 2) for k in range(0, 11)]
    best = None
    for c in grid_c:
        for b in grid_b:
            u = [score_new(x, y, c, b) for x, y in dev_cases["U"]]
            e = [score_new(x, y, c, b) for x, y in dev_cases["E"]]
            if st.median(u) <= 5 and all(v == 100 for v in e):
                key = (round(c + b, 2), c)
                if best is None or key < best[0]:
                    best = (key, c, b, st.median(u))
    return best


def boot_ci(diffs, n=2000, seed=0):
    rng = random.Random(seed)
    ms = sorted(st.mean(rng.choices(diffs, k=len(diffs))) for _ in range(n))
    return ms[int(0.025 * n)], ms[int(0.975 * n)]


def evaluate(test_cases):
    new = {t: [score_new(c, u) for c, u in test_cases[t]] for t in TYPES}
    old = {t: [score_old(c, u) for c, u in test_cases[t]] for t in TYPES}
    s = {t: summarize(new[t]) for t in TYPES if new[t]}
    so = {t: summarize(old[t]) for t in TYPES if old[t]}
    m = {t: s[t]["mean"] for t in s}
    lo, hi = boot_ci([h - x for h, x in zip(new["H1"], new["X1"])])
    gates = {
        "T1 E 모두 100": all(v == 100 for v in new["E"]),
        "T2 U 평균<=10, 55 이상<=1%": m["U"] <= 10 and s["U"]["ge55"] <= 0.01,
        "T3 A 평균<=75, E보다 25 이상 낮음": m["A"] <= 75 and m["E"] - m["A"] >= 25,
        "T4 H1 평균>=90": m["H1"] >= 90,
        "T5 X1 < H1(짝지은 차 95% 구간 하한>0)": lo > 0,
        "T6 D1 60~90, D2<D1, P<D1": 60 <= m["D1"] <= 90 and m["D2"] < m["D1"] and m["P"] < m["D1"],
        "T7 E>H1>X1>D1>D2>U": m["E"] > m["H1"] > m["X1"] > m["D1"] > m["D2"] > m["U"],
    }
    return {"new": s, "old": so, "h1_minus_x1_ci": [round(lo, 2), round(hi, 2)], "gates": gates,
            "chance": scoring.VISUAL_CHANCE, "baseline": scoring.VISUAL_BASELINE}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tune", action="store_true")
    ap.add_argument("--eval", action="store_true")
    ap.add_argument("--out", default=None, help="결과 JSON 경로(--eval)")
    a = ap.parse_args()
    if a.out:
        a.out = os.path.join(START_DIR, a.out) if not os.path.isabs(a.out) else a.out   # 백엔드로 옮기기 전 위치 기준
    pool = build_pool()
    dev, test = split(pool)
    print(f"문장 {len(pool)}개(개발 {len(dev)}, 시험 {len(test)})")
    if a.tune:
        cases = make_cases(dev)
        best = tune(cases)
        print("개발 절반 결정:", {"c": best[1], "b": best[2], "U 중앙값": round(best[3], 1)} if best else "조건을 만족하는 조합 없음")
    if a.eval:
        cases = make_cases(test)
        r = evaluate(cases)
        print(json.dumps(r, ensure_ascii=False, indent=1))
        if a.out:
            with open(a.out, "w", encoding="utf-8") as f:
                json.dump({"pool": len(pool), "dev": len(dev), "test": len(test), **r}, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
