#!/bin/bash
# 대화 듣기 실시간 합성 측정 파드 세션(맥, docs/listen-convo-tts-2026-10.md 5절). 파드는 liplab-lab의 tools/pod/pod.sh로만 다룬다.
#   bash scripts/convo_tts/session.sh stage     묶음(파드 없음): 백엔드 코드·자료, D-GOP int8 모델·아바타 체크포인트, 측정·점검 스크립트
#   bash scripts/convo_tts/session.sh launch    잔액 확인 → 파드 생성(워치독) → wait(자폭 타이머) → 속도 점검 → 올리기 → pod_run.sh
#   bash scripts/convo_tts/session.sh tail      파드 로그 끝부분
#   bash scripts/convo_tts/session.sh fetch     result.tgz를 받아 RUN 폴더에 푼다
#   bash scripts/convo_tts/session.sh finish    fetch → terminate → status
#   bash scripts/convo_tts/session.sh resume    pod_run.sh를 다시 띄운다(끝난 단계는 건너뛴다)
# 다른 작업과 섞이지 않게 상태 폴더 .ctstate, 파드 이름 liplab-ctts. 잔액이 MIN_BALANCE(기본 5달러)보다 적으면 만들지 않는다.
set -uo pipefail
APP=$(cd "$(dirname "$0")/../.." && pwd)
LAB=${LAB:-$HOME/Downloads/LIPLAB_ALL/liplab-lab}
P="$LAB/tools/pod/pod.sh"
export POD_STATE_DIR=${POD_STATE_DIR:-$LAB/tools/pod/.ctstate} POD_NAME=${POD_NAME:-liplab-ctts} POD_DISK_GB=${POD_DISK_GB:-60}
export DEADMAN_GRACE_MIN=${DEADMAN_GRACE_MIN:-15}
MODELS=${MODELS:-$HOME/Downloads/LIPLAB_ALL/liplab-integrate/backend/models}
S=${STAGE_DIR:-$LAB/data/ctts_stage}
GPUS=${GPUS:-NVIDIA A40|SECURE,NVIDIA RTX A6000|SECURE,NVIDIA L40S|SECURE}
WD_MIN=${WD_MIN:-150}
MIN_BALANCE=${MIN_BALANCE:-5}
mkdir -p "$S" "$LAB/data/pod_runs" "$POD_STATE_DIR"
CMD=${1:-}
LOG="$LAB/data/pod_runs/session_ctts_${CMD}_$(date +%Y%m%d_%H%M).log"
exec > >(tee -a "$LOG") 2>&1
step() { echo "=== $(date '+%F %T') $*"; }
die() { echo "CT_SESSION_FAIL $*"; exit 1; }
pod_id() { awk -F= '$1 == "POD_ID" {print $2}' "$POD_STATE_DIR/.pod_state" 2>/dev/null; }

