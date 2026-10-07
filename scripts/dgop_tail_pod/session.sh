#!/bin/bash
# 끝 모음 측정 파드 세션(맥, docs/dgop-final-vowel-2026-10.md). 파드는 liplab-lab의 tools/pod/pod.sh로만 다룬다.
#   bash scripts/dgop_tail_pod/session.sh stage    묶음(파드 없음): 이 브랜치 backend, measure.py·run.sh, 작업 목록, 538·608·서버 음성 소리
#   bash scripts/dgop_tail_pod/session.sh launch   파드 생성(워치독) → wait(자폭 타이머) → 올리기 → sha256 → run.sh
#   bash scripts/dgop_tail_pod/session.sh tail     파드 로그 끝부분
#   bash scripts/dgop_tail_pod/session.sh finish   결과 받기 → terminate → status
# 상태 폴더 .fvstate, 파드 이름 liplab-fv. RunPod 키는 pod.sh가 ~/.runpod/config.toml에서 메모리로만 읽는다.
# 538·608 원자료는 lab 묶음 폴더와 파드에만 두고 앱 저장소에 넣지 않는다.
set -uo pipefail
APP=$(cd "$(dirname "$0")/../.." && pwd)
LAB=${LAB:-$HOME/Downloads/liplab-lab}
P="$LAB/tools/pod/pod.sh"
export POD_STATE_DIR=${POD_STATE_DIR:-$LAB/tools/pod/.fvstate} POD_NAME=${POD_NAME:-liplab-fv} POD_DISK_GB=${POD_DISK_GB:-60}
export DEADMAN_GRACE_MIN=${DEADMAN_GRACE_MIN:-15}
M8=${M8:-$LAB/models/dgop_ours_2026-09-25_int8}
FP32=${FP32:-$LAB/models/dgop_ours_2026-09-25/aligner}
SC_OUT=${SC_OUT:-$LAB/data/pod_runs/20261006_35zrgz6wvrqiho/sc/out}
S=${STAGE_DIR:-$LAB/data/fv_stage}
GPUS=${GPUS:-NVIDIA A40|SECURE,NVIDIA RTX A6000|SECURE,NVIDIA L40S|SECURE}
WD_MIN=${WD_MIN:-120}
SHA_ALIGNER=18681947f740b7486f8fa4f93c7c0f68fe1595ac4fa9822800dfd38d713f5e66
SHA_SCORER=e8340d58dd911e380eca508815526eb77ec658560456ce1fe4c16b9b6e3654c4
mkdir -p "$S" "$LAB/data/pod_runs" "$POD_STATE_DIR"
CMD=${1:-}
LOG="$LAB/data/pod_runs/session_fv_${CMD}_$(date +%Y%m%d_%H%M).log"
exec > >(tee -a "$LOG") 2>&1
step() { echo "=== $(date '+%F %T') $*"; }
die() { echo "FVS_FAIL $*"; exit 1; }
pod_id() { awk -F= '$1 == "POD_ID" {print $2}' "$POD_STATE_DIR/.pod_state" 2>/dev/null; }
sha_of() { shasum -a 256 "$1" | cut -d' ' -f1; }

