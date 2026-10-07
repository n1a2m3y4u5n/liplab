#!/bin/bash
# V15 입모양 표 보정 파드 세션(맥, 2026-10-07). 사전 등록: docs/viseme-calibration-2026-10.md(커밋 2bf2291).
#   v2_session.sh와 같은 틀(liplab-lab/tools/pod의 pod.sh·pupload.py를 쓴다). 상태 폴더 .v15state와 파드 이름 liplab-v15를 따로 써서
#   다른 세션과 섞이지 않게 한다. V1 받기(tools/v1_dl.sh와 감독 스크립트)는 건드리지 않는다.
#   사용자 회선이 잠깐씩 끊기므로 파드 작업은 모두 분리 실행(pod.sh run)하고, 맥 쪽 명령은 재시도하며, 결과는 단계마다 받는다.
#
#   bash v15_session.sh stage                    묶음(하네스 빌드, 원본 GLB, 추출기, in/의 작업)
#   [WD_MIN=225] bash v15_session.sh start       묶음 → 파드 → 올리기 → run_v15.sh setup(분리 실행)
#   bash v15_session.sh push FILE...             로컬 파일을 파드 /workspace/v15/in/으로(후보 표·작업 JSON)
#   bash v15_session.sh harness                  하네스만 다시 빌드해 올리기(앱 표를 바꾼 뒤 확인 렌더용)
#   bash v15_session.sh step 'render NAME JOBS [GLB|-] [TABLES]'   파드에서 run_v15.sh 단계 분리 실행
#   bash v15_session.sh log [N]                  표식 꼬리
#   bash v15_session.sh fetch NAME               out/NAME(영상 제외)을 data/pod_runs/<날짜>_<파드>/v15/NAME/로
#   bash v15_session.sh extend MIN               워치독 마감 = 지금 + MIN분
#   bash v15_session.sh finish                   종료 → 상태 확인(받을 것은 먼저 fetch)
set -uo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
APP=$(cd "$HERE/../.." && pwd)
LAB=${LAB:-$HOME/Downloads/liplab-lab}
CALLER=$PWD
cd "$LAB/tools/pod" || exit 1
P=pod.sh
export POD_STATE_DIR=${POD_STATE_DIR:-$LAB/tools/pod/.v15state} POD_NAME=${POD_NAME:-liplab-v15}
export POD_DISK_GB=${POD_DISK_GB:-40}
D=$LAB/data/v15
S=$D/stage
GPUS=${GPUS:-NVIDIA A40|SECURE,NVIDIA RTX A6000|SECURE,NVIDIA L40S|SECURE}
WD_MIN=${WD_MIN:-225}
mkdir -p "$S" "$LAB/data/pod_runs" "$POD_STATE_DIR"
CMD=${1:-}
LOG="$LAB/data/pod_runs/session_v15_${CMD}_$(date +%Y%m%d_%H%M).log"
exec > >(tee -a "$LOG") 2>&1
step() { echo "=== $(date '+%F %T') $*"; }
die() { echo "V15S_FAIL $*"; exit 1; }
POD=$(awk -F= '$1 == "POD_ID" {print $2}' "$POD_STATE_DIR/.pod_state" 2>/dev/null)
retry() {   # N CMD...: 짧은 망 끊김을 일시 오류로 보고 물러나며 다시 시도
  local n=$1 k=1; shift
  until "$@"; do [ "$k" -ge "$n" ] && return 1; echo "V15S_RETRY $k/$n"; sleep $((k * 15)); k=$((k + 1)); done
}
build_harness() {   # OUTDIR
  (cd "$APP/scripts/v2_render" && ../../frontend/node_modules/.bin/vite build --config vite.config.mjs --outDir "$1" --logLevel error) || die "harness build"
  git -C "$APP" show 9f08043:frontend/public/models/realistic_face.glb > "$1/orig_face.glb" || die "orig glb"
}
do_stage() {
  step "묶음"
  R=$S/root
  rm -rf "$R" && mkdir -p "$R/scripts/v2_render" "$R/tools" "$R/in" "$R/harness"
  build_harness "$R/harness"
  cp "$APP/scripts/v2_render/render_jobs.py" "$R/scripts/v2_render/" || die render_jobs
  cp "$APP/scripts/v15_pod/run_v15.sh" "$R/" || die run_v15
  cp "$LAB/tools/extract_blendshapes.py" "$LAB/tools/face_landmarker.task" "$R/tools/" || die tools
  cp "$D"/in/* "$R/in/" 2>/dev/null || true
  (cd "$R" && find . -type f ! -name expect.sha256 -print0 | sort -z | xargs -0 shasum -a 256) > "$R/expect.sha256"
  COPYFILE_DISABLE=1 tar --no-mac-metadata --no-xattrs --exclude .DS_Store --exclude '._*' -cf "$S/v15.tar" -C "$R" . || die tar
  ls -la "$S/v15.tar"
}

case "$CMD" in
  stage) do_stage; echo V15S_STAGE_OK ;;
  start)
    do_stage
    step "파드 생성(워치독 ${WD_MIN}분, 상태 $POD_STATE_DIR, 이름 $POD_NAME, 디스크 ${POD_DISK_GB}GB)"
    created=0
    IFS=',' read -r -a CANDS <<< "$GPUS"
    for vc in ${MIN_VCPUS:-16 8}; do
      for cand in "${CANDS[@]}"; do
        g=${cand%%|*}; c=${cand#*|}
        step "후보 $g / $c (vCPU ≥ $vc)"
        if MIN_VCPU=$vc bash $P create "$g" "$c" --watchdog "$WD_MIN"; then created=1; break 2; fi
      done
    done
    [ "$created" = 1 ] || die "create(모든 후보 실패, 파드 없음)"
    POD=$(awk -F= '$1 == "POD_ID" {print $2}' "$POD_STATE_DIR/.pod_state" 2>/dev/null)
    echo "V15S_POD $POD"
    retry 3 bash $P wait || { bash $P terminate --force || true; die wait; }
    step "올리기"
    retry 3 python3 pupload.py "$S/v15.tar" /workspace/v15.tar "$APP/scripts/v15_pod/run_v15.sh" /workspace/run_v15.sh --chunk-mb 8 --par 24 > "$S/pupload.log" 2>&1
    tail -n 2 "$S/pupload.log"
    grep -q '^PUP_DONE ok=2 fail=0' "$S/pupload.log" || { bash $P terminate --force; die upload; }
    retry 3 bash $P ssh 'mkdir -p /workspace/v15 && cd /workspace/v15 && tar -xf ../v15.tar && sha256sum -c --quiet expect.sha256 && rm -f ../v15.tar && echo REMOTE_SHA_OK' | tee "$S/unpack.log"
    grep -q '^REMOTE_SHA_OK' "$S/unpack.log" || { bash $P terminate --force; die "unpack"; }
    retry 3 bash $P run "bash /workspace/run_v15.sh setup" || { bash $P terminate --force; die run; }
    echo V15S_STARTED ;;
  push)
    shift
    args=()
    for f in "$@"; do case "$f" in /*) ;; *) f="$CALLER/$f" ;; esac; args+=("$f" "/workspace/v15/in/$(basename "$f")"); done
    retry 3 python3 pupload.py "${args[@]}" --chunk-mb 8 --par 16 > "$S/push.log" 2>&1
    tail -n 1 "$S/push.log"
    grep -q "^PUP_DONE ok=$# fail=0" "$S/push.log" && echo V15S_PUSH_OK || die push ;;
  harness)
    rm -rf "$S/harness_new" && build_harness "$S/harness_new"
    (cd "$S" && COPYFILE_DISABLE=1 tar --no-mac-metadata --no-xattrs -cf harness_new.tar -C harness_new .)
    retry 3 python3 pupload.py "$S/harness_new.tar" /workspace/harness_new.tar --chunk-mb 8 --par 16 > "$S/push.log" 2>&1
    grep -q '^PUP_DONE ok=1 fail=0' "$S/push.log" || die "harness upload"
    retry 3 bash $P ssh 'cd /workspace/v15 && rm -rf harness && mkdir harness && tar -xf ../harness_new.tar -C harness && ls harness/assets && echo HARNESS_OK' | tee "$S/harness.log"
    grep -q HARNESS_OK "$S/harness.log" && echo V15S_HARNESS_OK || die harness ;;
  step)
    retry 3 bash $P run "bash /workspace/run_v15.sh $2" && echo V15S_STEP_STARTED || die step ;;
  log)
    retry 3 bash $P ssh "grep -E '^(V15_|ENVMP|RJ_BENCH|RJ_DONE|RJ_WORKER_FAIL|EXTRACT_|=== )' /workspace/dax/logs/v15.log | tail -n ${2:-30}; tail -n 2 /workspace/dax/logs/v15.log" ;;
  fetch)
    NAME=$2
    out="$LAB/data/pod_runs/$(date +%Y%m%d)_${POD:-unknown}/v15/$NAME"
    mkdir -p "$out"
    ok=0
    for k in 1 2 3 4 5; do
      if bash $P ssh "cd /workspace/v15/out/$NAME && tar -czf - --exclude='*.mp4' --exclude='*.part.*' --exclude='*.tmp*' ." | tar -xzf - -C "$out"; then
        ok=1; break
      fi
      echo "V15S_FETCH_RETRY $k"; sleep $((k * 15))
    done
    [ "$ok" = 1 ] && echo "V15S_FETCH_OK $out $(ls "$out/bs" 2>/dev/null | wc -l | tr -d ' ') bs" || die fetch ;;
  sh) retry 3 bash $P ssh "$2" ;;
  wait)   # MARKER [MAX_MIN]: 파드 로그에 표식이 나올 때까지 30초마다 확인(끊기면 다음 차례에 다시)
    MK=$2; MAXM=${3:-60}; t0=$(date +%s)
    while :; do
      n=$(bash $P ssh "grep -c '^$MK' /workspace/dax/logs/v15.log" 2>/dev/null | tail -n 1)
      case "$n" in ''|*[!0-9]*) n=0 ;; esac
      if [ "$n" -ge 1 ]; then echo "V15S_WAIT_OK $MK"; break; fi
      if bash $P ssh "grep -c '^V15_FAIL' /workspace/dax/logs/v15.log" 2>/dev/null | tail -n 1 | grep -qv '^0$'; then echo "V15S_WAIT_SAW_FAIL"; fi
      [ $(( $(date +%s) - t0 )) -ge $(( MAXM * 60 )) ] && die "wait $MK 시간 초과"
      sleep 30
    done ;;
  extend) bash $P extend "${2:-60}" ;;
  finish)
    retry 3 bash $P terminate --force || true
    bash $P status || true ;;
  *) echo "사용: $0 stage|start|push FILE...|harness|step 'ARGS'|log|fetch NAME|extend MIN|finish"; exit 2 ;;
esac
