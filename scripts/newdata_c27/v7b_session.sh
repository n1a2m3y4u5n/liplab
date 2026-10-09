#!/bin/bash
# V7b 파드 세션(맥, 2026-10-09). 등록: docs/v7-clear-speech-2026-10.md 7.3·7.4절, docs/newdata-608c27-538-2026-10.md 3절.
#   bash v7b_session.sh stage LIST     LIST(클립 이름 한 줄에 하나, v7b_read_spont.py select --list)의 mp4를 묶는다
#   bash v7b_session.sh launch         파드 → 올리기 → run_v7b.sh → 끝까지 기다림 → 받기 → terminate → status
# 상태 폴더 .v7bstate, 파드 이름 liplab-v7b. 538 클립은 lab 묶음(data/v18/v7b_stage)과 파드에만 둔다.
set -uo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
LAB=${LAB:-$HOME/Downloads/liplab-lab}
P="$LAB/tools/pod/pod.sh"
export POD_STATE_DIR=${POD_STATE_DIR:-$LAB/tools/pod/.v7bstate} POD_NAME=${POD_NAME:-liplab-v7b} POD_DISK_GB=${POD_DISK_GB:-30}
export DEADMAN_GRACE_MIN=${DEADMAN_GRACE_MIN:-15}
S=$LAB/data/v18/v7b_stage
GPUS=${GPUS:-NVIDIA A40|SECURE,NVIDIA RTX A6000|SECURE,NVIDIA L40S|SECURE}
WD_MIN=${WD_MIN:-75}
mkdir -p "$S" "$LAB/data/pod_runs" "$POD_STATE_DIR"
CMD=${1:-}
LOG="$LAB/data/pod_runs/session_v7b_${CMD}_$(date +%Y%m%d_%H%M).log"
exec > >(tee -a "$LOG") 2>&1
step() { echo "=== $(date '+%F %T') $*"; }
die() { echo "V7BS_FAIL $*"; exit 1; }
pod_id() { awk -F= '$1 == "POD_ID" {print $2}' "$POD_STATE_DIR/.pod_state" 2>/dev/null; }
case "$CMD" in
  stage)
    LIST=$2
    R=$S/root
    rm -rf "$R" && mkdir -p "$R/tools" "$R/clips"
    cp "$LAB/tools/extract_blendshapes.py" "$LAB/tools/face_landmarker.task" "$R/tools/" || die tools
    cp "$HERE/run_v7b.sh" "$R/" || die run
    n=0
    while read -r c; do
      [ -n "$c" ] || continue
      src=""
      for d in "$LAB/data/v18/v7b_dl2/clips" "$LAB/data/v18/v7b_dl/clips"; do [ -s "$d/$c.mp4" ] && { src="$d/$c.mp4"; break; }; done
      [ -n "$src" ] || die "클립 없음 $c"
      cp -c "$src" "$R/clips/$c.mp4" && n=$((n + 1))
    done < "$LIST"
    (cd "$R" && find . -type f ! -name expect.sha256 -print0 | sort -z | xargs -0 shasum -a 256) > "$R/expect.sha256"
    COPYFILE_DISABLE=1 tar --no-mac-metadata --no-xattrs --exclude .DS_Store --exclude '._*' -cf "$S/v7b.tar" -C "$R" . || die tar
    ls -la "$S/v7b.tar"; echo "V7BS_STAGE_OK clips=$n" ;;
  launch)
    [ -s "$S/v7b.tar" ] || die "묶음 없음"
    bash "$P" status || true
    created=0
    IFS=',' read -r -a CANDS <<< "$GPUS"
    for cand in "${CANDS[@]}"; do
      g=${cand%%|*}; c=${cand#*|}
      step "후보 $g / $c"
      if bash "$P" create "$g" "$c" --watchdog "$WD_MIN"; then created=1; break; fi
    done
    [ "$created" = 1 ] || die create
    echo "V7BS_POD $(pod_id)"
    bash "$P" wait || { bash "$P" terminate --force || true; die wait; }
    python3 "$LAB/tools/pod/pupload.py" "$S/v7b.tar" /workspace/v7b.tar --chunk-mb 8 --par 24 > "$S/pupload.log" 2>&1
    grep -q '^PUP_DONE ok=1 fail=0' "$S/pupload.log" || { bash "$P" terminate --force || true; die upload; }
    bash "$P" ssh 'mkdir -p /workspace/v7b && cd /workspace/v7b && tar -xf ../v7b.tar && rm -f ../v7b.tar && sha256sum -c --quiet expect.sha256 && echo REMOTE_SHA_OK' | tee "$S/unpack.log"
    grep -q '^REMOTE_SHA_OK' "$S/unpack.log" || { bash "$P" terminate --force || true; die unpack; }
    bash "$P" run 'bash /workspace/v7b/run_v7b.sh' || { bash "$P" terminate --force || true; die run; }
    WAITFOR_MAX_MIN=${WAIT_MAX:-60} WAIT_POLL=30 bash "$P" waitfor V7B_OK logs/v7b.log
    WRC=$?
    out="$LAB/data/pod_runs/$(date +%Y%m%d)_$(pod_id)/v7b"
    mkdir -p "$out"
    bash "$P" ssh 'grep -E "^(ENVMP|V7B_|EXTRACT|===)" /workspace/dax/logs/v7b.log | tail -n 20' || true
    bash "$P" ssh 'cd /workspace/v7b/out && tar -czf - bs' > "$out/result.tgz" && tar -xzf "$out/result.tgz" -C "$out" && echo "V7BS_FETCH_OK $out $(ls "$out/bs" | wc -l)" || echo V7BS_FETCH_WARN
    bash "$P" terminate --force || true
    bash "$P" status || true
    [ "$WRC" = 0 ] && echo V7BS_DONE || die "waitfor rc=$WRC" ;;
  finish) bash "$P" terminate --force || true; bash "$P" status || true ;;
  *) echo "v7b_session.sh stage LIST | launch | finish"; exit 2 ;;
esac
