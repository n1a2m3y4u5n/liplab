#!/bin/bash
# 목소리별 대조 측정 파드 세션(맥, docs/listen-voice-contrast-2026-10.md). 파드는 liplab-lab의 tools/pod/pod.sh로만 다룬다.
#   bash scripts/sound_pod/contrast_session.sh stage TARGETS.jsonl   1차 묶음(파드 없음): 점수 스크립트 + 대상 + 대상 클립(Ogg)
#   bash scripts/sound_pod/contrast_session.sh launch                파드 생성(워치독) → wait → 속도 점검 → 올리기 → score 시작
#                                                                    → setup2(다시 합성 환경) 시작 → D-GOP 모델 올리기
#   bash scripts/sound_pod/contrast_session.sh tail [score|setup2|resynth]   파드 로그 끝부분
#   bash scripts/sound_pod/contrast_session.sh fetch                 점수(work/score.jsonl)와 로그를 RUN/vc/로
#   bash scripts/sound_pod/contrast_session.sh stage2 TARGETS COMPS  2차 묶음: 앱 백엔드 코드 + 소리 점검 스크립트 + 다시 합성 대상
#   bash scripts/sound_pod/contrast_session.sh resynth               2차 묶음 올리기 → resynth 시작
#   bash scripts/sound_pod/contrast_session.sh fetch2                result.tgz를 RUN/vcr/에 푼다
#   bash scripts/sound_pod/contrast_session.sh finish                fetch → (있으면) fetch2 → terminate → status
# 상태 폴더 .vcstate, 파드 이름 liplab-vc(다른 작업과 섞이지 않게). 키는 pod.sh가 ~/.runpod/config.toml에서 메모리로만 읽는다.
# 올리는 것: 저장소의 합성 소리(Ogg), 스크립트, 앱 백엔드 코드, 앱 D-GOP 모델(다시 합성 판정용). AI Hub 자료는 올리지 않는다.
set -uo pipefail
APP=$(cd "$(dirname "$0")/../.." && pwd)
LAB=${LAB:-$HOME/Downloads/liplab-lab}
P="$LAB/tools/pod/pod.sh"
export POD_STATE_DIR=${POD_STATE_DIR:-$LAB/tools/pod/.vcstate} POD_NAME=${POD_NAME:-liplab-vc} POD_DISK_GB=${POD_DISK_GB:-50}
export DEADMAN_GRACE_MIN=${DEADMAN_GRACE_MIN:-15} REMOTE_DAX=/workspace/vc
MODELS=${MODELS:-$HOME/Downloads/liplab-integrate/backend/models/dgop_ours}
S=${STAGE_DIR:-$LAB/data/vc_stage}
GPUS=${GPUS:-NVIDIA A40|SECURE,NVIDIA RTX A6000|SECURE,NVIDIA L40S|SECURE}
WD_MIN=${WD_MIN:-150}
mkdir -p "$S" "$LAB/data/pod_runs" "$POD_STATE_DIR"
CMD=${1:-}
LOG="$LAB/data/pod_runs/session_vc_${CMD}_$(date +%Y%m%d_%H%M).log"
exec > >(tee -a "$LOG") 2>&1
step() { echo "=== $(date '+%F %T') $*"; }
die() { echo "VC_SESSION_FAIL $*"; exit 1; }
pod_id() { awk -F= '$1 == "POD_ID" {print $2}' "$POD_STATE_DIR/.pod_state" 2>/dev/null; }
TARF=(--no-mac-metadata --no-xattrs --exclude .DS_Store --exclude '._*')

upload() {  # 로컬 tar, 원격 폴더
  local tarf=$1 dest=$2 name
  name=$(basename "$tarf")
  python3 "$LAB/tools/pod/pupload.py" "$tarf" "/workspace/$name" --chunk-mb 8 --par 24 > "$S/pupload_$name.log" 2>&1
  local rc=$?
  tail -n 2 "$S/pupload_$name.log"
  { [ "$rc" = 0 ] && grep -q '^PUP_DONE ok=1 fail=0' "$S/pupload_$name.log"; } || die "upload $name(rc=$rc, 파드는 그대로: finish로 정리)"
  bash "$P" ssh "mkdir -p $dest && cd $dest && tar -xf /workspace/$name && rm -f /workspace/$name && sha256sum -c --quiet expect.sha256 && echo REMOTE_SHA_OK" \
    | tee "$S/unpack_$name.log" || die "풀기 $name"
  grep -q '^REMOTE_SHA_OK' "$S/unpack_$name.log" || die "파드 쪽 sha256 불일치 $name"
}

