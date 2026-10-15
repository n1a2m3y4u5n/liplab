#!/bin/bash
# 음소 칩 꼬리 A2 재확인(새 538 화자) 파드 세션(맥, docs/phone-tail-2026-10.md 8절). 파드는 liplab-lab의 tools/pod/pod.sh로만 다룬다.
#   bash scripts/phone_tail/pod/session_a2.sh stage    묶음(파드 없음): backend, 스크립트, A1 작업 목록·소리, 10/7 지연 표본 길이·목표
#   bash scripts/phone_tail/pod/session_a2.sh launch   잔액 확인(5달러 아래면 멈춤) → 파드 생성(워치독) → wait(자폭 타이머) → 올리기 → sha256 → run.sh
#   bash scripts/phone_tail/pod/session_a2.sh tail     파드 로그 끝부분
#   bash scripts/phone_tail/pod/session_a2.sh finish   결과 받기 → terminate → status
# 상태 폴더 .pta2state, 파드 이름 liplab-pta2. RunPod 키는 pod.sh가 ~/.runpod/config.toml에서 메모리로만 읽는다. 538 원자료는 lab 묶음과 파드에만 둔다.
set -uo pipefail
APP=$(cd "$(dirname "$0")/../../.." && pwd)
LAB=${LAB:-$HOME/Downloads/LIPLAB_ALL/liplab-lab}
P="$LAB/tools/pod/pod.sh"
export POD_STATE_DIR=${POD_STATE_DIR:-$LAB/tools/pod/.pta2state} POD_NAME=${POD_NAME:-liplab-pta2} POD_DISK_GB=${POD_DISK_GB:-50}
export DEADMAN_GRACE_MIN=${DEADMAN_GRACE_MIN:-15}
M8=${M8:-$LAB/models/dgop_ours_2026-09-25_int8}
S=${STAGE_DIR:-$LAB/data/pta2stage}
GPUS=${GPUS:-NVIDIA A40|SECURE,NVIDIA RTX A6000|SECURE,NVIDIA L40S|SECURE}
WD_MIN=${WD_MIN:-45}
MIN_BAL=${MIN_BAL:-5}
SHA_ALIGNER=18681947f740b7486f8fa4f93c7c0f68fe1595ac4fa9822800dfd38d713f5e66
SHA_SCORER=e8340d58dd911e380eca508815526eb77ec658560456ce1fe4c16b9b6e3654c4
mkdir -p "$S" "$LAB/data/pod_runs" "$POD_STATE_DIR"
CMD=${1:-}
LOG="$LAB/data/pod_runs/session_pta2_${CMD}_$(date +%Y%m%d_%H%M).log"
exec > >(tee -a "$LOG") 2>&1
step() { echo "=== $(date '+%F %T') $*"; }
die() { echo "A2S_FAIL $*"; exit 1; }
pod_id() { awk -F= '$1 == "POD_ID" {print $2}' "$POD_STATE_DIR/.pod_state" 2>/dev/null; }
sha_of() { shasum -a 256 "$1" | cut -d' ' -f1; }

