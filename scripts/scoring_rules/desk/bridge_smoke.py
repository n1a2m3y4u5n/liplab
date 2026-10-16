"""데스크탑 작은 점검(받기 없이): 확인 묶음 jobs.json(538·범주 28 절반 1)에서 앞 N클립만 특성을 계산해
10/9 ns 끝 자르기 점수(dgop_new.jsonl)와 같은지 본다(6.3절 다리 점검과 같은 비교, |차| ≤ 0.1). 판정 수치는 보지 않는다.

    python bridge_smoke.py W N WORKERS      (W = D:/liplab/sr/confirm)
"""
import json
import os
import random
import subprocess
import sys

W, N, WK = sys.argv[1], int(sys.argv[2]), sys.argv[3]
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
jobs = json.load(open(f"{W}/jobs.json", encoding="utf-8"))
rng = random.Random(1017)
sub = sorted(rng.sample(jobs, N), key=lambda j: j["clip"])
p = f"{W}/jobs_smoke.json"
json.dump(sub, open(p, "w", encoding="utf-8"), ensure_ascii=False)
out = f"{W}/out/feat_smoke.jsonl"
if os.path.exists(out):
    os.remove(out)
env = dict(os.environ, SR_W=W, SR_BACKEND=f"{W}/backend", PYTHONUTF8="1", OMP_NUM_THREADS="2", MKL_NUM_THREADS="2")
r = subprocess.run([sys.executable, "feat_pod.py", "feat", p, out, WK], cwd=f"{W}/tools", env=env)
assert r.returncode == 0
os.environ.setdefault("LIPLAB_LAB", "D:/liplab/lab")
import analyze as A  # noqa: E402
rows, errs = A.load(out)
print("rows", len(rows), "errors", dict(errs))
print("BRIDGE", json.dumps(A.bridge(rows), ensure_ascii=False))
