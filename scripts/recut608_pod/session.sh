#!/bin/bash
# 608 다시 자르기 파드 세션(맥, docs/scoring-608-recut-2026-10.md). 파드는 liplab-lab의 tools/pod/pod.sh로만 다룬다.
#   bash scripts/recut608_pod/session.sh stage    묶음(파드 없음): b675975 backend, 지금 backend, 스크립트, 작업 목록, 608 세션·538 표본 소리
#   bash scripts/recut608_pod/session.sh launch   파드 생성(워치독) → wait(자폭 타이머) → 올리기 → sha256 → run.sh
#   bash scripts/recut608_pod/session.sh tail     파드 로그 끝부분
#   bash scripts/recut608_pod/session.sh finish   결과 받기 → terminate → status
# 상태 폴더 .rcstate, 파드 이름 liplab-rc. RunPod 키는 pod.sh가 ~/.runpod/config.toml에서 메모리로만 읽는다.
# 538·608 원자료는 lab 묶음 폴더와 파드에만 두고 앱 저장소에 넣지 않는다. 다른 작업의 파드는 건드리지 않는다.
set -uo pipefail
APP=$(cd "$(dirname "$0")/../.." && pwd)
LAB=${LAB:-$HOME/Downloads/liplab-lab}
P="$LAB/tools/pod/pod.sh"
export POD_STATE_DIR=${POD_STATE_DIR:-$LAB/tools/pod/.rcstate} POD_NAME=${POD_NAME:-liplab-rc} POD_DISK_GB=${POD_DISK_GB:-50}
export DEADMAN_GRACE_MIN=${DEADMAN_GRACE_MIN:-15}
M8=${M8:-$LAB/models/dgop_ours_2026-09-25_int8}
ONNX=${ONNX:-$LAB/models/s4_student_2026-10-07/H/student_w8.onnx}
S=${STAGE_DIR:-$LAB/data/rc_stage}
GPUS=${GPUS:-NVIDIA A40|SECURE,NVIDIA RTX A6000|SECURE,NVIDIA L40S|SECURE}
WD_MIN=${WD_MIN:-90}
SHA_ALIGNER=18681947f740b7486f8fa4f93c7c0f68fe1595ac4fa9822800dfd38d713f5e66
SHA_SCORER=e8340d58dd911e380eca508815526eb77ec658560456ce1fe4c16b9b6e3654c4
mkdir -p "$S" "$LAB/data/pod_runs" "$POD_STATE_DIR"
CMD=${1:-}
LOG="$LAB/data/pod_runs/session_rc_${CMD}_$(date +%Y%m%d_%H%M).log"
exec > >(tee -a "$LOG") 2>&1
step() { echo "=== $(date '+%F %T') $*"; }
die() { echo "RCS_FAIL $*"; exit 1; }
pod_id() { awk -F= '$1 == "POD_ID" {print $2}' "$POD_STATE_DIR/.pod_state" 2>/dev/null; }
sha_of() { shasum -a 256 "$1" | cut -d' ' -f1; }