do_stage() {
  step "가중치 확인"
  [ "$(sha_of "$M8/aligner/model.int8.safetensors")" = "$SHA_ALIGNER" ] || die "정렬기 sha256"
  [ "$(sha_of "$M8/scorer/model.int8.safetensors")" = "$SHA_SCORER" ] || die "채점기 sha256"
  [ -s "$S/data/jobs.jsonl" ] && [ -s "$S/data/wav_list.tsv" ] || die "작업 목록 없음(build_a2.py 먼저)"
  R=$S/root
  rm -rf "$R" && mkdir -p "$R/backend/data" "$R/scripts/phone_tail/pod" "$R/data/wav"
  cp "$APP"/backend/*.py "$R/backend/" || die backend
  rm -f "$R"/backend/test_*.py
  cp "$APP"/backend/data/dgop_calibration*.json "$R/backend/data/" || die calibration
  cp "$APP"/scripts/phone_tail/{offline.py,chipval.py} "$R/scripts/phone_tail/" || die scripts
  cp "$APP"/scripts/phone_tail/pod/{measure_lp.py,run_a2.sh} "$R/scripts/phone_tail/pod/" || die scripts
  cp "$S/data/jobs.jsonl" "$R/data/" || die data
  for m in aligner scorer; do
    mkdir -p "$R/backend/models/dgop_ours/$m"
    for f in "$M8/$m"/*; do case "$(basename "$f")" in model.int8.safetensors|model.safetensors) ;; *) cp "$f" "$R/backend/models/dgop_ours/$m/" ;; esac; done
  done
  while IFS=$'\t' read -r c p; do cp "$p" "$R/data/wav/$c.wav" || die "소리 $c"; done < "$S/data/wav_list.tsv"
  echo "COPIED $(ls "$R/data/wav" | wc -l)"
  ( cd "$R" && find backend scripts data -type f | sort | xargs shasum -a 256 ) > "$R/expect.sha256"
  printf '%s  backend/models/dgop_ours/aligner/model.int8.safetensors\n%s  backend/models/dgop_ours/scorer/model.int8.safetensors\n' \
    "$SHA_ALIGNER" "$SHA_SCORER" >> "$R/expect.sha256"
  COPYFILE_DISABLE=1 tar --no-mac-metadata --no-xattrs --exclude .DS_Store --exclude '._*' -cf "$S/pta2.tar" -C "$R" . || die tar
  ls -la "$S/pta2.tar"
  echo "A2S_STAGE_OK"
}

do_launch() {
  [ -s "$S/pta2.tar" ] || die "묶음 없음(stage 먼저)"
  step "잔액·파드 목록"
  st=$(bash "$P" status 2>&1); echo "$st"
  bal=$(echo "$st" | grep -Eio 'balance[^0-9]*[0-9]+(\.[0-9]+)?' | grep -Eo '[0-9]+(\.[0-9]+)?' | head -1)
  [ -n "$bal" ] || die "잔액을 읽지 못함"
  awk -v b="$bal" -v m="$MIN_BAL" 'BEGIN { exit !(b >= m) }' || die "잔액 $bal < $MIN_BAL"
  step "파드 생성(워치독 ${WD_MIN}분, 상태 $POD_STATE_DIR, 이름 $POD_NAME)"
  created=0
  IFS=',' read -r -a CANDS <<< "$GPUS"
  for cand in "${CANDS[@]}"; do
    g=${cand%%|*}; c=${cand#*|}
    step "후보 $g / $c"
    if bash "$P" create "$g" "$c" --watchdog "$WD_MIN"; then created=1; break; fi
  done
  [ "$created" = 1 ] || die "create(모든 후보 실패, 파드 없음)"
  echo "A2S_POD $(pod_id)"
  bash "$P" wait || { bash "$P" terminate --force || true; die wait; }
  bash "$P" ssh 'nproc; cat /sys/fs/cgroup/cpu.max 2>/dev/null; grep -m1 "model name" /proc/cpuinfo; free -g | head -2; nvidia-smi --query-gpu=name,memory.total --format=csv,noheader'
  step "올리기"
  python3 "$LAB/tools/pod/pupload.py" "$S/pta2.tar" /workspace/pta2.tar "$M8/aligner/model.int8.safetensors" /workspace/aligner.int8 \
    "$M8/scorer/model.int8.safetensors" /workspace/scorer.int8 --chunk-mb 8 --par 24 > "$S/pupload.log" 2>&1
  PUP_RC=$?
  tail -n 4 "$S/pupload.log"
  { [ "$PUP_RC" = 0 ] && grep -q '^PUP_DONE ok=3 fail=0' "$S/pupload.log"; } || { bash "$P" terminate --force || true; die "upload(rc=$PUP_RC)"; }
  bash "$P" ssh 'mkdir -p /workspace/pta2 && cd /workspace/pta2 && tar -xf ../pta2.tar && rm -f ../pta2.tar && mv ../aligner.int8 backend/models/dgop_ours/aligner/model.int8.safetensors && mv ../scorer.int8 backend/models/dgop_ours/scorer/model.int8.safetensors && sha256sum -c --quiet expect.sha256 && echo REMOTE_SHA_OK' \
    | tee "$S/unpack.log" || { bash "$P" terminate --force || true; die "풀기"; }
  grep -q '^REMOTE_SHA_OK' "$S/unpack.log" || { bash "$P" terminate --force || true; die "sha256 불일치"; }
  step "run.sh 시작"
  bash "$P" run "bash /workspace/pta2/scripts/phone_tail/pod/run_a2.sh" || { bash "$P" terminate --force || true; die run; }
  echo "A2S_LAUNCH_OK $(pod_id)"
}

do_fetch() {
  POD=$(pod_id)
  [ -n "$POD" ] || die "파드 없음"
  out="$LAB/data/pod_runs/$(date +%Y%m%d)_${POD}/pta2"
  mkdir -p "$out"
  if bash "$P" ssh 'test -s /workspace/a2_result.tgz && grep -q "^A2_OK" /workspace/dax/logs/a2.log'; then
    bash "$P" ssh 'cat /workspace/a2_result.tgz' > "$out/result.tgz" && tar -xzf "$out/result.tgz" -C "$out" && echo "A2S_FETCH_OK $out" || echo "A2S_FETCH_WARN"
  else
    bash "$P" ssh 'cd /workspace && tar -czf - pta2/out/a2t dax/logs 2>/dev/null' | tar -xzf - -C "$out" && echo "A2S_FETCH_PARTIAL $out" || echo "A2S_FETCH_WARN"
  fi
  ls -la "$out" 2>/dev/null | tail -20
}

case "$CMD" in
  stage) do_stage ;;
  launch) do_launch ;;
  tail) bash "$P" ssh 'tail -n 25 /workspace/dax/logs/a2.log; tail -n 2 /workspace/dax/logs/lp.*.log 2>/dev/null' ;;
  fetch) do_fetch ;;
  finish) do_fetch; bash "$P" terminate --force || true; bash "$P" status || true ;;
  *) echo "session_a2.sh stage|launch|tail|fetch|finish"; exit 2 ;;
esac