do_stage() {
  step "묶음"
  R=$S/root
  rm -rf "$R" && mkdir -p "$R/backend" "$R/scripts"
  ( cd "$APP/backend" && COPYFILE_DISABLE=1 tar --exclude .venv --exclude __pycache__ --exclude 'liplab.db' --exclude 'models' --exclude '.pytest_cache' -cf - . ) \
    | tar -xf - -C "$R/backend" || die backend
  mkdir -p "$R/backend/models/dgop_ours"
  for d in aligner scorer; do
    mkdir -p "$R/backend/models/dgop_ours/$d" && cp "$MODELS/dgop_ours/$d"/* "$R/backend/models/dgop_ours/$d/" || die "모델 $d"
    test -s "$R/backend/models/dgop_ours/$d/model.int8.safetensors" || die "int8 없음 $d"
  done
  cp "$MODELS/kr_a4_wavlm.pt" "$R/backend/models/" || die a4
  cp "$APP"/scripts/convo_tts/*.py "$APP"/scripts/convo_tts/*.sh "$APP"/scripts/convo_tts/fixture_items.json "$R/scripts/" || die scripts
  cp "$APP"/scripts/sound_pod/qa_rules.py "$APP"/scripts/sound_pod/qa_asr.py "$APP"/scripts/sound_pod/qa_eval.py \
     "$APP"/scripts/sound_pod/qa_judge.py "$APP"/scripts/sound_pod/qa_ref.json "$R/scripts/" || die qa
  ( cd "$R" && find backend scripts -type f | sort | xargs shasum -a 256 ) > "$R/expect.sha256"
  COPYFILE_DISABLE=1 tar --no-mac-metadata --no-xattrs --exclude .DS_Store --exclude '._*' -cf "$S/ct.tar" -C "$R" . || die tar
  ls -la "$S/ct.tar"
  echo "CT_STAGE_OK"
}

start_run() { bash "$P" run "env STAGES=${STAGES:-main} bash /workspace/ct/scripts/pod_run.sh" || die run; }

do_launch() {
  [ -s "$S/ct.tar" ] || die "묶음 없음(stage 먼저)"
  step "잔액·파드 목록"
  st=$(bash "$P" status 2>&1); echo "$st" | tail -5
  bal=$(echo "$st" | awk '/^BALANCE/ {gsub(/\$/, "", $2); print $2}' | head -1)
  python3 -c "import sys; sys.exit(0 if float('${bal:-0}') >= float('$MIN_BALANCE') else 1)" || die "잔액 ${bal:-?} < $MIN_BALANCE"
  step "파드 생성(워치독 ${WD_MIN}분, 상태 $POD_STATE_DIR, 이름 $POD_NAME)"
  created=0
  IFS=',' read -r -a CANDS <<< "$GPUS"
  for cand in "${CANDS[@]}"; do
    g=${cand%%|*}; c=${cand#*|}
    step "후보 $g / $c"
    if bash "$P" create "$g" "$c" --watchdog "$WD_MIN"; then created=1; break; fi
  done
  [ "$created" = 1 ] || die "create(모든 후보 실패, 파드 없음)"
  POD=$(pod_id)
  echo "CT_POD $POD"
  bash "$P" wait || { bash "$P" terminate --force || true; die wait; }
  step "올리기 속도 점검(8MB)"
  T0=$(python3 -c 'import time; print(time.time())')
  head -c 8388608 /dev/urandom | perl -e 'alarm 90; exec @ARGV' bash "$P" ssh 'cat > /workspace/.speedtest && wc -c < /workspace/.speedtest && rm -f /workspace/.speedtest' \
    || { bash "$P" terminate --force || true; die speedtest; }
  T1=$(python3 -c 'import time; print(time.time())')
  echo "UPLOAD_MBPS $(python3 -c "print(round(8 / max(1e-3, $T1 - $T0), 2))") (연결 하나)"
  bash "$P" ssh 'nproc; cat /sys/fs/cgroup/cpu.max 2>/dev/null; cat /sys/fs/cgroup/cpu/cpu.cfs_quota_us 2>/dev/null; free -g | head -2; df -h /workspace | tail -1; lscpu | grep -E "Model name|^CPU\(s\)"; nvidia-smi --query-gpu=name,memory.total --format=csv,noheader'
  do_upload
  step "pod_run.sh 시작"
  start_run
  echo "CT_LAUNCH_OK $POD"
}

do_upload() {
  step "올리기"
  python3 "$LAB/tools/pod/pupload.py" "$S/ct.tar" /workspace/ct.tar --chunk-mb 8 --par 24 > "$S/pupload.log" 2>&1
  PUP_RC=$?
  tail -n 3 "$S/pupload.log"
  { [ "$PUP_RC" = 0 ] && grep -q '^PUP_DONE ok=1 fail=0' "$S/pupload.log"; } || die "upload(pupload rc=$PUP_RC, 파드는 그대로: 'upload' 다시 또는 finish)"
  bash "$P" ssh 'mkdir -p /workspace/ct && cd /workspace/ct && tar -xf ../ct.tar && rm -f ../ct.tar && sha256sum -c --quiet expect.sha256 && echo REMOTE_SHA_OK' \
    | tee "$S/unpack.log" || die "풀기"
  grep -q '^REMOTE_SHA_OK' "$S/unpack.log" || die "파드 쪽 sha256 불일치"
}

do_fetch() {
  POD=$(pod_id)
  [ -n "$POD" ] || die "파드 없음"
  out="$LAB/data/pod_runs/$(date +%Y%m%d)_${POD}/ctts"
  mkdir -p "$out"
  [ "${STAGES:-main}" = explore ] && out="$out/explore" && mkdir -p "$out"
  if bash "$P" ssh 'test -s /workspace/ct/result.tgz && grep -q CT_ALL_OK /workspace/ct/logs/run.log'; then
    bash "$P" ssh 'cat /workspace/ct/result.tgz' > "$out/result.tgz" && tar -xzf "$out/result.tgz" -C "$out" && echo "CT_FETCH_OK $out" || echo "CT_FETCH_WARN"
  else
    bash "$P" ssh 'cd /workspace/ct && tar -czf - work/*.json work/summary.* work/qa_* work/cache_server1/index.json work/cache_server1/convo_items.json logs 2>/dev/null' \
      | tar -xzf - -C "$out" && echo "CT_FETCH_PARTIAL $out" || echo "CT_FETCH_WARN"
  fi
  ls -la "$out" | tail -20
}

case "$CMD" in
  stage) do_stage ;;
  launch) do_launch ;;
  upload) do_upload ;;
  resume) start_run ;;
  tail) bash "$P" ssh 'tail -n 50 /workspace/ct/logs/run.log' ;;
  fetch) do_fetch ;;
  finish) do_fetch; bash "$P" terminate --force || true; bash "$P" status || true ;;
  *) echo "session.sh stage|launch|upload|resume|tail|fetch|finish"; exit 2 ;;
esac
