#!/bin/bash
# S2 음소 피드백 신뢰도 지도 파드 세션(맥, docs/phoneme-feedback-reliability-2026-10.md). 파드는 liplab-lab의 tools/pod/pod.sh로만 다룬다.
#   bash scripts/s2_reliability_pod/session.sh stage    묶음(파드 없음): 이 브랜치 backend, measure.py·run.sh, 작업 목록, 538 소리
#   bash scripts/s2_reliability_pod/session.sh launch   파드 생성(워치독) → wait(자폭 타이머) → 올리기 → sha256 → run.sh
#   bash scripts/s2_reliability_pod/session.sh tail     파드 로그 끝부분
#   bash scripts/s2_reliability_pod/session.sh finish   결과 받기 → terminate → status
# 상태 폴더 .s2state, 파드 이름 liplab-s2. RunPod 키는 pod.sh가 ~/.runpod/config.toml에서 메모리로만 읽는다.
# 538 원자료는 lab 묶음 폴더와 파드에만 두고 앱 저장소에 넣지 않는다.
set -uo pipefail
APP=$(cd "$(dirname "$0")/../.." && pwd)
LAB=${LAB:-$HOME/Downloads/liplab-lab}
P="$LAB/tools/pod/pod.sh"
# S2_SETS(기본 "A0 A1")로 묶을 자료를, S2_TRIM=1로 앱과 같은 끝 자르기를 고른다(run.sh가 넘긴다).
export POD_STATE_DIR=${POD_STATE_DIR:-$LAB/tools/pod/.s2state} POD_NAME=${POD_NAME:-liplab-s2} POD_DISK_GB=${POD_DISK_GB:-50}
export DEADMAN_GRACE_MIN=${DEADMAN_GRACE_MIN:-15}
M8=${M8:-$LAB/models/dgop_ours_2026-09-25_int8}
S=${STAGE_DIR:-$LAB/data/s2stage}
GPUS=${GPUS:-NVIDIA A40|SECURE,NVIDIA RTX A6000|SECURE,NVIDIA L40S|SECURE}
WD_MIN=${WD_MIN:-60}
SHA_ALIGNER=18681947f740b7486f8fa4f93c7c0f68fe1595ac4fa9822800dfd38d713f5e66
SHA_SCORER=e8340d58dd911e380eca508815526eb77ec658560456ce1fe4c16b9b6e3654c4
mkdir -p "$S" "$LAB/data/pod_runs" "$POD_STATE_DIR"
CMD=${1:-}
LOG="$LAB/data/pod_runs/session_s2_${CMD}_$(date +%Y%m%d_%H%M).log"
exec > >(tee -a "$LOG") 2>&1
step() { echo "=== $(date '+%F %T') $*"; }
die() { echo "S2S_FAIL $*"; exit 1; }
pod_id() { awk -F= '$1 == "POD_ID" {print $2}' "$POD_STATE_DIR/.pod_state" 2>/dev/null; }
sha_of() { shasum -a 256 "$1" | cut -d' ' -f1; }

