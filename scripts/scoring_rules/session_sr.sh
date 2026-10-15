#!/bin/bash
# 문장 점수 규칙 후보 파드 세션(맥, docs/scoring-rules-2026-10.md). 파드는 liplab-lab/tools/pod/pod.sh로만 다룬다(session_c27.sh와 같은 틀).
#   bash scripts/scoring_rules/session_sr.sh stage explore|confirm    묶음(파드 없음): 이 브랜치 backend, 도구, build_stage.py 산출
#   bash scripts/scoring_rules/session_sr.sh launch explore|confirm   파드 생성(워치독) → 올리기 → sha256 → run_sr.sh → 기다림 → 받기 → terminate
#   bash scripts/scoring_rules/session_sr.sh tail|finish PHASE
# 상태 폴더 tools/pod/.srstate, 파드 이름 liplab-sr. RunPod 키는 pod.sh가 메모리로만 읽는다. 원자료·조각은 lab 묶음 폴더와 파드에만 둔다.
set -uo pipefail
APP=$(cd "$(dirname "$0")/../.." && pwd)
LAB=${LAB:-$HOME/Downloads/LIPLAB_ALL/liplab-lab}
P="$LAB/tools/pod/pod.sh"
export POD_STATE_DIR=${POD_STATE_DIR:-$LAB/tools/pod/.srstate} POD_NAME=${POD_NAME:-liplab-sr} POD_DISK_GB=${POD_DISK_GB:-40}
export DEADMAN_GRACE_MIN=${DEADMAN_GRACE_MIN:-15}
M8=$LAB/models/dgop_ours_2026-09-25_int8
CMD=${1:-}
PH=${2:-}
[ "$PH" = explore ] || [ "$PH" = confirm ] || { echo "PHASE = explore|confirm"; exit 2; }
S=$LAB/data/srules_stage/$PH
COMMIT_SEG=b675975e670ebe637458e89a0e44709db0b5174e
GPUS=${GPUS:-NVIDIA A40|SECURE,NVIDIA RTX A6000|SECURE,NVIDIA L40S|SECURE}
WD_MIN=${WD_MIN:-150}
SHA_ALIGNER=18681947f740b7486f8fa4f93c7c0f68fe1595ac4fa9822800dfd38d713f5e66
SHA_SCORER=e8340d58dd911e380eca508815526eb77ec658560456ce1fe4c16b9b6e3654c4
PYV=$HOME/Downloads/LIPLAB_ALL/liplab/backend/.venv/bin/python
mkdir -p "$S" "$LAB/data/pod_runs" "$POD_STATE_DIR"
LOG="$LAB/data/pod_runs/session_sr_${PH}_${CMD}_$(date +%Y%m%d_%H%M).log"
exec > >(tee -a "$LOG") 2>&1
step() { echo "=== $(date '+%F %T') $*"; }
die() { echo "SRS_FAIL $*"; exit 1; }
pod_id() { awk -F= '$1 == "POD_ID" {print $2}' "$POD_STATE_DIR/.pod_state" 2>/dev/null; }
sha_of() { shasum -a 256 "$1" | cut -d' ' -f1; }

