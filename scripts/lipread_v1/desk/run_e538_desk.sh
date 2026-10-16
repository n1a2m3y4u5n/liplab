#!/bin/bash
# run_e538_desk.sh — 데스크탑 WSL(2026-10-17): S4 평가용 538 클립(E1 600·E2 1,740, 58명, 10/14 정리로 지워짐) 다시 받기.
#   V1 큐 받기가 끝난 뒤(IP당 한 세션) dl_more.sh를 같은 규칙(VBYTES 1.8GB, CAP 30)으로, 58명 모두 보호(인물 건너뛰기 없음)로 돌린다.
#   재현 확인은 data/e538r/expected.tsv(9/24·9/25 manifest)와 클립 이름·문장 비교(docs/scorer-stream-chunk-2026-10.md 6절).
#   cd /mnt/d/liplab/lab && bash tools/run_e538_desk.sh >> data/e538r/run.out 2>&1
set -uo pipefail
LAB=$(cd "$(dirname "$0")/.." && pwd)
export LIPLAB_LAB=$LAB LIPLAB_SNAP=$LAB/snap AIHUB_KEYS_FILE=$LAB/.aihub.keys
ROOT=$LAB/data/e538r
mkdir -p "$ROOT"
PAT='fetch608|aihub608|dl_more|v1_dl|v7b_|538\.do|run608|v1r_dl'
echo "WAIT start $(date '+%F %T')"
ok=0
while [ "$ok" -lt 3 ]; do
  if pgrep -f "$PAT" >/dev/null 2>&1 || ! grep -q '^V1R_DL end' "$LAB/data/v1_538r/v1r_dl.out" 2>/dev/null; then ok=0; sleep 60
  else ok=$((ok + 1)); [ "$ok" -lt 3 ] && sleep 60; fi
done
echo "WAIT done $(date '+%F %T')"
P=$(grep -v '^#' "$ROOT/queue.tsv" | cut -f1 | paste -sd, -)
BACKOFF_ROUNDS=1 DLMORE_ROOT=$ROOT VBYTES=1800000000 MINFREE_GB=10 BUDGET_GB=6 JOBS=1 \
  nice -n 15 bash "$LAB/tools/dl_more.sh" --protect "$P" --labels stream "$ROOT/queue.tsv"
rc=$?
python3 - "$ROOT" <<'PY'
import os, sys
root = sys.argv[1]
exp = [l.rstrip("\n").split("\t") for l in open(f"{root}/expected.tsv", encoding="utf-8") if l.strip()]
got = {}
if os.path.exists(f"{root}/manifest.tsv"):
    for l in open(f"{root}/manifest.tsv", encoding="utf-8"):
        t = l.rstrip("\n").split("\t")
        if len(t) >= 3:
            got[t[0]] = t[2]
same = sum(1 for e in exp if e[0] in got and got[e[0]] == e[2])
name = sum(1 for e in exp if e[0] in got)
print("E538_REPRO expected=%d name_match=%d name_text_match=%d frac=%.4f" % (len(exp), name, same, same / max(1, len(exp))))
PY
echo "E538_DONE rc=$rc $(date '+%F %T')"
