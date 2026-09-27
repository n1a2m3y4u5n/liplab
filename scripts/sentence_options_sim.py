"""3단계 문장 4지선다 보기의 누출 시뮬레이션(backend/sentence_options.py 머리말).

    backend/.venv/bin/python scripts/sentence_options_sim.py [--seed 0]

1) 레슨 안 누출: 문항 유형(주관식·4지선다·서술형)을 앱처럼 섞었을 때, 주관식·서술형 문항의 문장이 앞선 4지선다의 보기로
   이미 보인 비율. 예전 보기(같은 레슨의 다른 문장 3개)만 해당하고 새 보기(레슨 밖)는 0이다.
2) 길이 단서: 아바타 재생 길이로 음절 수를 어림하는(잡음 SD 10·15·25%) 관찰자가 보기 가운데 음절 수가 가장 가까운 것을
   고를 때의 정답률(우연 25%). 레슨은 단계별 대체 문장과 상황 기본 문장 묶음이고, 새 보기의 풀은 코드의 문장만 쓴다
   (배포에서는 캐시된 LLM 문장이 더해져 풀이 더 크다).
"""
import argparse
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))
os.environ.setdefault("LIPLAB_CONTENT_WARMUP", "0")

import llm_service as L  # noqa: E402
import sentence_options as S  # noqa: E402

QT = ["test", "test-multiple", "essay"]


def leak(n, rng, reps=20000):
    leaked = total = 0
    for _ in range(reps):
        types = [QT[i % 3] for i in range(n)]
        rng.shuffle(types)
        shown = set()
        for i, t in enumerate(types):
            if t != "test-multiple":
                total += 1
                leaked += i in shown
            else:
                others = [j for j in range(n) if j != i]
                rng.shuffle(others)
                shown.update(others[:3])
    return round(leaked / total, 3)


def length_observer(lessons, pool, noise, new, rng, reps=4000):
    hit = 0
    for _ in range(reps):
        les = rng.choice(lessons)
        i = rng.randrange(len(les))
        target = les[i]
        if new:
            opts = S.pick_options(target, pool, les, rng=rng)
        else:
            opts = rng.sample([s for j, s in enumerate(les) if j != i], 3)
        opts = opts + [target]
        est = S.syllables(target) * (1 + rng.gauss(0, noise))
        best = min(opts, key=lambda o: (abs(S.syllables(o) - est), rng.random()))
        hit += best == target
    return round(hit / reps, 3)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    rng = random.Random(a.seed)
    print("레슨 안 누출(예전 보기): " + ", ".join(f"문장 {n}개 {leak(n, rng)}" for n in (5, 6, 8, 10)))
    lessons = list(L.FALLBACK_BY_LEVEL.values()) + list(L._SITUATION_DEFAULTS.values())
    pool = S.static_pool()
    print(f"풀(코드 문장) {len(pool)}개")
    for noise in (0.10, 0.15, 0.25):
        print(f"길이만 보는 관찰자(잡음 {noise}): 예전 {length_observer(lessons, pool, noise, False, rng)}, "
              f"새 보기 {length_observer(lessons, pool, noise, True, rng)}, 우연 0.25")


if __name__ == "__main__":
    main()