do_stage() {
  step "가중치·코드 확인"
  [ "$(sha_of "$M8/aligner/model.int8.safetensors")" = "$SHA_ALIGNER" ] || die "정렬기 sha256"
  [ "$(sha_of "$M8/scorer/model.int8.safetensors")" = "$SHA_SCORER" ] || die "채점기 sha256"
  [ -z "$(git -C "$APP" status --porcelain -- backend scripts/scoring_rules)" ] || die "backend·scripts/scoring_rules에 커밋 안 된 변경"
  R=$S/root
  mkdir -p "$R"
  rm -rf "$R/backend" "$R/tools" "$R/scripts" && mkdir -p "$R/tools" "$R/scripts"
  git -C "$APP" archive HEAD backend | tar -x -C "$R" || die "git archive HEAD"
  git -C "$APP" archive "$COMMIT_SEG" scripts/speak_asr_pod_run.py | tar -x -C "$R" || die "git archive b675975"
  rm -rf "$R/backend/data/sound"
  for m in aligner scorer; do
    mkdir -p "$R/backend/models/dgop_ours/$m"
    for f in "$M8/$m"/*; do case "$(basename "$f")" in model.int8.safetensors|model.safetensors) ;; *) cp -c "$f" "$R/backend/models/dgop_ours/$m/" ;; esac; done
  done
  cp "$APP/scripts/scoring_rules/feat_pod.py" "$APP/scripts/scoring_rules/targets.py" "$R/tools/" && cp "$APP/scripts/scoring_rules/run_sr.sh" "$R/" || die scripts
  "$PYV" "$APP/scripts/scoring_rules/build_stage.py" "$PH" "$R" | tail -n 1 | tee "$S/stage.txt"
  grep -q STAGE_OK "$S/stage.txt" || die build_stage
  (cd "$R/tools" && "$PYV" feat_pod.py selftest) | grep -q SR_SELFTEST_OK || die "로컬 selftest"
  ( cd "$R" && find backend scripts tools audio c27b2 jobs.json run_sr.sh -type f 2>/dev/null | sort | xargs shasum -a 256 ) > "$R/expect.sha256"
  printf '%s  backend/models/dgop_ours/aligner/model.int8.safetensors\n%s  backend/models/dgop_ours/scorer/model.int8.safetensors\n' \
    "$SHA_ALIGNER" "$SHA_SCORER" >> "$R/expect.sha256"
  git -C "$APP" rev-parse HEAD > "$S/backend.rev"
  COPYFILE_DISABLE=1 tar --no-mac-metadata --no-xattrs --exclude .DS_Store --exclude '._*' -cf "$S/sr.tar" -C "$R" . || die tar
  ls -la "$S/sr.tar"
  echo "SRS_STAGE_OK backend=$(cat "$S/backend.rev")"
}

fetch_result() {
  local POD out
  POD=$(pod_id)
  [ -n "$POD" ] || { echo "파드 없음"; return 1; }
  out="$LAB/data/pod_runs/$(date +%Y%m%d)_${POD}/sr_$PH"
  mkdir -p "$out"
  if bash "$P" ssh 'test -s /workspace/sr_result.tgz && grep -q "^SR_OK" /workspace/dax/logs/sr.log'; then
    bash "$P" ssh 'cat /workspace/sr_result.tgz' > "$out/result.tgz" && tar -xzf "$out/result.tgz" -C "$out" && echo "SRS_FETCH_OK $out" || echo "SRS_FETCH_WARN"
  else
    bash "$P" ssh 'cd /workspace && tar -czf - out/*.jsonl jobs_b2.json c27b2/out/cuts608.json dax/logs/*.log 2>/dev/null' | tar -xzf - -C "$out" && echo "SRS_FETCH_PARTIAL $out" || echo "SRS_FETCH_WARN"
  fi
  ls -la "$out" "$out/out" 2>/dev/null | tail -20
}

do_launch() {
  [ -s "$S/sr.tar" ] || die "묶음 없음(stage 먼저)"
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
  echo "SRS_POD $(pod_id)"
  bash "$P" wait || { bash "$P" terminate --force || true; die wait; }
  bash "$P" ssh 'nproc; cat /sys/fs/cgroup/cpu.max 2>/dev/null; free -g | head -2; df -h /workspace | tail -1; nvidia-smi --query-gpu=name,memory.total --format=csv,noheader'
  step "올리기"
  python3 "$LAB/tools/pod/pupload.py" "$S/sr.tar" /workspace/sr.tar "$M8/aligner/model.int8.safetensors" /workspace/aligner.int8 \
    "$M8/scorer/model.int8.safetensors" /workspace/scorer.int8 --chunk-mb 8 --par 24 > "$S/pupload.log" 2>&1
  PUP_RC=$?
  tail -n 4 "$S/pupload.log"
  { [ "$PUP_RC" = 0 ] && grep -q '^PUP_DONE ok=3 fail=0' "$S/pupload.log"; } || { bash "$P" terminate --force || true; die "upload(rc=$PUP_RC)"; }
  bash "$P" ssh 'cd /workspace && tar -xf sr.tar && rm -f sr.tar && cp aligner.int8 backend/models/dgop_ours/aligner/model.int8.safetensors && cp scorer.int8 backend/models/dgop_ours/scorer/model.int8.safetensors && rm -f aligner.int8 scorer.int8 && sha256sum -c --quiet expect.sha256 && echo REMOTE_SHA_OK' \
    | tee "$S/unpack.log" || { bash "$P" terminate --force || true; die "풀기"; }
  grep -q '^REMOTE_SHA_OK' "$S/unpack.log" || { bash "$P" terminate --force || true; die "sha256 불일치"; }
  step "run_sr.sh $PH 시작"
  bash "$P" run "bash /workspace/run_sr.sh $PH" || { bash "$P" terminate --force || true; die run; }
  echo "SRS_LAUNCH_OK $(pod_id)"
  WAITFOR_MAX_MIN=${WAIT_MAX:-140} WAIT_POLL=60 bash "$P" waitfor SR_OK logs/sr.log
  WRC=$?
  bash "$P" ssh 'grep -E "^(ENV|SR_|SEG|B2|FEAT|ERRORS|===)" /workspace/dax/logs/sr.log | tail -n 40' || true
  fetch_result
  bash "$P" terminate --force || true
  bash "$P" status || true
  [ "$WRC" = 0 ] && echo "SRS_DONE" || die "waitfor rc=$WRC"
}

case "$CMD" in
  stage) do_stage ;;
  launch) do_launch ;;
  tail) bash "$P" ssh 'tail -n 30 /workspace/dax/logs/sr.log' ;;
  finish) fetch_result; bash "$P" terminate --force || true; bash "$P" status || true ;;
  *) echo "session_sr.sh stage|launch|tail|finish PHASE"; exit 2 ;;
esac
