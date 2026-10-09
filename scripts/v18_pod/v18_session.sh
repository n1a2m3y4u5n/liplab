#!/bin/bash
# V18 입술 돌출 파드 세션(맥, 2026-10-09). 사전 등록: docs/lip-protrusion-v18-2026-10.md.
#   v15_session.sh와 같은 틀(liplab-lab/tools/pod의 pod.sh·pupload.py). 상태 폴더 .v18state, 파드 이름 liplab-v18로 다른 세션과 섞이지 않게 한다.
#   bash v18_session.sh stage            묶음(하네스, 스크립트, 정렬기, 비정면 클립, 작업)
#   [WD_MIN=120] bash v18_session.sh start   묶음 → 파드 → 올리기 → run_v18.sh setup(분리 실행)
#   bash v18_session.sh step 'ARGS'      run_v18.sh 단계 분리 실행
#   bash v18_session.sh wait MARKER [MIN]  파드 로그에 표식이 나올 때까지
#   bash v18_session.sh log [N]
#   bash v18_session.sh fetch NAME       out/NAME(영상 제외)을 data/pod_runs/<날짜>_<파드>/v18/NAME/로(real은 side_bs·align)
#   bash v18_session.sh extend MIN | finish
set -uo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
APP=$(cd "$HERE/../.." && pwd)
LAB=${LAB:-$HOME/Downloads/liplab-lab}
cd "$LAB/tools/pod" || exit 1
P=pod.sh
export POD_STATE_DIR=${POD_STATE_DIR:-$LAB/tools/pod/.v18state} POD_NAME=${POD_NAME:-liplab-v18}
export POD_DISK_GB=${POD_DISK_GB:-40}
D=$LAB/data/v18
S=$D/stage
M8=$LAB/models/dgop_ours_2026-09-25_int8
SHA_ALIGNER=18681947f740b7486f8fa4f93c7c0f68fe1595ac4fa9822800dfd38d713f5e66
GPUS=${GPUS:-NVIDIA A40|SECURE,NVIDIA RTX A6000|SECURE,NVIDIA L40S|SECURE}
WD_MIN=${WD_MIN:-120}
mkdir -p "$S" "$LAB/data/pod_runs" "$POD_STATE_DIR"
CMD=${1:-}
LOG="$LAB/data/pod_runs/session_v18_${CMD}_$(date +%Y%m%d_%H%M).log"
exec > >(tee -a "$LOG") 2>&1
step() { echo "=== $(date '+%F %T') $*"; }
die() { echo "V18S_FAIL $*"; exit 1; }
POD=$(awk -F= '$1 == "POD_ID" {print $2}' "$POD_STATE_DIR/.pod_state" 2>/dev/null)
retry() {
  local n=$1 k=1; shift
  until "$@"; do [ "$k" -ge "$n" ] && return 1; echo "V18S_RETRY $k/$n"; sleep $((k * 15)); k=$((k + 1)); done
}
do_stage() {
  step "묶음"
  [ "$(shasum -a 256 "$M8/aligner/model.int8.safetensors" | cut -d' ' -f1)" = "$SHA_ALIGNER" ] || die "정렬기 sha256"
  R=$S/root
  rm -rf "$R" && mkdir -p "$R/scripts/v2_render" "$R/tools" "$R/in" "$R/harness" "$R/clips"
  (cd "$APP/scripts/v2_render" && ../../frontend/node_modules/.bin/vite build --config vite.config.mjs --outDir "$R/harness" --logLevel error) || die "harness build"
  git -C "$APP" archive HEAD backend | tar -x -C "$R" || die "git archive"
  rm -rf "$R/backend/data/sound"
  mkdir -p "$R/backend/models/dgop_ours/aligner"
  for f in "$M8/aligner"/*; do cp -c "$f" "$R/backend/models/dgop_ours/aligner/"; done
  for f in coart_pod_eval.py v2_avatar_validity.py v18_protrusion.py; do cp "$APP/scripts/$f" "$R/scripts/" || die "$f"; done
  cp "$APP/scripts/v2_render/render_jobs.py" "$R/scripts/v2_render/" || die render_jobs
  cp "$HERE/run_v18.sh" "$R/" || die run_v18
  cp "$LAB/tools/extract_blendshapes.py" "$LAB/tools/face_landmarker.task" "$R/tools/" || die tools
  cp "$D/in/items_side.jsonl" "$D/in/jobs_v18.json" "$D/in/tables_v18.json" "$R/in/" || die in
  python3 - "$D/in/side_sel.json" "$R/clips" <<'PY' || die clips
import json, os, shutil, sys
sel = json.load(open(sys.argv[1], encoding="utf-8")); out = sys.argv[2]
for c in sel["clips"]:
    shutil.copyfile(c["mp4"], os.path.join(out, c["clip"] + ".mp4"))
    shutil.copyfile(c["wav"], os.path.join(out, c["clip"] + ".wav"))
print("CLIPS", len(sel["clips"]))
PY
  (cd "$R" && find . -type f ! -name expect.sha256 -print0 | sort -z | xargs -0 shasum -a 256) > "$R/expect.sha256"
  COPYFILE_DISABLE=1 tar --no-mac-metadata --no-xattrs --exclude .DS_Store --exclude '._*' -cf "$S/v18.tar" -C "$R" . || die tar
  ls -la "$S/v18.tar"
}
case "$CMD" in
  stage) do_stage; echo V18S_STAGE_OK ;;
  start)
    bash $P status | grep BALANCE
    do_stage
    step "파드 생성(워치독 ${WD_MIN}분)"
    created=0
    IFS=',' read -r -a CANDS <<< "$GPUS"
    for vc in ${MIN_VCPUS:-16 8}; do
      for cand in "${CANDS[@]}"; do
        g=${cand%%|*}; c=${cand#*|}
        step "후보 $g / $c (vCPU ≥ $vc)"
        if MIN_VCPU=$vc bash $P create "$g" "$c" --watchdog "$WD_MIN"; then created=1; break 2; fi
      done
    done
    [ "$created" = 1 ] || die "create"
    POD=$(awk -F= '$1 == "POD_ID" {print $2}' "$POD_STATE_DIR/.pod_state" 2>/dev/null)
    echo "V18S_POD $POD"
    retry 3 bash $P wait || { bash $P terminate --force || true; die wait; }
    step "올리기"
    retry 3 python3 pupload.py "$S/v18.tar" /workspace/v18.tar "$HERE/run_v18.sh" /workspace/run_v18.sh --chunk-mb 8 --par 24 > "$S/pupload.log" 2>&1
    tail -n 2 "$S/pupload.log"
    grep -q '^PUP_DONE ok=2 fail=0' "$S/pupload.log" || { bash $P terminate --force; die upload; }
    retry 3 bash $P ssh 'mkdir -p /workspace/v18 && cd /workspace/v18 && tar -xf ../v18.tar && sha256sum -c --quiet expect.sha256 && rm -f ../v18.tar && echo REMOTE_SHA_OK' | tee "$S/unpack.log"
    grep -q '^REMOTE_SHA_OK' "$S/unpack.log" || { bash $P terminate --force; die "unpack"; }
    retry 3 bash $P run "bash /workspace/run_v18.sh setup" || { bash $P terminate --force; die run; }
    echo V18S_STARTED ;;
  step) retry 3 bash $P run "bash /workspace/run_v18.sh $2" && echo V18S_STEP_STARTED || die step ;;
  log) retry 3 bash $P ssh "grep -E '^(V18_|ENVMP|ENVAPP|RJ_BENCH|RJ_DONE|RJ_WORKER_FAIL|EXTRACT_|=== )' /workspace/dax/logs/v18.log | tail -n ${2:-30}; tail -n 2 /workspace/dax/logs/v18.log" ;;
  wait)
    MK=$2; MAXM=${3:-60}; t0=$(date +%s)
    while :; do
      n=$(bash $P ssh "grep -c '^$MK' /workspace/dax/logs/v18.log" 2>/dev/null | tail -n 1)
      case "$n" in ''|*[!0-9]*) n=0 ;; esac
      if [ "$n" -ge 1 ]; then echo "V18S_WAIT_OK $MK"; break; fi
      f=$(bash $P ssh "grep -c '^V18_FAIL' /workspace/dax/logs/v18.log" 2>/dev/null | tail -n 1)
      case "$f" in ''|*[!0-9]*) f=0 ;; esac
      [ "$f" -ge 1 ] && die "파드 V18_FAIL"
      [ $(( $(date +%s) - t0 )) -ge $(( MAXM * 60 )) ] && die "wait $MK 시간 초과"
      sleep 30
    done ;;
  fetch)
    NAME=$2
    out="$LAB/data/pod_runs/$(date +%Y%m%d)_${POD:-unknown}/v18/$NAME"
    mkdir -p "$out"
    if [ "$NAME" = real ]; then SRC="side_bs align_side.jsonl"; DIR=/workspace/v18/out; else SRC="."; DIR=/workspace/v18/out/$NAME; fi
    ok=0
    for k in 1 2 3 4 5; do
      if bash $P ssh "cd $DIR && tar -czf - --exclude='*.mp4' --exclude='*.part.*' --exclude='*.tmp*' $SRC" | tar -xzf - -C "$out"; then ok=1; break; fi
      echo "V18S_FETCH_RETRY $k"; sleep $((k * 15))
    done
    [ "$ok" = 1 ] && echo "V18S_FETCH_OK $out" || die fetch ;;
  sh) retry 3 bash $P ssh "$2" ;;
  extend) bash $P extend "${2:-60}" ;;
  finish)
    retry 3 bash $P terminate --force || true
    bash $P status || true ;;
  *) echo "사용: $0 stage|start|step 'ARGS'|wait MARKER [MIN]|log|fetch NAME|sh CMD|extend MIN|finish"; exit 2 ;;
esac
