#!/bin/bash
# 소리 품질 점검·재합성 파드 세션(맥, docs/sound-qa-2026-10.md). 파드는 liplab-lab의 tools/pod/pod.sh로만 다룬다.
#   bash scripts/sound_pod/qa_session.sh stage TARGETS.jsonl   묶음(파드 없음): 백엔드 코드, D-GOP 모델, 점검 스크립트, 대상, 기존 클립(ogg)
#   bash scripts/sound_pod/qa_session.sh launch                파드 생성(워치독) → wait(자폭 타이머) → 속도 점검 → 올리기 → sha256 → qa_run.sh
#   bash scripts/sound_pod/qa_session.sh tail                  파드 로그 끝부분
#   bash scripts/sound_pod/qa_session.sh fetch                 result.tgz(판정·선택·인코딩 소리·로그)를 받아 RUN 폴더에 푼다(여러 번 불러도 됨)
#   bash scripts/sound_pod/qa_session.sh finish                fetch → terminate → status
#   bash scripts/sound_pod/qa_session.sh resume                연결이 끊긴 뒤 qa_run.sh를 다시 띄운다(끝난 단계는 건너뛴다)
# 환경: MODE=missing(목록에 없는 글만), LAB(기본 ~/Downloads/liplab-lab), MODELS(D-GOP int8 모델 폴더), GPUS, WD_MIN.
# 다른 작업과 섞이지 않게 상태 폴더 .sqastate, 파드 이름 liplab-sqa. 키는 pod.sh가 ~/.runpod/config.toml에서 메모리로만 읽는다.
set -uo pipefail
APP=$(cd "$(dirname "$0")/../.." && pwd)
LAB=${LAB:-$HOME/Downloads/liplab-lab}
P="$LAB/tools/pod/pod.sh"
export POD_STATE_DIR=${POD_STATE_DIR:-$LAB/tools/pod/.sqastate} POD_NAME=${POD_NAME:-liplab-sqa} POD_DISK_GB=${POD_DISK_GB:-60}
export DEADMAN_GRACE_MIN=${DEADMAN_GRACE_MIN:-15}
MODELS=${MODELS:-$HOME/Downloads/liplab-integrate/backend/models/dgop_ours}
S=${STAGE_DIR:-$LAB/data/sqa_stage}
GPUS=${GPUS:-NVIDIA A40|SECURE,NVIDIA RTX A6000|SECURE,NVIDIA L40S|SECURE}
WD_MIN=${WD_MIN:-210}
mkdir -p "$S" "$LAB/data/pod_runs" "$POD_STATE_DIR"
CMD=${1:-}
LOG="$LAB/data/pod_runs/session_sqa_${CMD}_$(date +%Y%m%d_%H%M).log"
exec > >(tee -a "$LOG") 2>&1
step() { echo "=== $(date '+%F %T') $*"; }
die() { echo "SQA_FAIL $*"; exit 1; }
pod_id() { awk -F= '$1 == "POD_ID" {print $2}' "$POD_STATE_DIR/.pod_state" 2>/dev/null; }

