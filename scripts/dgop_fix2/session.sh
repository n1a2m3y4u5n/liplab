#!/bin/bash
# 끝 구간 다시 나누기 확인 측정 파드 세션(맥, docs/dgop-final-vowel-fix2-2026-10.md). 파드는 liplab-lab의 tools/pod/pod.sh로만 다룬다.
#   bash scripts/dgop_fix2/session.sh stage    묶음(파드 없음): 이 브랜치 backend·측정 코드, 작업 목록, 538n·608n·서버 음성 소리, 저하 도구
#   bash scripts/dgop_fix2/session.sh launch   잔액 확인 → 파드 생성(워치독) → wait(자폭 타이머) → 올리기 → sha256 → run.sh
#   bash scripts/dgop_fix2/session.sh tail     파드 로그 끝부분
#   bash scripts/dgop_fix2/session.sh fetch    결과 받기(파드는 그대로)
#   bash scripts/dgop_fix2/session.sh finish   fetch → terminate → status로 이 파드가 없어진 것을 확인
# 상태 폴더 .alstate, 파드 이름 liplab-al. RunPod 키는 pod.sh가 ~/.runpod/config.toml에서 메모리로만 읽는다.
# 다른 이름의 파드(liplab-ad 등)는 건드리지 않는다. 538·608 원자료는 liplab-lab과 파드에만 둔다.
set -uo pipefail
APP=$(cd "$(dirname "$0")/../.." && pwd)
LAB=${LAB:-$HOME/Downloads/liplab-lab}
P="$LAB/tools/pod/pod.sh"
export POD_STATE_DIR=${POD_STATE_DIR:-$LAB/tools/pod/.alstate} POD_NAME=${POD_NAME:-liplab-al} POD_DISK_GB=${POD_DISK_GB:-60}
export DEADMAN_GRACE_MIN=${DEADMAN_GRACE_MIN:-15}
M8=${M8:-$LAB/models/dgop_ours_2026-09-25_int8}
NS=${NS:-$LAB/data/ns_stage/root}
S=${STAGE_DIR:-$LAB/data/al_stage}
GPUS=${GPUS:-NVIDIA A40|SECURE,NVIDIA RTX A6000|SECURE,NVIDIA L40S|SECURE}
WD_MIN=${WD_MIN:-90}
MIN_BALANCE=${MIN_BALANCE:-10}
SHA_ALIGNER=18681947f740b7486f8fa4f93c7c0f68fe1595ac4fa9822800dfd38d713f5e66
SHA_SCORER=e8340d58dd911e380eca508815526eb77ec658560456ce1fe4c16b9b6e3654c4
mkdir -p "$S" "$LAB/data/pod_runs" "$POD_STATE_DIR"
CMD=${1:-}
LOG="$LAB/data/pod_runs/session_al_${CMD}_$(date +%Y%m%d_%H%M).log"
exec > >(tee -a "$LOG") 2>&1
step() { echo "=== $(date '+%F %T') $*"; }
die() { echo "ALS_FAIL $*"; exit 1; }
pod_id() { awk -F= '$1 == "POD_ID" {print $2}' "$POD_STATE_DIR/.pod_state" 2>/dev/null; }
sha_of() { shasum -a 256 "$1" | cut -d' ' -f1; }

