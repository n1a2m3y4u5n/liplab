#!/bin/bash
# roi_dl.sh: 데스크탑 WSL(2026-10-17): 입술 영역 전단용 538 받기(docs/lipread-roi-2026-10.md 8·11절).
#   cd /mnt/d/liplab/lab && bash tools/roi_dl.sh >> data/roi538/roi_dl.out 2>&1   (끊기면 같은 명령으로 이어 받음)
# A: 아직 받지 않은 배치(새 화자, 인물 중복은 V1·S4 루트와 대조), B: 받은 168명을 영상 앞 2.2 GB까지 다시(31~60번째 문장).
# 키 하나, 인증 실패면 멈춘다(BACKOFF_ROUNDS=1). D: 여유 60 GB 아래면 시작하지 않는다.
set -uo pipefail
LAB=$(cd "$(dirname "$0")/.." && pwd)
export LIPLAB_LAB=$LAB LIPLAB_SNAP=$LAB/snap AIHUB_KEYS_FILE=$LAB/.aihub.keys
R=$LAB/data/roi538; mkdir -p "$R/a" "$R/b"
PAT='fetch608|aihub608|dl_more|v1_dl|v7b_|538\.do|run608'
echo "ROI_DL wait $(date '+%F %T')"
while pgrep -f "$PAT" >/dev/null 2>&1; do sleep 60; done
python3 "$LAB/tools/roi_queue.py" "$LAB/data" "$R" "$LAB/tools/eval40.txt" || exit 3
run_phase() {   # $1=a|b  나머지=dl_more 추가 인자
  local ph=$1; shift
  echo "ROI_DL phase $ph start $(date '+%F %T') free=$(df -BG --output=avail "$R" | awk 'NR==2{gsub(/G/,"");print $1}')GB"
  BACKOFF_ROUNDS=1 DLMORE_ROOT=$R/$ph VBYTES=2200000000 CAP=60 MINCLIPS=15 MINFREE_GB=60 BUDGET_GB=6 JOBS=1 \
    nice -n 10 bash "$LAB/tools/dl_more.sh" --protect none --labels stream "$@" "$R/queue_$ph.tsv"
  local rc=$?
  echo "ROI_DL phase $ph end rc=$rc $(date '+%F %T') done=$(ls "$R/$ph"/.state/*.done 2>/dev/null | wc -l) fail=$(ls "$R/$ph"/.state/*.fail 2>/dev/null | wc -l)"
  return $rc
}
run_phase a --also-manifest "$LAB/data/v1_538r/manifest.tsv" --also-manifest "$LAB/data/e538r/manifest.tsv" || { [ $? -eq 3 ] && { echo "ROI_DL 키 실패로 멈춤"; exit 3; }; }
run_phase b; rc=$?
touch "$R/DL_DONE"
echo "ROI_DL_DONE rc=$rc $(date '+%F %T')"