do_stage() {
  local T=${1:-}
  [ -s "$T" ] || die "대상 목록 없음: $T"
  step "묶음"
  R=$S/root
  rm -rf "$R" && mkdir -p "$R/backend/data" "$R/scripts" "$R/sound/clips" "$R/models/dgop_ours" "$R/work"
  cp "$APP"/backend/*.py "$R/backend/" || die backend
  cp "$APP"/backend/data/dgop_calibration*.json "$R/backend/data/" || die calibration
  cp "$APP"/scripts/sound_pod/qa_*.py "$APP"/scripts/sound_pod/qa_run.sh "$R/scripts/" || die scripts
  [ -f "$APP/scripts/sound_pod/qa_ref.json" ] && cp "$APP/scripts/sound_pod/qa_ref.json" "$R/scripts/"
  for d in aligner scorer; do
    mkdir -p "$R/models/dgop_ours/$d" && cp "$MODELS/$d"/* "$R/models/dgop_ours/$d/" || die "모델 $d"
  done
  cp "$T" "$R/work/targets.jsonl"
  python3 - "$R/work/targets.jsonl" "$APP/backend/data/sound/clips" "$R/sound/clips" <<'EOF' || die "클립 고르기"
import json, os, shutil, sys
n = 0
for l in open(sys.argv[1], encoding="utf-8"):
    if l.strip():
        i = json.loads(l).get("orig_id")
        if i:
            shutil.copy(os.path.join(sys.argv[2], i + ".ogg"), sys.argv[3]); n += 1
print("CLIPS", n)
EOF
  ( cd "$R" && find backend scripts sound models work -type f | sort | xargs shasum -a 256 ) > "$R/expect.sha256"
  COPYFILE_DISABLE=1 tar --no-mac-metadata --no-xattrs --exclude .DS_Store --exclude '._*' -cf "$S/sqa.tar" -C "$R" . || die tar
  ls -la "$S/sqa.tar"
  echo "SQA_STAGE_OK"
}

start_run() { bash "$P" run "env MODE=${MODE:-full} ${QA_ENV:-} bash /workspace/sqa/scripts/qa_run.sh" || die run; }

do_launch() {
  [ -s "$S/sqa.tar" ] || die "묶음 없음(stage 먼저)"
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
  POD=$(pod_id)
  echo "SQA_POD $POD"
  bash "$P" wait || { bash "$P" terminate --force || true; die wait; }
  step "올리기 속도 점검(8MB)"
  T0=$(python3 -c 'import time; print(time.time())')
  head -c 8388608 /dev/urandom | perl -e 'alarm 90; exec @ARGV' bash "$P" ssh 'cat > /workspace/.speedtest && wc -c < /workspace/.speedtest && rm -f /workspace/.speedtest' \
    || { bash "$P" terminate --force || true; die speedtest; }
  T1=$(python3 -c 'import time; print(time.time())')
  echo "UPLOAD_MBPS $(python3 -c "print(round(8 / max(1e-3, $T1 - $T0), 2))") (연결 하나)"
  bash "$P" ssh 'nproc; cat /sys/fs/cgroup/cpu.max 2>/dev/null; free -g | head -2; df -h /workspace | tail -1; nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader'
  do_upload
  step "qa_run.sh 시작"
  start_run
  echo "SQA_LAUNCH_OK $POD"
}

do_upload() {
  step "올리기"
  python3 "$LAB/tools/pod/pupload.py" "$S/sqa.tar" /workspace/sqa.tar --chunk-mb 8 --par 24 > "$S/pupload.log" 2>&1
  PUP_RC=$?
  tail -n 3 "$S/pupload.log"
  { [ "$PUP_RC" = 0 ] && grep -q '^PUP_DONE ok=1 fail=0' "$S/pupload.log"; } || die "upload(pupload rc=$PUP_RC, 파드는 그대로: 'upload' 다시 또는 finish)"
  bash "$P" ssh 'mkdir -p /workspace/sqa && cd /workspace/sqa && tar -xf ../sqa.tar && rm -f ../sqa.tar && sha256sum -c --quiet expect.sha256 && echo REMOTE_SHA_OK' \
    | tee "$S/unpack.log" || die "풀기"
  grep -q '^REMOTE_SHA_OK' "$S/unpack.log" || die "파드 쪽 sha256 불일치"
}

do_fetch() {
  POD=$(pod_id)
  [ -n "$POD" ] || die "파드 없음"
  out="$LAB/data/pod_runs/$(date +%Y%m%d)_${POD}/sqa"
  mkdir -p "$out"
  if bash "$P" ssh 'test -s /workspace/sqa/result.tgz && grep -q QA_ALL_OK /workspace/sqa/logs/run.log'; then
    bash "$P" ssh 'cat /workspace/sqa/result.tgz' > "$out/result.tgz" && tar -xzf "$out/result.tgz" -C "$out" && echo "SQA_FETCH_OK $out" || echo "SQA_FETCH_WARN"
  else
    # 덜 끝났으면 판정·로그만(중간 확인용)
    bash "$P" ssh 'cd /workspace/sqa && tar -czf - work/*.json work/*.uids work/judged.*.jsonl logs 2>/dev/null' | tar -xzf - -C "$out" \
      && echo "SQA_FETCH_PARTIAL $out" || echo "SQA_FETCH_WARN"
  fi
  ls -la "$out" | tail -20
}

case "$CMD" in
  stage) do_stage "${2:-}" ;;
  launch) do_launch ;;
  upload) do_upload ;;
  resume) start_run ;;
  tail) bash "$P" ssh 'tail -n 40 /workspace/sqa/logs/run.log' ;;
  fetch) do_fetch ;;
  finish) do_fetch; bash "$P" terminate --force || true; bash "$P" status || true ;;
  *) echo "qa_session.sh stage TARGETS|launch|upload|resume|tail|fetch|finish"; exit 2 ;;
esac
