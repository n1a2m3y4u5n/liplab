#!/bin/bash
# 608 새 화자 확인 파드 세션(맥, docs/scoring-608-newspk-2026-10.md). 파드는 liplab-lab의 tools/pod/pod.sh로만 다룬다.
#   bash scripts/newspk608_pod/session.sh stage    묶음(파드 없음): b675975 backend, 지금 backend, 스크립트, build.py가 만든 작업 목록·소리
#   bash scripts/newspk608_pod/session.sh launch   파드 생성(워치독) → wait(자폭 타이머) → 올리기 → sha256 → run.sh
#   bash scripts/newspk608_pod/session.sh tail     파드 로그 끝부분
#   bash scripts/newspk608_pod/session.sh finish   결과 받기 → terminate → status
# 상태 폴더 .nsstate, 파드 이름 liplab-ns. RunPod 키는 pod.sh가 ~/.runpod/config.toml에서 메모리로만 읽는다.
# 538·608 원자료는 lab 묶음 폴더와 파드에만 두고 앱 저장소에 넣지 않는다. 다른 작업의 파드는 건드리지 않는다.
set -uo pipefail
APP=$(cd "$(dirname "$0")/../.." && pwd)
LAB=${LAB:-$HOME/Downloads/liplab-lab}
P="$LAB/tools/pod/pod.sh"
export POD_STATE_DIR=${POD_STATE_DIR:-$LAB/tools/pod/.nsstate} POD_NAME=${POD_NAME:-liplab-ns} POD_DISK_GB=${POD_DISK_GB:-40}
export DEADMAN_GRACE_MIN=${DEADMAN_GRACE_MIN:-15}
M8=${M8:-$LAB/models/dgop_ours_2026-09-25_int8}
S=${STAGE_DIR:-$LAB/data/ns_stage}
GPUS=${GPUS:-NVIDIA A40|SECURE,NVIDIA RTX A6000|SECURE,NVIDIA L40S|SECURE}
WD_MIN=${WD_MIN:-90}
NEW_REV=${NEW_REV:-a57ee690}
SHA_ALIGNER=18681947f740b7486f8fa4f93c7c0f68fe1595ac4fa9822800dfd38d713f5e66
SHA_SCORER=e8340d58dd911e380eca508815526eb77ec658560456ce1fe4c16b9b6e3654c4
mkdir -p "$S" "$LAB/data/pod_runs" "$POD_STATE_DIR"
CMD=${1:-}
LOG="$LAB/data/pod_runs/session_ns_${CMD}_$(date +%Y%m%d_%H%M).log"
exec > >(tee -a "$LOG") 2>&1
step() { echo "=== $(date '+%F %T') $*"; }
die() { echo "NSS_FAIL $*"; exit 1; }
pod_id() { awk -F= '$1 == "POD_ID" {print $2}' "$POD_STATE_DIR/.pod_state" 2>/dev/null; }
sha_of() { shasum -a 256 "$1" | cut -d' ' -f1; }

