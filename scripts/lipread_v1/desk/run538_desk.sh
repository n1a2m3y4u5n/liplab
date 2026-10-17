#!/bin/bash
# run538_desk.sh — 데스크탑 WSL(2026-10-17): 608 범주 27 두 번째 묶음 받기가 끝난 뒤(IP당 한 세션) 538 V1 큐 130개를 받는다.
#   cd /mnt/d/liplab/lab && bash tools/run538_desk.sh >> data/v1_538r/v1r_dl.out 2>&1
set -uo pipefail
LAB=$(cd "$(dirname "$0")/.." && pwd)
export LIPLAB_LAB=$LAB LIPLAB_SNAP=$LAB/snap AIHUB_KEYS_FILE=$LAB/.aihub.keys
mkdir -p "$LAB/data/v1_538r"
PAT='fetch608|aihub608|dl_more|v1_dl|v7b_|538\.do|run608'
echo "WAIT start $(date '+%F %T')"
ok=0
while [ "$ok" -lt 3 ]; do
  if pgrep -f "$PAT" >/dev/null 2>&1 || [ ! -s "$LAB/data/hi608/c27/b2/fetch_summary.json" ]; then
    ok=0; sleep 60
  else
    ok=$((ok + 1)); [ "$ok" -lt 3 ] && sleep 60
  fi
done
echo "WAIT done $(date '+%F %T') → v1r_dl_desk.sh"
cd "$LAB" && exec bash tools/v1r_dl_desk.sh
