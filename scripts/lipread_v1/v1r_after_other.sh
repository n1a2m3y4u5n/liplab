#!/bin/bash
# v1r_after_other.sh — 다른 AI Hub 받기(IP당 한 세션)가 끝나기를 기다렸다가 v1r_dl.sh를 시작한다(2026-10-15).
#   1분 간격으로 세 번 연속 다른 받기 프로세스가 없을 때 시작한다. 패턴은 사용자 지시(aihub|fetch608|v7b_|538.do|dl_more|v1_dl).
set -uo pipefail
LAB=$(cd "$(dirname "$0")/.." && pwd)
PAT='aihub|fetch608|v7b_|538\.do|dl_more|v1_dl'
mkdir -p "$LAB/data/v1_538r"
echo "WAIT start $(date '+%F %T')"
ok=0
while [ "$ok" -lt 3 ]; do
  if pgrep -f "$PAT" >/dev/null 2>&1; then
    [ "$ok" -gt 0 ] && echo "WAIT 다시 돎 $(date '+%T')"
    ok=0; sleep 60
  else
    ok=$((ok + 1)); [ "$ok" -lt 3 ] && sleep 60
  fi
done
echo "WAIT done $(date '+%F %T') → v1r_dl.sh"
cd "$LAB" && exec bash tools/v1r_dl.sh