do_stage() {
  step "가중치 확인"
  [ "$(sha_of "$M8/aligner/model.int8.safetensors")" = "$SHA_ALIGNER" ] || die "정렬기 sha256"
  [ "$(sha_of "$M8/scorer/model.int8.safetensors")" = "$SHA_SCORER" ] || die "채점기 sha256"
  R=$S/root
  [ -s "$R/data/jobs.json" ] || die "작업 목록 없음(build.py 먼저)"
  step "묶음"
  rm -rf "$R/backend" "$R/backend_new" "$R/scripts" "$R/tools" && mkdir -p "$R/backend_new" "$R/scripts" "$R/tools"
  git -C "$APP" archive b675975 backend | tar -x -C "$R" || die "git archive b675975"
  git -C "$APP" archive "$NEW_REV" backend | tar -x -C "$R/backend_new" --strip-components=1 || die "git archive $NEW_REV"
  rm -rf "$R/backend_new/data/sound" "$R/backend/data/sound"
  for bk in backend backend_new; do
    for m in aligner scorer; do
      mkdir -p "$R/$bk/models/dgop_ours/$m"
      for f in "$M8/$m"/*; do case "$(basename "$f")" in model.int8.safetensors|model.safetensors) ;; *) cp "$f" "$R/$bk/models/dgop_ours/$m/" ;; esac; done
    done
  done
  git -C "$APP" show b675975:scripts/speak_asr_pod_run.py > "$R/scripts/speak_asr_pod_run.py" || die asr_script
  git -C "$APP" show b675975:scripts/speak_collapse.py > "$R/scripts/speak_collapse.py" || die collapse
  cp "$APP/scripts/newspk608_pod/newspk.py" "$APP/scripts/newspk608_pod/run.sh" "$R/scripts/" || die scripts
  cp "$LAB/tools/scores_1006.py" "$R/tools/" || die scores_1006
  ( cd "$R" && find backend backend_new scripts tools data -type f | sort | xargs shasum -a 256 ) > "$R/expect.sha256"
  for bk in backend backend_new; do
    printf '%s  %s/models/dgop_ours/aligner/model.int8.safetensors\n%s  %s/models/dgop_ours/scorer/model.int8.safetensors\n' \
      "$SHA_ALIGNER" "$bk" "$SHA_SCORER" "$bk" >> "$R/expect.sha256"
  done
  COPYFILE_DISABLE=1 tar --no-mac-metadata --no-xattrs --exclude .DS_Store --exclude '._*' -cf "$S/ns.tar" -C "$R" . || die tar
  ls -la "$S/ns.tar"
  echo "NSS_STAGE_OK"
}

do_launch() {
  [ -s "$S/ns.tar" ] || die "묶음 없음(stage 먼저)"
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
  echo "NSS_POD $(pod_id)"
  bash "$P" wait || { bash "$P" terminate --force || true; die wait; }
  bash "$P" ssh 'nproc; cat /sys/fs/cgroup/cpu.max 2>/dev/null; cat /sys/fs/cgroup/cpu/cpu.cfs_quota_us 2>/dev/null; free -g | head -2; df -h /workspace | tail -1; nvidia-smi --query-gpu=name,memory.total --format=csv,noheader; grep -m1 "model name" /proc/cpuinfo'
  step "올리기"
  python3 "$LAB/tools/pod/pupload.py" "$S/ns.tar" /workspace/ns.tar "$M8/aligner/model.int8.safetensors" /workspace/aligner.int8 \
    "$M8/scorer/model.int8.safetensors" /workspace/scorer.int8 --chunk-mb 8 --par 24 > "$S/pupload.log" 2>&1
  PUP_RC=$?
  tail -n 4 "$S/pupload.log"
  { [ "$PUP_RC" = 0 ] && grep -q '^PUP_DONE ok=3 fail=0' "$S/pupload.log"; } || { bash "$P" terminate --force || true; die "upload(rc=$PUP_RC)"; }
  bash "$P" ssh 'mkdir -p /workspace/ns && cd /workspace/ns && tar -xf ../ns.tar && rm -f ../ns.tar && for bk in backend backend_new; do cp ../aligner.int8 $bk/models/dgop_ours/aligner/model.int8.safetensors && cp ../scorer.int8 $bk/models/dgop_ours/scorer/model.int8.safetensors; done && rm -f ../aligner.int8 ../scorer.int8 && sha256sum -c --quiet expect.sha256 && echo REMOTE_SHA_OK' \
    | tee "$S/unpack.log" || { bash "$P" terminate --force || true; die "풀기"; }
  grep -q '^REMOTE_SHA_OK' "$S/unpack.log" || { bash "$P" terminate --force || true; die "sha256 불일치"; }
  step "run.sh 시작"
  bash "$P" run 'bash /workspace/ns/scripts/run.sh' || { bash "$P" terminate --force || true; die run; }
  echo "NSS_LAUNCH_OK $(pod_id)"
}

do_fetch() {
  POD=$(pod_id)
  [ -n "$POD" ] || die "파드 없음"
  out="$LAB/data/pod_runs/$(date +%Y%m%d)_${POD}/ns"
  mkdir -p "$out"
  if bash "$P" ssh 'test -s /workspace/ns_result.tgz && grep -q "^NS_OK" /workspace/dax/logs/ns.log'; then
    bash "$P" ssh 'cat /workspace/ns_result.tgz' > "$out/result.tgz" && tar -xzf "$out/result.tgz" -C "$out" && echo "NSS_FETCH_OK $out" || echo "NSS_FETCH_WARN"
  else
    bash "$P" ssh 'cd /workspace/ns && tar -czf - out/*.jsonl out/*.json ../dax/logs/*.log 2>/dev/null' | tar -xzf - -C "$out" && echo "NSS_FETCH_PARTIAL $out" || echo "NSS_FETCH_WARN"
  fi
  ls -la "$out" "$out/out" 2>/dev/null | tail -20
}

case "$CMD" in
  stage) do_stage ;;
  launch) do_launch ;;
  tail) bash "$P" ssh 'tail -n 30 /workspace/dax/logs/ns.log' ;;
  fetch) do_fetch ;;
  finish) do_fetch; bash "$P" terminate --force || true; bash "$P" status || true ;;
  *) echo "session.sh stage|launch|tail|fetch|finish"; exit 2 ;;
esac
