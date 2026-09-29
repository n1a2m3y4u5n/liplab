"""약점 입모양 순위 시뮬레이션: 단어 단위 생성 모형(docs/weak-viseme-ranking.md 2~4절, 기준은 돌리기 전에 적었다).

    backend/.venv/bin/python scripts/weak_viseme_rank_sim.py --seed 0 [--reps 3000] [--no-recognition] [--json out.json]
    backend/.venv/bin/python scripts/weak_viseme_rank_sim.py --independent --seed 1

가상 학습자마다 입모양 1~10의 개인 결손 w를 뽑고, 모집단 바닥(누구나 못 읽는 몫, 입 안쪽 무리가 크다)을 더해 한 번 볼 때 못 읽을
확률 p를 만든다. 1단계 인지 30번과 2단계 단어 문항(보기 4개, 실제 보기 고르기 규칙)을 풀게 한다. 단어 문항은 정답과 다른 자리의
입모양을 하나라도 읽으면 그 보기를 지우고, 남은 것 가운데 하나를 고른다. 기록은 앱처럼 한다.
  R0(지금): 틀리면 정답 단어의 모든 입모양에 오류 1
  R1(오답 배분): 틀리면 고른 답과 입모양이 다른 자리(viseme_confusions)의 정답 쪽 입모양에만 오류 1
순위는 K0(지금 rank_weak, 숙달도 순), Kc(가시성 등급 사전 대비 초과 오답), Kp(모집단 합산 사전 대비 초과 오답).
정답은 w가 가장 큰 입모양(또래보다 더 못 읽는 입모양)이다. 예전 판(입모양마다 따로 관찰)은 이 번짐을 재지 못했다.
결과(9/29): 기준(적중 +10점, 겹침 유지)을 시드 0에서 넘은 후보는 R1+Kp 하나(+10.8점)였고 시드 1에서 +9.5점으로 못 넘어
앱은 바꾸지 않았다(docs/weak-viseme-ranking.md 5절). 후보 규칙(credit_errors, rank_adjusted)은 이 파일에만 있다.
예전 판(입모양마다 따로 관찰, kt 순위 도입 근거)은 --independent로 그대로 돌린다(old 0.70 → kt 0.90, seed 1).
"""
import argparse
import collections
import json
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))

import assessment as asmt  # noqa: E402
import content_rules as cr  # noqa: E402
import curriculum as C  # noqa: E402
import knowledge_tracing as kt  # noqa: E402
import visual_difficulty as vd  # noqa: E402
from scoring import viseme_confusions  # noqa: E402

VIS = list(range(1, 11))
CLASS = {v: vd.VISIBILITY_CLASS[v] for v in VIS}
INSIDE = set(vd.INSIDE_CLUSTER)
FLOOR_NOM = {"high": 0.05, "medium": 0.15, "low": 0.60}
W_MAX = 0.5
# Kc 사전: 등급 명목 바닥 f에 평균 결손 0.25를 얹은 값(사전 기준 2절)
PRIOR_CLASS = {c: round(f + (1 - f) * W_MAX / 2, 2) for c, f in FLOOR_NOM.items()}
N_REC = 30
N_WORDS = (60, 150, 400)
LEVEL2_TRIALS = 40
N_OPTSETS = 8
N_REF = 500