do_stage() {
  local T=${1:-}
  [ -s "$T" ] || die "대상 목록 없음: $T"
  step "1차 묶음"
  R=$S/root1
  rm -rf "$R" && mkdir -p "$R/scripts" "$R/sound/clips" "$R/work"
  cp "$APP"/scripts/sound_pod/contrast_score.py "$APP"/scripts/sound_pod/contrast_run.sh "$R/scripts/" || die scripts
  cp "$T" "$R/work/targets.jsonl"
  python3 - "$R/work/targets.jsonl" "$APP/backend/data/sound/clips" "$R/sound/clips" <<'EOF' || die "클립 고르기"
import json, os, shutil, sys
ids = {json.loads(l)["clip"] for l in open(sys.argv[1], encoding="utf-8") if l.strip()}
for i in ids:
    shutil.copy(os.path.join(sys.argv[2], i + ".ogg"), sys.argv[3])
print("CLIPS", len(ids))
EOF
  ( cd "$R" && find scripts sound work -type f | sort | xargs shasum -a 256 ) > "$R/expect.sha256"
  COPYFILE_DISABLE=1 tar "${TARF[@]}" -cf "$S/vc1.tar" -C "$R" . || die tar
  step "D-GOP 모델 묶음(다시 합성 판정용, 앱 체크포인트)"
  M=$S/rootm
  if [ ! -s "$S/vcm.tar" ]; then
    rm -rf "$M" && mkdir -p "$M/models/dgop_ours"
    for d in aligner scorer; do mkdir -p "$M/models/dgop_ours/$d" && cp "$MODELS/$d"/* "$M/models/dgop_ours/$d/" || die "모델 $d"; done
    ( cd "$M" && find models -type f | sort | xargs shasum -a 256 ) > "$M/expect.sha256"
    COPYFILE_DISABLE=1 tar "${TARF[@]}" -cf "$S/vcm.tar" -C "$M" . || die tar_m
  fi
  ls -la "$S/vc1.tar" "$S/vcm.tar"
  echo "VC_STAGE_OK"
}

do_launch() {
  [ -s "$S/vc1.tar" ] || die "묶음 없음(stage 먼저)"
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
  echo "VC_POD $POD"
  bash "$P" wait || { bash "$P" terminate --force || true; die wait; }
  step "올리기 속도 점검(8MB)"
  T0=$(python3 -c 'import time; print(time.time())')
  head -c 8388608 /dev/urandom | perl -e 'alarm 90; exec @ARGV' bash "$P" ssh 'cat > /workspace/.speedtest && wc -c < /workspace/.speedtest && rm -f /workspace/.speedtest' \
    || { bash "$P" terminate --force || true; die speedtest; }
  T1=$(python3 -c 'import time; print(time.time())')
  echo "UPLOAD_MBPS $(python3 -c "print(round(8 / max(1e-3, $T1 - $T0), 2))") (연결 하나)"
  bash "$P" ssh 'nproc; cat /sys/fs/cgroup/cpu.max 2>/dev/null; cat /sys/fs/cgroup/cpu/cpu.cfs_quota_us 2>/dev/null; free -g | head -2; df -h /workspace | tail -1; nvidia-smi --query-gpu=name,memory.total --format=csv,noheader'
  step "1차 올리기"
  upload "$S/vc1.tar" /workspace/vc
  step "score 시작"
  bash "$P" run "bash /workspace/vc/scripts/contrast_run.sh score" || die run_score
  step "setup2 시작(다시 합성 환경, 결과와 무관하게 미리)"
  bash "$P" run "bash /workspace/vc/scripts/contrast_run.sh setup2" || die run_setup2
  step "D-GOP 모델 올리기"
  upload "$S/vcm.tar" /workspace/sqa
  echo "VC_LAUNCH_OK $POD"
}

do_fetch() {
  POD=$(pod_id)
  [ -n "$POD" ] || die "파드 없음"
  out="$LAB/data/pod_runs/$(date +%Y%m%d)_${POD}/vc"
  mkdir -p "$out"
  bash "$P" ssh 'cd /workspace/vc && tar -czf - $(ls -d work/score.jsonl work/targets.jsonl logs 2>/dev/null)' | tar -xzf - -C "$out" \
    && echo "VC_FETCH_OK $out" || echo "VC_FETCH_WARN"
  ls -la "$out" "$out/work" 2>/dev/null | tail -8
}

do_stage2() {
  local T=${1:-} C=${2:-}
  [ -s "$T" ] && [ -s "$C" ] || die "stage2 TARGETS COMPS"
  step "2차 묶음"
  R=$S/root2
  rm -rf "$R" && mkdir -p "$R/backend/data" "$R/scripts" "$R/sound/clips" "$R/work"
  cp "$APP"/backend/*.py "$R/backend/" || die backend
  cp "$APP"/backend/data/dgop_calibration*.json "$R/backend/data/" || die calibration
  cp "$APP"/scripts/sound_pod/qa_*.py "$APP"/scripts/sound_pod/qa_ref.json "$APP"/scripts/sound_pod/contrast_score.py \
     "$APP"/scripts/sound_pod/contrast_pick.py "$R/scripts/" || die scripts
  cp "$T" "$R/work/targets.jsonl"; cp "$C" "$R/work/comps.jsonl"
  python3 - "$R/work/comps.jsonl" "$APP/backend/data/sound/clips" "$R/sound/clips" <<'EOF' || die "클립 고르기"
import json, os, shutil, sys
ids = {json.loads(l)["clip"] for l in open(sys.argv[1], encoding="utf-8") if l.strip()}
for i in ids:
    shutil.copy(os.path.join(sys.argv[2], i + ".ogg"), sys.argv[3])
print("CLIPS", len(ids))
EOF
  ( cd "$R" && find backend scripts sound work -type f | sort | xargs shasum -a 256 ) > "$R/expect.sha256"
  COPYFILE_DISABLE=1 tar "${TARF[@]}" -cf "$S/vc2.tar" -C "$R" . || die tar
  ls -la "$S/vc2.tar"
  echo "VC_STAGE2_OK"
}

do_resynth() {
  [ -s "$S/vc2.tar" ] || die "stage2 먼저"
  upload "$S/vc2.tar" /workspace/sqa
  # contrast_run.sh는 1차 묶음에 있다(같은 판). resynth 단계가 쓰는 contrast_score·pick은 2차 묶음의 scripts/
  bash "$P" run "bash /workspace/vc/scripts/contrast_run.sh resynth" || die run_resynth
  echo "VC_RESYNTH_LAUNCH_OK"
}

do_fetch2() {
  POD=$(pod_id)
  [ -n "$POD" ] || die "파드 없음"
  out="$LAB/data/pod_runs/$(date +%Y%m%d)_${POD}/vcr"
  mkdir -p "$out"
  if bash "$P" ssh 'test -s /workspace/sqa/result.tgz && grep -q VC_RESYNTH_OK /workspace/vc/logs/resynth.log'; then
    bash "$P" ssh 'cat /workspace/sqa/result.tgz' > "$out/result.tgz" && tar -xzf "$out/result.tgz" -C "$out" && echo "VC_FETCH2_OK $out" || echo "VC_FETCH2_WARN"
  else
    bash "$P" ssh 'cd /workspace/sqa && tar -czf - $(ls -d work/judged.*.jsonl work/cand_score.jsonl logs 2>/dev/null)' | tar -xzf - -C "$out" \
      && echo "VC_FETCH2_PARTIAL $out" || echo "VC_FETCH2_WARN"
  fi
  ls -la "$out" | tail -12
}

case "$CMD" in
  stage) do_stage "${2:-}" ;;
  launch) do_launch ;;
  tail) bash "$P" ssh "tail -n 30 /workspace/vc/logs/${2:-score}.log" ;;
  fetch) do_fetch ;;
  stage2) do_stage2 "${2:-}" "${3:-}" ;;
  resynth) do_resynth ;;
  fetch2) do_fetch2 ;;
  finish) do_fetch; bash "$P" ssh 'test -d /workspace/sqa/work/cand' && do_fetch2; bash "$P" terminate --force || true; bash "$P" status || true ;;
  *) echo "contrast_session.sh stage|launch|tail|fetch|stage2|resynth|fetch2|finish"; exit 2 ;;
esac