do_stage() {
  step "가중치 확인"
  [ "$(sha_of "$M8/aligner/model.int8.safetensors")" = "$SHA_ALIGNER" ] || die "정렬기 sha256"
  [ "$(sha_of "$M8/scorer/model.int8.safetensors")" = "$SHA_SCORER" ] || die "채점기 sha256"
  [ -s "$ONNX" ] || die "학생 ONNX 없음"
  step "묶음"
  R=$S/root
  rm -rf "$R" && mkdir -p "$R/backend_new/data" "$R/scripts" "$R/tools" "$R/data/hi608/wav16" "$R/data/c538wav" "$R/models"
  git -C "$APP" archive b675975 backend | tar -x -C "$R" || die "git archive b675975"
  cp "$APP"/backend/*.py "$R/backend_new/" || die backend_new
  cp "$APP"/backend/data/dgop_calibration*.json "$R/backend_new/data/" || die calibration
  for bk in backend backend_new; do
    for m in aligner scorer; do
      mkdir -p "$R/$bk/models/dgop_ours/$m"
      for f in "$M8/$m"/*; do case "$(basename "$f")" in model.int8.safetensors|model.safetensors) ;; *) cp "$f" "$R/$bk/models/dgop_ours/$m/" ;; esac; done
    done
  done
  git -C "$APP" show b675975:scripts/speak_asr_pod_run.py > "$R/scripts/speak_asr_pod_run.py" || die asr_script
  git -C "$APP" show b675975:scripts/speak_collapse.py > "$R/scripts/speak_collapse.py" || die collapse
  cp "$APP/scripts/s4_eval_pod.py" "$APP/scripts/recut608_pod/recut.py" "$APP/scripts/recut608_pod/run.sh" "$R/scripts/" || die scripts
  cp "$LAB/tools/scores_1006.py" "$R/tools/" || die scores_1006
  python3 "$APP/scripts/recut608_pod/build.py" "$R/data" || die build
  python3 - "$R/data" "$LAB" <<'EOF' || die "소리 복사"
import json, shutil, sys
d, lab = sys.argv[1:3]
need = json.load(open(f"{d}/need.json"))
for c in need["c538"]:
    shutil.copy(f"{lab}/data/s12stage/root/c538wav/{c}.wav", f"{d}/c538wav/")
for f in need["sessions"]:
    shutil.copy(f"{lab}/data/s12stage/root/hi608/wav16/{f}", f"{d}/hi608/wav16/")
print("COPIED c538", len(need["c538"]), "sessions", len(need["sessions"]))
EOF
  ( cd "$R" && find backend backend_new scripts tools data -type f | sort | xargs shasum -a 256 ) > "$R/expect.sha256"
  for bk in backend backend_new; do
    printf '%s  %s/models/dgop_ours/aligner/model.int8.safetensors\n%s  %s/models/dgop_ours/scorer/model.int8.safetensors\n' \
      "$SHA_ALIGNER" "$bk" "$SHA_SCORER" "$bk" >> "$R/expect.sha256"
  done
  printf '%s  models/student_w8.onnx\n' "$(sha_of "$ONNX")" >> "$R/expect.sha256"
  COPYFILE_DISABLE=1 tar --no-mac-metadata --no-xattrs --exclude .DS_Store --exclude '._*' -cf "$S/rc.tar" -C "$R" . || die tar
  ls -la "$S/rc.tar"
  echo "RCS_STAGE_OK"
}

do_launch() {
  [ -s "$S/rc.tar" ] || die "묶음 없음(stage 먼저)"
  step "잔액·파드 목록"
  bash "$P" status || true
  step "파드 생성(워치독 ${WD_MIN}분, 상태 $POD_STATE_DIR, 이름 $POD_NAME, 디스크 ${POD_DISK_GB}GB)"
  created=0
  IFS=',' read -r -a CANDS <<< "$GPUS"
  for cand in "${CANDS[@]}"; do
    g=${cand%%|*}; c=${cand#*|}
    step "후보 $g / $c"
    if bash "$P" create "$g" "$c" --watchdog "$WD_MIN"; then created=1; break; fi
  done
  [ "$created" = 1 ] || die "create(모든 후보 실패, 파드 없음)"
  echo "RCS_POD $(pod_id)"
  bash "$P" wait || { bash "$P" terminate --force || true; die wait; }
  bash "$P" ssh 'nproc; cat /sys/fs/cgroup/cpu.max 2>/dev/null; free -g | head -2; df -h /workspace | tail -1; nvidia-smi --query-gpu=name,memory.total --format=csv,noheader'
  step "올리기"
  python3 "$LAB/tools/pod/pupload.py" "$S/rc.tar" /workspace/rc.tar "$M8/aligner/model.int8.safetensors" /workspace/aligner.int8 \
    "$M8/scorer/model.int8.safetensors" /workspace/scorer.int8 "$ONNX" /workspace/student_w8.onnx \
    --chunk-mb 8 --par 24 > "$S/pupload.log" 2>&1
  PUP_RC=$?
  tail -n 4 "$S/pupload.log"
  { [ "$PUP_RC" = 0 ] && grep -q '^PUP_DONE ok=4 fail=0' "$S/pupload.log"; } || { bash "$P" terminate --force || true; die "upload(rc=$PUP_RC)"; }
  bash "$P" ssh 'mkdir -p /workspace/rc && cd /workspace/rc && tar -xf ../rc.tar && rm -f ../rc.tar && for bk in backend backend_new; do cp ../aligner.int8 $bk/models/dgop_ours/aligner/model.int8.safetensors && cp ../scorer.int8 $bk/models/dgop_ours/scorer/model.int8.safetensors; done && mv ../student_w8.onnx models/student_w8.onnx && rm -f ../aligner.int8 ../scorer.int8 && sha256sum -c --quiet expect.sha256 && echo REMOTE_SHA_OK' \
    | tee "$S/unpack.log" || { bash "$P" terminate --force || true; die "풀기"; }
  grep -q '^REMOTE_SHA_OK' "$S/unpack.log" || { bash "$P" terminate --force || true; die "sha256 불일치"; }
  step "run.sh 시작"
  bash "$P" run 'bash /workspace/rc/scripts/run.sh' || { bash "$P" terminate --force || true; die run; }
  echo "RCS_LAUNCH_OK $(pod_id)"
}

do_fetch() {
  POD=$(pod_id)
  [ -n "$POD" ] || die "파드 없음"
  out="$LAB/data/pod_runs/$(date +%Y%m%d)_${POD}/rc"
  mkdir -p "$out"
  if bash "$P" ssh 'test -s /workspace/rc_result.tgz && grep -q "^RC_OK" /workspace/dax/logs/rc.log'; then
    bash "$P" ssh 'cat /workspace/rc_result.tgz' > "$out/result.tgz" && tar -xzf "$out/result.tgz" -C "$out" && echo "RCS_FETCH_OK $out" || echo "RCS_FETCH_WARN"
  else
    bash "$P" ssh 'cd /workspace/rc && tar -czf - out/*.json out/*.jsonl ../dax/logs/*.log 2>/dev/null' | tar -xzf - -C "$out" && echo "RCS_FETCH_PARTIAL $out" || echo "RCS_FETCH_WARN"
  fi
  ls -la "$out" "$out/out" 2>/dev/null | tail -20
}

case "$CMD" in
  stage) do_stage ;;
  launch) do_launch ;;
  tail) bash "$P" ssh 'tail -n 30 /workspace/dax/logs/rc.log' ;;
  fetch) do_fetch ;;
  finish) do_fetch; bash "$P" terminate --force || true; bash "$P" status || true ;;
  *) echo "session.sh stage|launch|tail|fetch|finish"; exit 2 ;;
esac
