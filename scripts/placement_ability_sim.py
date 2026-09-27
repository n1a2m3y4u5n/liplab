"""배치검사 능력 추정 시뮬레이션(docs/assessment-design.md 10절).

    backend/.venv/bin/python scripts/placement_ability_sim.py --seed 0 [--est max,eap:10:0.25] [--out 결과.json]

지금 score_placement는 '맞힌 문항 중 최고 난이도'를 능력으로 쓰고, 수준 = int(능력 × 4) + 1, 시작 단계는 수준 1 입모양·2~3 단어·
4~5 문장이다. 4지선다라 우연 정답(25%)이 있어 어려운 문항 하나를 찍어 맞히면 수준이 높게 잡히고, '…부터 시작하기'는 그 단계로
바로 배치한다(앞 단계를 건너뜀).

가상 학습자 θ ~ U(0.15, 0.95), 실제 수준·단계는 θ로 같은 규칙을 적용한 값. 정답 확률 P = c + (1 − c)·σ(a·(θ − d')),
c = 0.25, d' = d + N(0, sd)(난이도 지수가 완벽하지 않음). 생성 조합: a ∈ {6, 10, 16} × sd ∈ {0, 0.08}.
검사: (1) 동형 폼 A 24문항(실제 난이도), (2) 적응형 8문항(assessment.estimate_ability 경계에 가장 가까운 난이도, 풀은 서비스
단어의 난이도 지수).
추정기: max(지금) 또는 eap:<기울기>:<사전 SD>(사전 N(0.55, SD)를 [0, 1]에 자른 사후 평균, 우연 1/보기 수).
지표: 시작 단계 일치율, 과배치(추천 단계 > 실제), 심한 과배치(실제 입모양·단어인데 문장 추천), 과소배치(추천 < 실제), |수준 차|.
"""
import argparse
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))
os.environ.setdefault("LIPLAB_CONTENT_WARMUP", "0")

import assessment as A  # noqa: E402

GRID = np.linspace(0.0, 1.0, 201)
GEN = [(a, sd) for a in (6.0, 10.0, 16.0) for sd in (0.0, 0.08)]


def level_of(theta):
    return int(min(5, max(1, int(theta * 4) + 1)))


def stage_of(level):
    return 1 if level <= 1 else (2 if level <= 3 else 3)


def est_max(items):
    solved = [d for d, ok, _ in items if ok]
    return max(solved) if solved else 0.0


def est_eap(items, slope, prior_sd, prior_m=0.55):
    logp = -((GRID - prior_m) ** 2) / (2 * prior_sd ** 2)
    for d, ok, k in items:
        c = 1.0 / k
        p = c + (1 - c) / (1 + np.exp(-slope * (GRID - d)))
        logp = logp + np.log(p if ok else 1 - p)
    w = np.exp(logp - logp.max())
    return float((GRID * w).sum() / w.sum())


def estimator(spec):
    if spec == "max":
        return est_max
    _, slope, sd = spec.split(":")
    return lambda items: est_eap(items, float(slope), float(sd))


def pool_difficulties():
    import content_rules as cr
    import curriculum as C
    import perceptual as P
    words = [w["word"] for w in C.WORD_BANK]
    skip = set(A.test_only_words()) | set(getattr(C, "STAGE2_EXCLUDED", {}))
    words = [w for w in dict.fromkeys(words) if w not in skip and cr.is_hangul_word(w)]
    from collections import Counter
    sig = Counter(cr.viseme_signature(w) for w in words)
    return [e["difficulty"] for e in (P.word_difficulty(w, sig) for w in words) if e]


def run(seed, specs, n_learners=6000):
    forms = A.frozen_forms(build_if_missing=False)
    form_d = [it["difficulty"] for it in forms["A"]]
    pool = pool_difficulties()
    ests = {s: estimator(s) for s in specs}
    out = {"seed": seed, "n": n_learners, "results": []}
    for gi, (a, sd) in enumerate(GEN):
        rng = np.random.default_rng([seed, gi])
        for test in ("form", "adaptive"):
            acc = {s: {"agree": 0, "over": 0, "severe_over": 0, "under": 0, "abs_level": 0.0} for s in specs}
            for _ in range(n_learners):
                theta = rng.uniform(0.15, 0.95)
                lv, st = level_of(theta), stage_of(level_of(theta))
                if test == "form":
                    ds = form_d
                    items = []
                    for d in ds:
                        p = 0.25 + 0.75 / (1 + np.exp(-a * (theta - (d + rng.normal(0, sd) if sd else d))))
                        items.append((d, bool(rng.random() < p), 4))
                else:
                    asked, responses, items = [], {}, []
                    avail = list(pool)
                    for q in range(8):
                        th = A.estimate_ability(asked, responses)["ability"]
                        j = min(range(len(avail)), key=lambda i: (abs(avail[i] - th), rng.random()))
                        d = avail.pop(j)
                        p = 0.25 + 0.75 / (1 + np.exp(-a * (theta - (d + rng.normal(0, sd) if sd else d))))
                        ok = bool(rng.random() < p)
                        iid = f"q{q}"
                        asked.append({"id": iid, "word": "정답", "difficulty": d, "visemes": []})
                        responses[iid] = "정답" if ok else "오답"
                        items.append((d, ok, 4))
                for s, f in ests.items():
                    lv_hat = level_of(f(items))
                    st_hat = stage_of(lv_hat)
                    r = acc[s]
                    r["agree"] += st_hat == st
                    r["over"] += st_hat > st
                    r["severe_over"] += st_hat == 3 and st <= 2 and lv <= 2
                    r["under"] += st_hat < st
                    r["abs_level"] += abs(lv_hat - lv)
            for s in specs:
                r = acc[s]
                out["results"].append({"gen_slope": a, "gen_sd": sd, "test": test, "est": s,
                                       **{k: round(v / n_learners, 4) for k, v in r.items()}})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--est", default="max,eap:10:0.25")
    ap.add_argument("--n", type=int, default=6000)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    res = run(a.seed, a.est.split(","), a.n)
    txt = json.dumps(res, ensure_ascii=False, indent=1)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(txt + "\n")
    # 요약: 추정기·검사별 평균
    from collections import defaultdict
    agg = defaultdict(list)
    for r in res["results"]:
        agg[(r["est"], r["test"])].append(r)
    for (e, t), rs in sorted(agg.items()):
        m = {k: round(sum(x[k] for x in rs) / len(rs), 4) for k in ("agree", "over", "severe_over", "under", "abs_level")}
        print(e, t, m)


if __name__ == "__main__":
    main()