def _align_tokens(s, t):
    """정답 s와 보기 t를 최소 비용으로 맞춘 뒤 다른 자리의 입모양(치환은 정답 쪽, 삭제는 정답 쪽, 삽입은 보기 쪽)."""
    n, m = len(s), len(t)
    D = [[0.0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        D[i][0] = float(i)
    for j in range(m + 1):
        D[0][j] = float(j)
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            x, y = s[i - 1], t[j - 1]
            sub = 0.0 if x == y else (0.5 if (x in INSIDE and y in INSIDE) else 1.0)
            D[i][j] = min(D[i - 1][j] + 1, D[i][j - 1] + 1, D[i - 1][j - 1] + sub)
    out, i, j = [], n, m
    while i > 0 or j > 0:
        if i > 0 and j > 0:
            x, y = s[i - 1], t[j - 1]
            sub = 0.0 if x == y else (0.5 if (x in INSIDE and y in INSIDE) else 1.0)
            if D[i][j] == D[i - 1][j - 1] + sub:
                if x != y:
                    out.append(x)
                i, j = i - 1, j - 1
                continue
        if i > 0 and D[i][j] == D[i - 1][j] + 1:
            out.append(s[i - 1])
            i -= 1
        else:
            out.append(t[j - 1])
            j -= 1
    return out


def credit_errors(target, chosen, vids):
    """R1 기록 규칙: 오답에서 오류를 줄 입모양. 고른 답과 입모양이 다른 자리(same_viseme 거짓)의 정답 쪽 입모양 가운데
    정답 단어의 입모양(vids)에 드는 것. 그런 자리가 없으면 다른 자리 전부, 그것도 없으면 vids 전부(R0과 같다)."""
    vs = {v for v in vids if 1 <= v <= 10}
    cfs = viseme_confusions(target, chosen)
    for keep in (lambda c: not c.get("same_viseme"), lambda c: True):
        out = sorted({c.get("viseme") for c in cfs if keep(c) and c.get("viseme") in vs})
        if out:
            return out
    return sorted(vs)


def rank_adjusted(records, prior, k=3):
    """Kc·Kp 순위: 관찰 오답률을 기대 오답률 prior 쪽으로 줄인 ê = (오류 + 2ē) / (시도 + 2)에서 초과 오답
    s = (ê − ē) / (1 − ē)가 큰 순 k개(동점은 번호 순). 최근 오답 감쇠는 시뮬레이션에서 쓰지 않아 뺐다."""
    score = {}
    for r in records:
        v, e, n = r["viseme_id"], r["error_count"], r["total_attempts"]
        if v in kt.TEACHABLE_VISEMES and n > 0:
            pe = min(max(prior.get(v, 0.5), 0.0), 0.99)
            score[v] = ((e + 2 * pe) / (n + 2) - pe) / (1 - pe)
    return sorted(score, key=lambda v: (-score[v], v))[:k]


class World:
    """단어 풀·보기 묶음·짝별 지각 토큰과 오답 배분 집합(시드마다 한 번)."""

    def __init__(self, seed):
        tw = asmt.test_only_words()
        ex = getattr(C, "STAGE2_EXCLUDED", {})
        pool = [w["word"] for w in C.WORD_BANK if w["word"] not in tw and w["word"] not in ex]
        table = vd.Stage2Table(pool)
        rng = random.Random(1000 + seed)
        self.words = table.words
        self.seq = {w: table.index.seq[w] for w in self.words}
        self.vids = {w: sorted({v for v in cr.word_visemes(w) if 1 <= v <= 10}) for w in self.words}
        self.optsets = {lv: {w: [vd.pick_distractors(w, table.index, lv, rng, classes=table.classes(w))
                                 for _ in range(N_OPTSETS)] for w in self.words} for lv in (2, 3)}
        self.tokens, self.credit = {}, {}
        for lv in (2, 3):
            for w in self.words:
                for ds in self.optsets[lv][w]:
                    for d in ds:
                        if (w, d) not in self.tokens:
                            self.tokens[(w, d)] = [v for v in _align_tokens(self.seq[w], self.seq[d]) if 1 <= v <= 10]
                            self.credit[(w, d)] = credit_errors(w, d, self.vids[w])


def floors(seed):
    rng = random.Random(2000 + seed)
    return {v: FLOOR_NOM[CLASS[v]] * rng.uniform(0.7, 1.3) for v in VIS}


def simulate(world, f, rng, n_rec=N_REC):
    """학습자 한 명: (w, R0 기록, R1 기록). 기록은 {viseme: [오류, 시도]}."""
    w = {v: rng.uniform(0, W_MAX) for v in VIS}
    p = {v: f[v] + (1 - f[v]) * w[v] for v in VIS}
    r0 = {v: [0, 0] for v in VIS}
    r1 = {v: [0, 0] for v in VIS}
    for _ in range(n_rec):
        v = rng.choice(VIS)
        e = rng.random() < p[v]
        for r in (r0, r1):
            r[v][1] += 1
            r[v][0] += e
    for t in range(rng.choice(N_WORDS)):
        lv = 2 if t < LEVEL2_TRIALS else 3
        word = rng.choice(world.words)
        ds = rng.choice(world.optsets[lv][word])
        alive = [d for d in ds if not any(rng.random() >= p[v] for v in world.tokens[(word, d)])]
        pick = rng.randrange(len(alive) + 1)
        vids = world.vids[word]
        for v in vids:
            r0[v][1] += 1
            r1[v][1] += 1
        if pick < len(alive):
            chosen = alive[pick]
            for v in vids:
                r0[v][0] += 1
            for v in world.credit[(word, chosen)]:
                r1[v][0] += 1
    return w, p, r0, r1


def _records(r):
    return [{"viseme_id": v, "error_count": e, "total_attempts": n, "last_error_at": None}
            for v, (e, n) in r.items() if n > 0]


def rank(method, r, prior=None):
    if method == "K0":
        return [x["viseme_id"] for x in kt.rank_weak(_records(r), k=3)]
    return rank_adjusted(_records(r), prior, k=3)


def run(seed, reps=3000, n_rec=N_REC):
    world = World(seed)
    f = floors(seed)
    # 모집단 사전(Kp): 따로 뽑은 학습자 500명의 합산 오답률, 기록 방식별
    ref = random.Random(3000 + seed)
    pool = {"R0": collections.Counter(), "R1": collections.Counter()}
    for _ in range(N_REF):
        _, _, r0, r1 = simulate(world, f, ref, n_rec)
        for name, r in (("R0", r0), ("R1", r1)):
            for v, (e, n) in r.items():
                pool[name][(v, "e")] += e
                pool[name][(v, "n")] += n
    prior_pop = {name: {v: c[(v, "e")] / c[(v, "n")] for v in VIS if c[(v, "n")]} for name, c in pool.items()}
    prior_cls = {v: PRIOR_CLASS[CLASS[v]] for v in VIS}
    combos = [("R0+K0", "R0", "K0", None), ("R0+Kc", "R0", "Kc", prior_cls), ("R0+Kp", "R0", "Kp", prior_pop["R0"]),
              ("R1+K0", "R1", "K0", None), ("R1+Kc", "R1", "Kc", prior_cls), ("R1+Kp", "R1", "Kp", prior_pop["R1"])]
    res = {c[0]: collections.Counter() for c in combos}
    rng = random.Random(seed)
    for _ in range(reps):
        w, p, r0, r1 = simulate(world, f, rng, n_rec)
        worst = max(VIS, key=lambda v: (w[v], -v))
        worst3 = set(sorted(VIS, key=lambda v: -w[v])[:3])
        raw_worst = max(VIS, key=lambda v: (p[v], -v))
        for name, rec, method, prior in combos:
            top = rank(method, r0 if rec == "R0" else r1, prior)
            c = res[name]
            c["hit3"] += worst in top
            c["overlap"] += len(set(top) & worst3)
            n_in = sum(v in INSIDE for v in top)
            c["crowd"] += n_in
            c["all_inside"] += n_in == 3 and len(top) == 3
            c["first_is_worst"] += bool(top) and top[0] == worst
            c["hit3_raw"] += raw_worst in top
    out = {name: {k: round(c[k] / reps, 3) for k in ("hit3", "overlap", "crowd", "all_inside", "first_is_worst", "hit3_raw")}
           for name, c in res.items()}
    base = out["R0+K0"]
    for name, m in out.items():
        m["d_hit3"] = round(m["hit3"] - base["hit3"], 3)
        m["d_overlap"] = round(m["overlap"] - base["overlap"], 3)
        m["pass"] = m["d_hit3"] >= 0.10 and m["d_overlap"] >= 0 and name != "R0+K0"
    return {"seed": seed, "reps": reps, "n_recognition": n_rec, "n_words": len(world.words),
            "floors": {v: round(f[v], 3) for v in VIS}, "prior_class": prior_cls,
            "prior_pop": {k: {v: round(x, 3) for v, x in d.items()} for k, d in prior_pop.items()}, "results": out}


def run_independent(seed, method, reps=3000):
    """예전 판(9/27 밤): 입모양마다 따로 관찰. 실제 오답률 U(0.05, 0.6), 단어 은행 빈도대로 60·150·400번.
    old(오류 횟수 상위 5개를 오답률로 정렬)와 kt(지금 rank_weak, 숙달도 순 5개)를 비교했다."""
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
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--reps", type=int, default=3000)
    ap.add_argument("--no-recognition", action="store_true")
    ap.add_argument("--independent", action="store_true", help="예전 판(입모양마다 따로 관찰)")
    ap.add_argument("--json")
    a = ap.parse_args()
    if a.independent:
        for m in ("old", "kt"):
            print(m, run_independent(a.seed, m, a.reps))
        return
    out = run(a.seed, a.reps, 0 if a.no_recognition else N_REC)
    for name, m in out["results"].items():
        print(f"{name:7s}", m)
    if a.json:
        with open(a.json, "w", encoding="utf-8") as fh:
            json.dump(out, fh, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