do_stage() {
  step "가중치 확인"
  [ "$(sha_of "$M8/aligner/model.int8.safetensors")" = "$SHA_ALIGNER" ] || die "정렬기 sha256"
  [ "$(sha_of "$M8/scorer/model.int8.safetensors")" = "$SHA_SCORER" ] || die "채점기 sha256"
  [ -s "$FP32/model.safetensors" ] || die "fp32 정렬기 없음"
  step "묶음"
  R=$S/root
  rm -rf "$R" && mkdir -p "$R/backend/data" "$R/scripts" "$R/data/c538wav" "$R/data/hi608/wav16" "$R/data/tts" "$R/models"
  cp "$APP"/backend/*.py "$R/backend/" || die backend
  cp "$APP"/backend/data/dgop_calibration*.json "$R/backend/data/" || die calibration
  cp "$APP"/scripts/dgop_tail_pod/measure.py "$APP"/scripts/dgop_tail_pod/run.sh "$R/scripts/" || die scripts
  for m in aligner scorer; do
    mkdir -p "$R/backend/models/dgop_ours/$m"
    for f in "$M8/$m"/*; do case "$(basename "$f")" in model.int8.safetensors) ;; *) cp "$f" "$R/backend/models/dgop_ours/$m/" ;; esac; done
  done
  mkdir -p "$R/models/aligner_fp32"
  for f in "$FP32"/*; do case "$(basename "$f")" in model.safetensors|.done) ;; *) cp "$f" "$R/models/aligner_fp32/" ;; esac; done
  python3 "$APP/scripts/dgop_tail_pod/build_jobs.py" "$SC_OUT" "$LAB/data/scores_2026-10-06/dgop_pairs.csv" "$APP/backend/data/sound" "$R/data" || die jobs
  python3 - "$R/data" "$LAB" "$APP/backend/data/sound/clips" <<'EOF' || die "소리 복사"
import json, os, shutil, sys
d, lab, clips = sys.argv[1:4]
n = {"538": 0, "608": 0, "tts": 0}
sess = set()
for l in open(f"{d}/jobs.jsonl", encoding="utf-8"):
    j = json.loads(l)
    if j["set"] == "538":
        shutil.copy(f"{lab}/data/s12stage/root/c538wav/{j['clip']}.wav", f"{d}/c538wav/"); n["538"] += 1
    else:
        sess.add(j["file"])
for f in sorted(sess):
    shutil.copy(f"{lab}/data/s12stage/root/hi608/wav16/{f}", f"{d}/hi608/wav16/"); n["608"] += 1
for l in open(f"{d}/tts_jobs.jsonl", encoding="utf-8"):
    j = json.loads(l)
    shutil.copy(os.path.join(clips, j["file"]), f"{d}/tts/"); n["tts"] += 1
print("COPIED", n)
EOF
  ( cd "$R" && find backend scripts data models -type f | sort | xargs shasum -a 256 ) > "$R/expect.sha256"
  printf '%s  backend/models/dgop_ours/aligner/model.int8.safetensors\n%s  backend/models/dgop_ours/scorer/model.int8.safetensors\n' \
    "$SHA_ALIGNER" "$SHA_SCORER" >> "$R/expect.sha256"
  COPYFILE_DISABLE=1 tar --no-mac-metadata --no-xattrs --exclude .DS_Store --exclude '._*' -cf "$S/fv.tar" -C "$R" . || die tar
  ls -la "$S/fv.tar"
  echo "FVS_STAGE_OK"
}

do_launch() {
  [ -s "$S/fv.tar" ] || die "묶음 없음(stage 먼저)"
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
  echo "FVS_POD $(pod_id)"
  bash "$P" wait || { bash "$P" terminate --force || true; die wait; }
  bash "$P" ssh 'nproc; cat /sys/fs/cgroup/cpu.max 2>/dev/null; free -g | head -2; df -h /workspace | tail -1; nvidia-smi --query-gpu=name,memory.total --format=csv,noheader'
  step "올리기"
  python3 "$LAB/tools/pod/pupload.py" "$S/fv.tar" /workspace/fv.tar "$M8/aligner/model.int8.safetensors" /workspace/aligner.int8 \
    "$M8/scorer/model.int8.safetensors" /workspace/scorer.int8 "$FP32/model.safetensors" /workspace/aligner.fp32 \
    --chunk-mb 8 --par 24 > "$S/pupload.log" 2>&1
  PUP_RC=$?
  tail -n 4 "$S/pupload.log"
  { [ "$PUP_RC" = 0 ] && grep -q '^PUP_DONE ok=4 fail=0' "$S/pupload.log"; } || { bash "$P" terminate --force || true; die "upload(rc=$PUP_RC)"; }
  bash "$P" ssh 'mkdir -p /workspace/fv && cd /workspace/fv && tar -xf ../fv.tar && rm -f ../fv.tar && mv ../aligner.int8 backend/models/dgop_ours/aligner/model.int8.safetensors && mv ../scorer.int8 backend/models/dgop_ours/scorer/model.int8.safetensors && mv ../aligner.fp32 models/aligner_fp32/model.safetensors && sha256sum -c --quiet expect.sha256 && echo REMOTE_SHA_OK' \
    | tee "$S/unpack.log" || { bash "$P" terminate --force || true; die "풀기"; }
  grep -q '^REMOTE_SHA_OK' "$S/unpack.log" || { bash "$P" terminate --force || true; die "sha256 불일치"; }
  step "run.sh 시작"
  bash "$P" run 'bash /workspace/fv/scripts/run.sh' || { bash "$P" terminate --force || true; die run; }
  echo "FVS_LAUNCH_OK $(pod_id)"
}

do_fetch() {
  POD=$(pod_id)
  [ -n "$POD" ] || die "파드 없음"
  out="$LAB/data/pod_runs/$(date +%Y%m%d)_${POD}/fv"
  mkdir -p "$out"
  if bash "$P" ssh 'test -s /workspace/fv_result.tgz && grep -q "^FV_OK" /workspace/dax/logs/fv.log'; then
    bash "$P" ssh 'cat /workspace/fv_result.tgz' > "$out/result.tgz" && tar -xzf "$out/result.tgz" -C "$out" && echo "FVS_FETCH_OK $out" || echo "FVS_FETCH_WARN"
  else
    bash "$P" ssh 'cd /workspace/fv && tar -czf - out/*.jsonl ../dax/logs/*.log 2>/dev/null' | tar -xzf - -C "$out" && echo "FVS_FETCH_PARTIAL $out" || echo "FVS_FETCH_WARN"
  fi
  ls -la "$out" "$out/out" 2>/dev/null | tail -20
}

case "$CMD" in
  stage) do_stage ;;
  launch) do_launch ;;
  tail) bash "$P" ssh 'tail -n 30 /workspace/dax/logs/fv.log; wc -l /workspace/fv/out/*.jsonl 2>/dev/null | tail -n 1' ;;
  fetch) do_fetch ;;
  finish) do_fetch; bash "$P" terminate --force || true; bash "$P" status || true ;;
  *) echo "session.sh stage|launch|tail|fetch|finish"; exit 2 ;;
esac
