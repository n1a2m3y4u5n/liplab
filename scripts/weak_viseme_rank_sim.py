"""약점 입모양 순위 시뮬레이션(/api/statistics·시나리오 표적). kt 방식을 knowledge_tracing.rank_weak로 넣었다(9/27 밤).

    backend/.venv/bin/python scripts/weak_viseme_rank_sim.py [--seed 1]

가상 학습자마다 입모양 1~10의 실제 오답률을 0.05~0.6에서 뽑고, 단어 은행에 나오는 빈도대로 60·150·400번 시도한다.
old(예전): 오류 횟수 상위 5개를 자른 뒤 오답률로 정렬. kt(지금): 지식추적 숙달도(knowledge_tracing.estimate_mastery,
베타 사후평균)가 낮은 순 5개. 가장 약한 입모양이 1위인 비율, 목록에 드는 비율, 약한 3개와 겹치는 수를 잰다.
seed 1 결과: 목록에 드는 비율 old 0.70 → kt 0.90, 약한 3개와 겹치는 수 1.79 → 1.95, 1위 적중 0.38 → 0.38(비슷).
"""
import argparse
import collections
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))

import content_rules as cr  # noqa: E402
import curriculum as C  # noqa: E402
import knowledge_tracing as kt  # noqa: E402


def run(seed, method, reps=3000):
    freq = collections.Counter(v for w in C.WORD_BANK for v in set(cr.word_visemes(w["word"])) if 1 <= v <= 10)
    vs = sorted(freq)
    weights = [freq[v] for v in vs]
    rng = random.Random(seed)
    res = collections.Counter()
    for _ in range(reps):
        true_err = {v: rng.uniform(0.05, 0.6) for v in vs}
        worst = max(vs, key=lambda v: true_err[v])
        worst3 = set(sorted(vs, key=lambda v: -true_err[v])[:3])
        att = collections.Counter(rng.choices(vs, weights=weights, k=rng.choice([60, 150, 400])))
        rec = []
        for v in vs:
            if att[v]:
                rec.append({"viseme_id": v, "error_count": sum(rng.random() < true_err[v] for _ in range(att[v])),
                            "total_attempts": att[v], "last_error_at": None})
        if method == "old":
            top = sorted(rec, key=lambda r: -r["error_count"])[:5]
            rank = [r["viseme_id"] for r in sorted(top, key=lambda r: -r["error_count"] / r["total_attempts"])]
        else:
            m = kt.estimate_mastery(rec)
            rank = sorted(m, key=lambda v: m[v])[:5]
        res["first_is_worst"] += bool(rank) and rank[0] == worst
        res["worst_in_list"] += worst in rank
        res["top3_overlap"] += len(set(rank[:3]) & worst3)
    return {k: round(v / reps, 3) for k, v in res.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    for m in ("old", "kt"):
        print(m, run(a.seed, m))


if __name__ == "__main__":
    main()