do_stage() {
  step "가중치 확인"
  [ "$(sha_of "$M8/aligner/model.int8.safetensors")" = "$SHA_ALIGNER" ] || die "정렬기 int8 sha256"
  [ "$(sha_of "$M8/scorer/model.int8.safetensors")" = "$SHA_SCORER" ] || die "채점기 int8 sha256"
  step "묶음"
  R=$S/root
  rm -rf "$R/backend" "$R/scripts" "$R/tools" && mkdir -p "$R/backend/data" "$R/scripts" "$R/tools" "$R/data"
  cp "$APP"/backend/*.py "$R/backend/" || die backend
  cp "$APP"/backend/data/dgop_calibration*.json "$R/backend/data/" || die calibration
  cp "$APP"/scripts/dgop_fix2/measure.py "$APP"/scripts/dgop_fix2/run.sh "$APP"/scripts/dgop_fix2/mfa.sh "$R/scripts/" || die scripts
  cp "$LAB/tools/make_deaf_corpus.py" "$R/tools/" || die tools
  for m in aligner scorer; do
    mkdir -p "$R/backend/models/dgop_ours/$m"
    for f in "$M8/$m"/*; do case "$(basename "$f")" in model.int8.safetensors) ;; *) cp "$f" "$R/backend/models/dgop_ours/$m/" ;; esac; done
  done
  python3 "$APP/scripts/dgop_fix2/build_jobs.py" "$NS" "$APP/backend/data/sound" "$R/data" || die jobs
  ( cd "$R" && find backend scripts tools data -type f | sort | xargs shasum -a 256 ) > "$R/expect.sha256"
  printf '%s  backend/models/dgop_ours/aligner/model.int8.safetensors\n%s  backend/models/dgop_ours/scorer/model.int8.safetensors\n' \
    "$SHA_ALIGNER" "$SHA_SCORER" >> "$R/expect.sha256"
  COPYFILE_DISABLE=1 tar --no-mac-metadata --no-xattrs --exclude .DS_Store --exclude '._*' -cf "$S/al.tar" -C "$R" . || die tar
  ls -la "$S/al.tar"
  echo "ALS_STAGE_OK"
}

do_launch() {
  [ -s "$S/al.tar" ] || die "묶음 없음(stage 먼저)"
  step "잔액·파드 목록"
  st=$(bash "$P" status 2>&1); echo "$st"
  bal=$(echo "$st" | awk '/^BALANCE/ {gsub(/\$/, "", $2); print $2}')
  [ -n "$bal" ] || die "잔액을 읽지 못함"
  awk -v b="$bal" -v m="$MIN_BALANCE" 'BEGIN { exit !(b + 0 >= m + 0) }' || die "잔액 \$$bal < \$$MIN_BALANCE, 파드를 쓰지 않는다"
  step "파드 생성(워치독 ${WD_MIN}분, 상태 $POD_STATE_DIR, 이름 $POD_NAME, 디스크 ${POD_DISK_GB}GB)"
  created=0
  IFS=',' read -r -a CANDS <<< "$GPUS"
  for cand in "${CANDS[@]}"; do
    g=${cand%%|*}; c=${cand#*|}
    step "후보 $g / $c"
    if bash "$P" create "$g" "$c" --watchdog "$WD_MIN"; then created=1; break; fi
  done
  [ "$created" = 1 ] || die "create(모든 후보 실패, 파드 없음)"
  echo "ALS_POD $(pod_id)"
  bash "$P" wait || { bash "$P" terminate --force || true; die wait; }
  bash "$P" ssh 'nproc; cat /sys/fs/cgroup/cpu.max 2>/dev/null; free -g | head -2; df -h /workspace | tail -1; nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader'
  step "올리기"
  python3 "$LAB/tools/pod/pupload.py" "$S/al.tar" /workspace/al.tar "$M8/aligner/model.int8.safetensors" /workspace/aligner.int8 \
    "$M8/scorer/model.int8.safetensors" /workspace/scorer.int8 --chunk-mb 8 --par 24 > "$S/pupload.log" 2>&1
  PUP_RC=$?
  tail -n 4 "$S/pupload.log"
  { [ "$PUP_RC" = 0 ] && grep -q '^PUP_DONE ok=3 fail=0' "$S/pupload.log"; } || { bash "$P" terminate --force || true; die "upload(rc=$PUP_RC)"; }
  bash "$P" ssh 'mkdir -p /workspace/al && cd /workspace/al && tar -xf ../al.tar && rm -f ../al.tar && mv ../aligner.int8 backend/models/dgop_ours/aligner/model.int8.safetensors && mv ../scorer.int8 backend/models/dgop_ours/scorer/model.int8.safetensors && sha256sum -c --quiet expect.sha256 && echo REMOTE_SHA_OK' \
    | tee "$S/unpack.log" || { bash "$P" terminate --force || true; die "풀기"; }
  grep -q '^REMOTE_SHA_OK' "$S/unpack.log" || { bash "$P" terminate --force || true; die "sha256 불일치"; }
  step "run.sh 시작"
  bash "$P" run 'bash /workspace/al/scripts/run.sh' || { bash "$P" terminate --force || true; die run; }
  echo "ALS_LAUNCH_OK $(pod_id)"
}

get() {  # 원격 파일 → 로컬, 크기 확인
  local rf=$1 lf=$2 rs ls_
  mkdir -p "$(dirname "$lf")"
  rs=$(bash "$P" ssh "stat -c %s '$rf' 2>/dev/null" | tr -d '\r\n')
  [ -n "$rs" ] || { echo "없음: $rf"; return 1; }
  bash "$P" ssh "cat '$rf'" > "$lf" || return 1
  ls_=$(stat -f %z "$lf")
  [ "$rs" = "$ls_" ] || { echo "크기 다름: $rf $rs vs $ls_"; return 1; }
  echo "받음 $lf ($ls_)"
}

do_fetch() {
  POD=$(pod_id)
  [ -n "$POD" ] || die "파드 없음"
  out="$LAB/data/pod_runs/$(date +%Y%m%d)_${POD}/al"
  mkdir -p "$out"
  if bash "$P" ssh 'test -s /workspace/al_result.tgz && grep -q "^AL_OK" /workspace/dax/logs/al.log'; then
    get /workspace/al_result.tgz "$out/result.tgz" && tar -xzf "$out/result.tgz" -C "$out" && echo "ALS_FETCH_OK $out" || echo "ALS_FETCH_WARN"
  else
    bash "$P" ssh 'cd /workspace && tar -czf - al/out dax/logs 2>/dev/null' | tar -xzf - -C "$out" && echo "ALS_FETCH_PARTIAL $out" || echo "ALS_FETCH_WARN"
  fi
  ls -la "$out" "$out/al/out" 2>/dev/null | tail -30
}

do_finish() {
  POD=$(pod_id)
  do_fetch
  bash "$P" terminate --force || true
  st=$(bash "$P" status 2>&1); echo "$st"
  if [ -n "$POD" ] && echo "$st" | grep -q "$POD"; then echo "ALS_FAIL 파드 $POD 가 아직 목록에 있음"; else echo "ALS_TERMINATED $POD"; fi
}

case "$CMD" in
  stage) do_stage ;;
  launch) do_launch ;;
  tail) bash "$P" ssh 'tail -n 25 /workspace/dax/logs/al.log; tail -n 3 /workspace/dax/logs/mfa.log 2>/dev/null; wc -l /workspace/al/out/*.jsonl 2>/dev/null | tail -n 1; nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader' ;;
  fetch) do_fetch ;;
  finish) do_finish ;;
  *) echo "session.sh stage|launch|tail|fetch|finish"; exit 2 ;;
esac
