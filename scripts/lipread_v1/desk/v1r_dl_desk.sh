#!/bin/bash
# v1r_dl_desk.sh — 데스크탑 WSL판(2026-10-17, v1r_dl.sh에서 df·회선 제한만 바꿈). V1 재받기(2026-10-15). 10/14 정리에서 지운 538 V1 클립을 새 루트(data/v1_538r)로 다시 받는다.
#   큐는 10/6과 같은 queue_v1.tsv 앞 N_QUEUE개(기본 130, 같은 순서). 인물 중복 검사는 기존 68명과
#   이 루트만 본다(옛 v1_538 manifest는 넣지 않는다: 넣으면 같은 인물을 모두 중복으로 보고 다음 인물로 넘어간다).
#   (10/14 정리로 archive/expand538·expand538_more가 없어져, 기존 68명(벤치 30, 9/25 12·26)의 인물은 pod_runs의 세 manifest_all로 본다.)
#   VBYTES 기본 1.0GB(10/6은 1.8GB, 그때 87명 중 79명이 첫 mp4 하나로 30문장을 채움). 원본은 컷 뒤 dl_more가 지운다.
#   디스크: 다운로드 시작 전 여유 MINFREE_GB(기본 10) 미만이면 dl_more가 멈추고(종료코드 4), 이 감시는 여유가
#   STOP_GB(기본 8) 아래로 떨어지면 받기를 끝낸다(다시 실행하면 이어 받음).
#   회선 양보: LIPLAB_LIMIT_RATE=2M 으로 시작하거나, 도는 중에 echo 2M > data/v1_538r/.limit_rate (다음 요청부터, 지우면 해제).
#   사용: cd ~/Downloads/LIPLAB_ALL/liplab-lab && nohup caffeinate -i bash tools/v1r_dl.sh > data/v1_538r/v1r_dl.out 2>&1 &
set -uo pipefail
set +x
LAB=$(cd "$(dirname "$0")/.." && pwd)
SRC=$LAB/data/v1_538
PR=$LAB/data/pod_runs
ROOT=$LAB/data/v1_538r
N_QUEUE=${N_QUEUE:-130}
STOP_GB=${STOP_GB:-8}
mkdir -p "$ROOT"
{ head -n 1 "$SRC/queue_v1.tsv"; grep -v '^#' "$SRC/queue_v1.tsv" | head -n "$N_QUEUE"; } > "$ROOT/queue_run.tsv"
echo "V1R_DL start $(date '+%F %T') queue=$(grep -vc '^#' "$ROOT/queue_run.tsv") free=$(df -BG --output=avail "$ROOT" | awk 'NR==2{gsub(/G/, ""); print $1}')GB vbytes=${VBYTES:-1000000000} rate=$(cat "$ROOT/.limit_rate" 2>/dev/null || echo none)"

cleanup_failed() {
  local f s
  for f in "$ROOT"/.state/*.fail; do
    [ -e "$f" ] || continue
    s=$(basename "$f" .fail)
    if [ -d "$ROOT/.work/$s" ] && grep -q '라벨 JSON 없음' "$f" 2>/dev/null; then
      rm -rf "${ROOT:?}/.work/$s" && echo "V1R_DL cleaned .work/$s (라벨 없음) $(date '+%T')"
    fi
  done
}

# 맥 부하(10/15 메인 세션 알림): 받기·ffmpeg 컷을 nice 20으로, 받기 1·컷 1(동시 2개 이하). 회선은 .limit_rate(기본 4M)로 제한.
# 데스크탑: 사용자 지시로 회선 제한 없음(.limit_rate를 만들지 않는다. 필요하면 echo 4M > $ROOT/.limit_rate)
DLMORE_ROOT=$ROOT VBYTES=${VBYTES:-1000000000} MINFREE_GB=${MINFREE_GB:-10} BUDGET_GB=${BUDGET_GB:-4} JOBS=1 \
  nice -n 20 bash "$LAB/tools/dl_more.sh" --protect none --labels stream \
  --also-manifest "$PR/20260924_k74l2l74024fsz/manifest_all.tsv" \
  --also-manifest "$PR/20260925_4aol7xkyf762yh/dax/manifest_all.tsv" \
  --also-manifest "$PR/20260925_nwcqu40di2ct11/dax/manifest_all.tsv" "$ROOT/queue_run.tsv" &
DL=$!
while kill -0 "$DL" 2>/dev/null; do
  cleanup_failed
  fr=$(df -BG --output=avail "$ROOT" | awk 'NR==2{gsub(/G/, ""); print $1}')
  if [ "${fr:-0}" -lt "$STOP_GB" ]; then
    echo "V1R_DL disk free ${fr}GB < ${STOP_GB}GB → 멈춤 $(date '+%T')"
    kill -TERM "$DL" 2>/dev/null
    sleep 20
    break
  fi
  sleep 30
done
wait "$DL"; rc=$?
cleanup_failed
echo "V1R_DL end rc=$rc $(date '+%F %T') done=$(ls "$ROOT"/.state/*.done 2>/dev/null | wc -l | tr -d ' ') fail=$(ls "$ROOT"/.state/*.fail 2>/dev/null | wc -l | tr -d ' ') skip=$(ls "$ROOT"/.state/*.skip 2>/dev/null | wc -l | tr -d ' ') free=$(df -BG --output=avail "$ROOT" | awk 'NR==2{gsub(/G/, ""); print $1}')GB"
