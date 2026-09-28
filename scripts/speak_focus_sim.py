"""말하기 약한 소리 위주 출제 시뮬레이션: 가상 학습자마다 약한 자모 1~2개를 정하고, 4단계 앞 12문항 가운데 그 소리가 든 단어의
비율을 예전(mixed_order만)과 지금(focus_order 추가)으로 비교한다. 약점 추정은 D-GOP 시도 기록을 흉내 낸다(약한 소리 상대 점수 0.5)."""
import os, random, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))
os.environ.setdefault("LIPLAB_CONTENT_WARMUP", "0")
import jamo_vocab as J
import speak_curriculum as sc

items = sc.get_stage(4)["items"]
jamos = sorted({t.split(":", 1)[-1] for it in items for t in J.text_to_tokens(it["target"])})
rng = random.Random(1)
old = new = recov = 0
N = 400
for u in range(N):
    weak = rng.sample(jamos, rng.choice([1, 2]))
    attempts = []
    for _ in range(15):   # 최근 말하기 시도(단어)
        w = rng.choice(items)["target"]
        attempts.append({"phones": [{"label": t.split(":", 1)[-1],
                                     "dgop": (0.4 if t.split(":", 1)[-1] in weak else 0.8) * rng.uniform(0.85, 1.15)}
                                    for t in J.text_to_tokens(w)]})
    est = sc.weak_sounds(attempts)
    recov += bool(set(est) & set(weak))
    base = sc.mixed_order(items, f"{u}:day")
    focused = sc.focus_order(base, est, lead=3)
    has = lambda it: any(t.split(":", 1)[-1] in weak for t in J.text_to_tokens(it["target"]))
    old += sum(map(has, base[:12])) / 12
    new += sum(map(has, focused[:12])) / 12
print(f"약점 추정 적중 {recov/N:.3f}  앞 12문항 중 약한 소리 단어 비율: 예전 {old/N:.3f} → 지금 {new/N:.3f}")
