"""다자 대화 읽기 보기 누수: 프론트 readOptions 규칙을 재현해, 입을 보지 않는 학습자가
(1) 대화의 다른 턴 문장(이미 보고 답한 줄)을 지우고 (2) 남은 것 중 무작위로 고를 때 정답률을 잰다."""
import random, sys, os
sys.path.insert(0, os.getcwd())
import conversation_scenario as C

def shuffle(a, seed):
    r = random.Random(seed); a = list(a); r.shuffle(a); return a

def read_options(conv):
    out = []
    for i, t in enumerate(conv["turns"]):
        alike = [x for x in (t.get("lookalikes") or []) if x and x != t["text"]]
        others = [u["text"] for u in conv["turns"] if u["text"] and u["text"] != t["text"] and u["text"] not in alike]
        opts = [t["text"]] + alike[:3]
        for o in shuffle(others, conv["seed"] + i):
            if len(opts) >= 4: break
            if o not in opts: opts.append(o)
        out.append(opts)
    return out

tot = hit = alike_turns = 0
for seed in range(300):
    rng = random.Random(seed)
    scene = rng.choice(C._SCENES)
    conv = C._fallback_conversation(rng.choice([2, 3]), 6, scene, rng)
    conv = C.enrich(conv, rng); conv["seed"] = seed
    own = {t["text"] for t in conv["turns"]}
    for t, opts in zip(conv["turns"], read_options(conv)):
        tot += 1
        alike_turns += any(x not in own for x in opts if x != t["text"])
        rem = [o for o in opts if o == t["text"] or o not in own]
        hit += 1 / len(rem)
print(f"turns {tot}  blind elimination accuracy {hit/tot:.3f}  (chance 0.25)  turns with any outside distractor {alike_turns/tot:.3f}")
