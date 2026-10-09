#!/bin/bash
# V7b 받기 전체(맥, 2026-10-09, 앱 docs/newdata-608c27-538-2026-10.md 3절). 608 받기가 끝난 뒤 한 번 실행한다.
#   nohup caffeinate -i bash tools/v7b_fetch_all.sh > data/v18/v7b_dl2/fetch_all.log 2>&1 &
set -u
cd "$(dirname "$0")/.."
if pgrep -f "fetch608|dev_expand_fetch|dl_more|v1_dl" >/dev/null; then echo "V7BALL_FAIL 다른 AI Hub 받기가 돈다"; exit 1; fi
NEW="spk375 spk380 spk383 spk410 spk412 spk418 spk425 spk432 spk433 spk445 spk472 spk478 spk502 spk508 spk515 spk613"
KNOWN="spk377=E192,spk411=E072,spk471=E146,spk473=E230,spk509=E033,spk607=E220"
EXPL="spk345=E209,spk507=E197,spk511=E092,spk347=E009,spk353=E080,spk379=E007,spk409=E022,spk477=E005"
echo "=== $(date '+%F %T') survey"
python3 tools/v7b_stream.py survey $NEW
python3 tools/v7b_stream.py plan | tail -3
echo "=== $(date '+%F %T') 확인 절반 옛 배치"
python3 tools/v7b_stream.py run $(echo "$KNOWN" | tr ',' '\n' | cut -d= -f1) --known "$KNOWN"
echo "=== $(date '+%F %T') 확인 절반 새 배치"
python3 tools/v7b_stream.py run $NEW
echo "=== $(date '+%F %T') 탐색 절반(남으면)"
python3 tools/v7b_stream.py run $(echo "$EXPL" | tr ',' '\n' | cut -d= -f1) --known "$EXPL"
echo "V7BALL_DONE $(date '+%F %T') free=$(df -g ~ | awk 'NR==2{print $4}')GB"
