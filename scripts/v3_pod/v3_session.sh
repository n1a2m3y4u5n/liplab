#!/bin/bash
# V3 간이판 파드 세션(맥, 2026-10-15). 사전 등록: docs/avatar-v3-2026-10.md(커밋 2fdcd1ea).
#   V18 세션 틀(liplab-lab/tools/pod의 pod.sh·pupload.py). 상태 폴더 .v3state, 파드 이름 liplab-v3로 다른 세션과 섞이지 않게 한다.
#   맥 부하를 줄이려고 분석(표 만들기·판독기·V2 지표)도 파드에서 한다. 맥은 묶음·작업 JSON·결과 받기만.
#   bash v3_session.sh stage            묶음(하네스, 스크립트, 정렬기, 탐색 자료, 확인 클립, 작업)
#   [WD_MIN=150] bash v3_session.sh start   묶음 → 파드 → 올리기 → run_v3.sh setup(분리 실행)
#   bash v3_session.sh push FILE...     로컬 파일을 /workspace/v3/in/으로
#   bash v3_session.sh harness          하네스만 다시 빌드해 올리기(동결 표를 앱 모듈에 넣은 뒤)
#   bash v3_session.sh step 'ARGS'      run_v3.sh 단계 분리 실행
#   bash v3_session.sh wait MARKER [MIN] | log [N] | fetch PATH | sh CMD | extend MIN | finish
set -uo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
APP=$(cd "$HERE/../.." && pwd)
LAB=${LAB:-$HOME/Downloads/LIPLAB_ALL/liplab-lab}
CALLER=$PWD
cd "$LAB/tools/pod" || exit 1
P=pod.sh
export POD_STATE_DIR=${POD_STATE_DIR:-$LAB/tools/pod/.v3state} POD_NAME=${POD_NAME:-liplab-v3}
export POD_DISK_GB=${POD_DISK_GB:-40}
D=$LAB/data/v3_avatar
S=$D/stage
M8=$LAB/models/dgop_ours_2026-09-25_int8
SHA_ALIGNER=18681947f740b7486f8fa4f93c7c0f68fe1595ac4fa9822800dfd38d713f5e66
RUN2=$LAB/data/pod_runs/20261006_oel3rwn7y5zjbv/v2_part2/out
V2F=$LAB/data/pod_runs/20261007_czde54612e5kcu/v2_final/out
V15X=$LAB/data/pod_runs/20261007_zszjqyqz5m03q2/v15/ex_D
GPUS=${GPUS:-NVIDIA A40|SECURE,NVIDIA RTX A6000|SECURE,NVIDIA L40S|SECURE}
WD_MIN=${WD_MIN:-150}
mkdir -p "$S" "$LAB/data/pod_runs" "$POD_STATE_DIR"
CMD=${1:-}
LOG="$LAB/data/pod_runs/session_v3_${CMD}_$(date +%Y%m%d_%H%M).log"
exec > >(tee -a "$LOG") 2>&1
step() { echo "=== $(date '+%F %T') $*"; }
die() { echo "V3S_FAIL $*"; exit 1; }
POD=$(awk -F= '$1 == "POD_ID" {print $2}' "$POD_STATE_DIR/.pod_state" 2>/dev/null)
retry() {
  local n=$1 k=1; shift
  until "$@"; do [ "$k" -ge "$n" ] && return 1; echo "V3S_RETRY $k/$n"; sleep $((k * 15)); k=$((k + 1)); done
}
NICE="nice -n 20"
build_harness() {   # OUTDIR
  (cd "$APP/scripts/v2_render" && $NICE ../../frontend/node_modules/.bin/vite build --config vite.config.mjs --outDir "$1" --logLevel error) || die "harness build"
}
do_stage() {
  step "묶음"
  [ "$(shasum -a 256 "$M8/aligner/model.int8.safetensors" | cut -d' ' -f1)" = "$SHA_ALIGNER" ] || die "정렬기 sha256"
  R=$S/root
  rm -rf "$R" && mkdir -p "$R/scripts/v2_render" "$R/scripts/data" "$R/tools" "$R/in" "$R/harness" "$R/clips" "$R/ex"
  build_harness "$R/harness"
  git -C "$APP" archive HEAD backend | tar -x -C "$R" || die "git archive"
  rm -rf "$R/backend/data/sound"
  mkdir -p "$R/backend/models/dgop_ours/aligner"
  for f in "$M8/aligner"/*; do cp -c "$f" "$R/backend/models/dgop_ours/aligner/"; done
  for f in coart_pod_eval.py v2_avatar_validity.py v15_calibrate.py v3_avatar.py; do cp "$APP/scripts/$f" "$R/scripts/" || die "$f"; done
  cp "$APP/scripts/data/viseme_v15.json" "$R/scripts/data/" || die v15json
  cp "$APP/scripts/v2_render/render_jobs.py" "$R/scripts/v2_render/" || die render_jobs
  cp "$HERE/run_v3.sh" "$R/" || die run_v3
  cp "$LAB/tools/extract_blendshapes.py" "$LAB/tools/face_landmarker.task" "$R/tools/" || die tools
  cp "$LAB/data/v2_avatar/sel.json" "$R/ex/sel.json" && cp "$RUN2/align_real.jsonl" "$R/ex/align_real.jsonl" || die ex
  cp "$D/sel_confirm.json" "$D/items_confirm.jsonl" "$R/in/" || die confirm_sel
  cp "$D"/in/* "$R/in/" 2>/dev/null || true
  # 탐색 자료(JSON이라 묶어 압축): 실제 900클립 추출, 지금 표(V2) 기본 얼굴 렌더, V15 표 D 탐색 렌더
  (cd "$RUN2" && COPYFILE_DISABLE=1 $NICE tar -czf "$R/ex/bs_real.tgz" bs_real) || die bs_real
  (cd "$V2F" && ls renders | grep -E '^txt_.*_default_[12]\.0\.sched\.json$' > "$S/v1_list.txt" && \
     sed 's/\.sched\.json$/.json/; s#^#bs_render/#' "$S/v1_list.txt" > "$S/v1_bs.txt" && sed 's#^#renders/#' "$S/v1_list.txt" >> "$S/v1_bs.txt" && \
     COPYFILE_DISABLE=1 $NICE tar -czf "$R/ex/v1_ex.tgz" -T "$S/v1_bs.txt") || die v1
  (cd "$V15X" && COPYFILE_DISABLE=1 $NICE tar -czf "$R/ex/v15_ex.tgz" renders bs) || die v15
  python3 - "$D/sel_confirm.json" "$R/clips" <<'PY' || die clips
import json, os, shutil, sys
sel = json.load(open(sys.argv[1], encoding="utf-8")); out = sys.argv[2]
for c in sel["clips"]:
    shutil.copyfile(c["mp4"], os.path.join(out, c["clip"] + ".mp4"))
    shutil.copyfile(c["wav"], os.path.join(out, c["clip"] + ".wav"))
print("CLIPS", len(sel["clips"]))
PY
  (cd "$R" && find . -type f ! -name expect.sha256 -print0 | sort -z | xargs -0 shasum -a 256) > "$R/expect.sha256"
  COPYFILE_DISABLE=1 tar --no-mac-metadata --no-xattrs --exclude .DS_Store --exclude '._*' -cf "$S/v3.tar" -C "$R" . || die tar
  ls -la "$S/v3.tar"
}
case "$CMD" in
  stage) do_stage; echo V3S_STAGE_OK ;;
  start)
    bash $P status | grep -E 'BALANCE|STATUS'
    [ -f "$S/v3.tar" ] || do_stage
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
    echo "V3S_POD $POD"
    retry 3 bash $P wait || { bash $P terminate --force || true; die wait; }
    step "올리기"
    retry 3 python3 pupload.py "$S/v3.tar" /workspace/v3.tar "$HERE/run_v3.sh" /workspace/run_v3.sh --chunk-mb 8 --par 24 > "$S/pupload.log" 2>&1
    tail -n 2 "$S/pupload.log"
    grep -q '^PUP_DONE ok=2 fail=0' "$S/pupload.log" || { bash $P terminate --force; die upload; }
    retry 3 bash $P ssh 'mkdir -p /workspace/v3 && cd /workspace/v3 && tar -xf ../v3.tar && sha256sum -c --quiet expect.sha256 && rm -f ../v3.tar && echo REMOTE_SHA_OK' | tee "$S/unpack.log"
    grep -q '^REMOTE_SHA_OK' "$S/unpack.log" || { bash $P terminate --force; die "unpack"; }
    retry 3 bash $P run "bash /workspace/run_v3.sh setup" || { bash $P terminate --force; die run; }
    echo V3S_STARTED ;;
  push)
    shift
    args=()
    for f in "$@"; do case "$f" in /*) ;; *) f="$CALLER/$f" ;; esac; args+=("$f" "/workspace/v3/in/$(basename "$f")"); done
    retry 3 python3 pupload.py "${args[@]}" --chunk-mb 8 --par 16 > "$S/push.log" 2>&1
    tail -n 1 "$S/push.log"
    grep -q "^PUP_DONE ok=$# fail=0" "$S/push.log" && echo V3S_PUSH_OK || die push ;;
  harness)
    rm -rf "$S/harness_new" && build_harness "$S/harness_new"
    (cd "$S" && COPYFILE_DISABLE=1 tar --no-mac-metadata --no-xattrs -cf harness_new.tar -C harness_new .)
    retry 3 python3 pupload.py "$S/harness_new.tar" /workspace/harness_new.tar "$APP/scripts/v3_avatar.py" /workspace/v3/scripts/v3_avatar.py --chunk-mb 8 --par 16 > "$S/push.log" 2>&1
    grep -q '^PUP_DONE ok=2 fail=0' "$S/push.log" || die "harness upload"
    retry 3 bash $P ssh 'cd /workspace/v3 && rm -rf harness && mkdir harness && tar -xf ../harness_new.tar -C harness && ls harness/assets && echo HARNESS_OK' | tee "$S/harness.log"
    grep -q HARNESS_OK "$S/harness.log" && echo V3S_HARNESS_OK || die harness ;;
  step) retry 3 bash $P run "bash /workspace/run_v3.sh $2" && echo V3S_STEP_STARTED || die step ;;
  log) retry 3 bash $P ssh "grep -E '^(V3_|ENVMP|ENVAPP|RJ_BENCH|RJ_DONE|RJ_WORKER_FAIL|EXTRACT_|EVALUATE|VERDICT|FIT|HUMAN|CLASSIFIER|DATASET|JOBS|TABLES|  [a-z0-9]|=== )' /workspace/dax/logs/v3.log | tail -n ${2:-40}; tail -n 2 /workspace/dax/logs/v3.log" ;;
  wait)
    MK=$2; MAXM=${3:-60}; t0=$(date +%s)
    while :; do
      n=$(bash $P ssh "grep -c '^$MK' /workspace/dax/logs/v3.log" 2>/dev/null | tail -n 1)
      case "$n" in ''|*[!0-9]*) n=0 ;; esac
      if [ "$n" -ge 1 ]; then echo "V3S_WAIT_OK $MK"; break; fi
      f=$(bash $P ssh "grep -c '^V3_FAIL' /workspace/dax/logs/v3.log" 2>/dev/null | tail -n 1)
      case "$f" in ''|*[!0-9]*) f=0 ;; esac
      [ "$f" -ge 1 ] && die "파드 V3_FAIL"
      [ $(( $(date +%s) - t0 )) -ge $(( MAXM * 60 )) ] && die "wait $MK 시간 초과"
      sleep 30
    done ;;
  fetch)   # PATH(/workspace/v3/out 기준, 영상 제외)
    NAME=$2
    out="$LAB/data/pod_runs/$(date +%Y%m%d)_${POD:-unknown}/v3"
    mkdir -p "$out"
    ok=0
    for k in 1 2 3 4 5; do
      if bash $P ssh "cd /workspace/v3/out && tar -czf - --exclude='*.mp4' --exclude='*.part.*' --exclude='*.tmp*' $NAME" | tar -xzf - -C "$out"; then ok=1; break; fi
      echo "V3S_FETCH_RETRY $k"; sleep $((k * 15))
    done
    [ "$ok" = 1 ] && echo "V3S_FETCH_OK $out/$NAME" || die fetch ;;
  sh) retry 3 bash $P ssh "$2" ;;
  extend) bash $P extend "${2:-60}" ;;
  finish)
    retry 3 bash $P terminate --force || true
    bash $P status || true ;;
  *) echo "사용: $0 stage|start|push|harness|step 'ARGS'|wait MARKER [MIN]|log|fetch PATH|sh CMD|extend MIN|finish"; exit 2 ;;
esac