do_stage() {
  step "가중치 확인"
  [ "$(sha_of "$M8/aligner/model.int8.safetensors")" = "$SHA_ALIGNER" ] || die "정렬기 sha256"
  [ "$(sha_of "$M8/scorer/model.int8.safetensors")" = "$SHA_SCORER" ] || die "채점기 sha256"
  [ -s "$S/data/jobs.jsonl" ] || die "작업 목록 없음(build_jobs.py 먼저)"
  step "묶음"
  R=$S/root
  rm -rf "$R" && mkdir -p "$R/backend/data" "$R/scripts" "$R/data/wav"
  cp "$APP"/backend/*.py "$R/backend/" || die backend
  rm -f "$R"/backend/test_*.py
  cp "$APP"/backend/data/dgop_calibration*.json "$R/backend/data/" || die calibration
  cp "$APP"/scripts/s2_reliability_pod/measure.py "$APP"/scripts/s2_reliability_pod/run.sh "$R/scripts/" || die scripts
  cp "$S/data/jobs.jsonl" "$R/data/" || die jobs
  for m in aligner scorer; do
    mkdir -p "$R/backend/models/dgop_ours/$m"
    for f in "$M8/$m"/*; do case "$(basename "$f")" in model.int8.safetensors|model.safetensors) ;; *) cp "$f" "$R/backend/models/dgop_ours/$m/" ;; esac; done
  done
  python3 - "$R/data" "$LAB" <<'EOF' || die "소리 복사"
import json, os, shutil, sys
d, lab = sys.argv[1:3]
src = {"A0": os.path.expanduser("~/Downloads/liplab_gpu_snapshot/expand538_more/clips"), "A1": f"{lab}/data/v1_538/clips"}
n = {"A0": 0, "A1": 0}
sets = set(os.environ.get("S2_SETS", "A0 A1").split())
keep = []
for l in open(f"{d}/jobs.jsonl", encoding="utf-8"):
    j = json.loads(l)
    if j["set"] not in sets:
        continue
    keep.append(l)
    shutil.copyfile(f"{src[j['set']]}/{j['clip']}.wav", f"{d}/wav/{j['clip']}.wav"); n[j["set"]] += 1
open(f"{d}/jobs.jsonl", "w", encoding="utf-8").writelines(keep)
print("COPIED", n)
EOF
  ( cd "$R" && find backend scripts data -type f | sort | xargs shasum -a 256 ) > "$R/expect.sha256"
  printf '%s  backend/models/dgop_ours/aligner/model.int8.safetensors\n%s  backend/models/dgop_ours/scorer/model.int8.safetensors\n' \
    "$SHA_ALIGNER" "$SHA_SCORER" >> "$R/expect.sha256"
  COPYFILE_DISABLE=1 tar --no-mac-metadata --no-xattrs --exclude .DS_Store --exclude '._*' -cf "$S/s2.tar" -C "$R" . || die tar
  ls -la "$S/s2.tar"
  echo "S2S_STAGE_OK"
}

do_launch() {
  [ -s "$S/s2.tar" ] || die "묶음 없음(stage 먼저)"
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
  echo "S2S_POD $(pod_id)"
  bash "$P" wait || { bash "$P" terminate --force || true; die wait; }
  bash "$P" ssh 'nproc; cat /sys/fs/cgroup/cpu.max 2>/dev/null; free -g | head -2; df -h /workspace | tail -1; nvidia-smi --query-gpu=name,memory.total --format=csv,noheader'
  step "올리기"
  python3 "$LAB/tools/pod/pupload.py" "$S/s2.tar" /workspace/s2.tar "$M8/aligner/model.int8.safetensors" /workspace/aligner.int8 \
    "$M8/scorer/model.int8.safetensors" /workspace/scorer.int8 --chunk-mb 8 --par 24 > "$S/pupload.log" 2>&1
  PUP_RC=$?
  tail -n 4 "$S/pupload.log"
  { [ "$PUP_RC" = 0 ] && grep -q '^PUP_DONE ok=3 fail=0' "$S/pupload.log"; } || { bash "$P" terminate --force || true; die "upload(rc=$PUP_RC)"; }
  bash "$P" ssh 'mkdir -p /workspace/s2 && cd /workspace/s2 && tar -xf ../s2.tar && rm -f ../s2.tar && mv ../aligner.int8 backend/models/dgop_ours/aligner/model.int8.safetensors && mv ../scorer.int8 backend/models/dgop_ours/scorer/model.int8.safetensors && sha256sum -c --quiet expect.sha256 && echo REMOTE_SHA_OK' \
    | tee "$S/unpack.log" || { bash "$P" terminate --force || true; die "풀기"; }
  grep -q '^REMOTE_SHA_OK' "$S/unpack.log" || { bash "$P" terminate --force || true; die "sha256 불일치"; }
  step "run.sh 시작"
  bash "$P" run "env S2_TRIM=${S2_TRIM:-0} bash /workspace/s2/scripts/run.sh" || { bash "$P" terminate --force || true; die run; }
  echo "S2S_LAUNCH_OK $(pod_id)"
}

do_fetch() {
  POD=$(pod_id)
  [ -n "$POD" ] || die "파드 없음"
  out="$LAB/data/pod_runs/$(date +%Y%m%d)_${POD}/s2"
  mkdir -p "$out"
  if bash "$P" ssh 'test -s /workspace/s2_result.tgz && grep -q "^S2_OK" /workspace/dax/logs/s2.log'; then
    bash "$P" ssh 'cat /workspace/s2_result.tgz' > "$out/result.tgz" && tar -xzf "$out/result.tgz" -C "$out" && echo "S2S_FETCH_OK $out" || echo "S2S_FETCH_WARN"
  else
    bash "$P" ssh 'cd /workspace && tar -czf - s2/out dax/logs 2>/dev/null' | tar -xzf - -C "$out" && echo "S2S_FETCH_PARTIAL $out" || echo "S2S_FETCH_WARN"
  fi
  ls -la "$out" "$out/s2/out" 2>/dev/null | tail -20
}

case "$CMD" in
  stage) do_stage ;;
  launch) do_launch ;;
  tail) bash "$P" ssh 'tail -n 30 /workspace/dax/logs/s2.log; tail -n 2 /workspace/dax/logs/run.*.log 2>/dev/null; wc -l /workspace/s2/out/*.jsonl 2>/dev/null | tail -n 1' ;;
  fetch) do_fetch ;;
  finish) do_fetch; bash "$P" terminate --force || true; bash "$P" status || true ;;
  *) echo "session.sh stage|launch|tail|fetch|finish"; exit 2 ;;
esac
