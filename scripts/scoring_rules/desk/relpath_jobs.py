"""데스크탑: b2jobs가 만든 jobs_b2.json의 조각 경로(cut_608이 쓴 절대 경로)를 jobs 파일 폴더 기준 상대 경로로 바꾼다.
feat_pod.py는 '/'로 시작하는 경로만 절대 경로로 보므로 Windows의 'D:/…'를 그대로 두면 앞에 폴더가 한 번 더 붙는다.
경로 말고는 아무것도 바꾸지 않는다.   python relpath_jobs.py JOBS_B2.json
"""
import json
import os
import sys

p = os.path.abspath(sys.argv[1])
root = os.path.dirname(p)
jobs = json.load(open(p, encoding="utf-8"))
n = 0
for j in jobs:
    q = j["path"]
    if os.path.isabs(q):
        j["path"] = os.path.relpath(q, root).replace("\\", "/")
        n += 1
    assert os.path.exists(os.path.join(root, j["path"])), j["path"]
json.dump(jobs, open(p, "w", encoding="utf-8"), ensure_ascii=False)
print("RELPATH_OK", n, len(jobs), flush=True)
